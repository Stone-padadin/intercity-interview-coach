"""Synthetic events and loopback HTTP only; these tests never open a board."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import bridge
import prepare


def event(seq=1, kind='asr.final', **data):
    payload = dict(text='测试点A电压2.5伏', final=True, truncated=False,
                   usable_for_confirmation=True, confirmed=False, source='user_reported')
    payload.update(data)
    return dict(schema='b.lab.v1', event_id=f'bootA-{seq}', boot_id='bootA', seq=seq,
                experiment_id='synthetic_exp', device_ms=1000, phase='record', kind=kind, data=payload)


def frame(value):
    return b'BLAB1 '+json.dumps(value, ensure_ascii=False).encode('utf-8')


def command(op='speak', arg='验证编号甲七', **extra):
    value = dict(schema='b.lab.command.v1', command_id='cmd_1', experiment_id='synthetic_exp',
                 expires_at_ms=2000, operation=op, argument=arg)
    value.update(extra)
    return value


class DecodeTests(unittest.TestCase):
    def test_final_measurement_stays_unconfirmed(self):
        result = bridge.decode_frame(frame(event()))
        self.assertFalse(result['data']['confirmed'])
        self.assertEqual(result['data']['source'], 'user_reported')

    def test_ignores_legacy_logs_and_echo(self):
        for line in (b'I SDK: private example', b'> lab speak x ff', b''):
            self.assertIsNone(bridge.decode_frame(line))

    def test_partial_or_premature_confirmation_rejected(self):
        for flags in ({'final': False}, {'confirmed': True}, {'source': 'sensor_measured'}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                bridge.decode_frame(frame(event(**flags)))

    def test_truncation_is_explicitly_not_confirmable(self):
        value = event(truncated=True, usable_for_confirmation=False)
        self.assertFalse(bridge.decode_frame(frame(value))['data']['usable_for_confirmation'])
        value['data']['usable_for_confirmation'] = True
        with self.assertRaises(ValueError):
            bridge.decode_frame(frame(value))

    def test_chinese_quotes_newlines_survive_json(self):
        text = '位置"A"\n数值2.5伏'
        self.assertEqual(bridge.decode_frame(frame(event(text=text)))['data']['text'], text)

    def test_bad_types_limits_and_identity(self):
        for changes in ({'seq': True}, {'seq': -1}, {'event_id': 'other'}, {'kind': []},
                        {'phase': {}}, {'schema': 'unknown'}, {'data': None}):
            value = event(); value.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                bridge.decode_frame(frame(value))
        with self.assertRaises(ValueError):
            bridge.decode_frame(frame(event(text='中'*64)))

    def test_non_utf8_or_oversize_rejected(self):
        for value in (b'BLAB1 \xff', b'BLAB1 '+b' '*4096, b'BLAB1 {}'):
            with self.assertRaises(ValueError):
                bridge.decode_frame(value)

    def test_agent_text_cannot_be_user_measurement(self):
        value = event(kind='agent.final', source='agent_generated')
        self.assertEqual(bridge.decode_frame(frame(value))['data']['source'], 'agent_generated')

    def test_frame_longer_than_vendor_cli_buffer_is_not_cut(self):
        value = event(text='中'*63)
        encoded = frame(value)
        self.assertGreater(len(encoded), 256)
        self.assertEqual(bridge.decode_frame(encoded)['data']['text'], value['data']['text'])


class ClockTests(unittest.TestCase):
    def sync(self, clock):
        clock.sent('nonce', 100000, 2000)
        return clock.observe(event(kind='clock.sync', nonce='nonce'), 100100, 2100)

    def test_unknown_until_matching_sync(self):
        clock = bridge.Clock()
        self.assertIsNone(clock.observe(event(), 100000, 2000)['occurred_at_estimated'])
        result = self.sync(clock)
        self.assertEqual(result['clock_uncertainty_ms'], 50)
        self.assertIsNotNone(result['occurred_at_estimated'])

    def test_reboot_and_stale_mapping_become_unknown(self):
        clock = bridge.Clock(); self.sync(clock)
        self.assertIsNone(clock.observe(event(), 170000, 72101)['occurred_at_estimated'])
        value = event(); value.update(boot_id='bootB', event_id='bootB-1')
        self.assertIsNone(clock.observe(value, 100200, 2200)['occurred_at_estimated'])

    def test_wall_clock_jump_and_slow_reply_rejected(self):
        for wall, mono in ((110000, 2100), (106000, 8000)):
            clock = bridge.Clock(); clock.sent('nonce', 100000, 2000)
            self.assertIsNone(clock.observe(event(kind='clock.sync', nonce='nonce'), wall, mono)['occurred_at_estimated'])

    def test_wall_jump_invalidates_previously_valid_mapping(self):
        clock = bridge.Clock(); self.sync(clock)
        self.assertIsNone(clock.observe(event(), 110100, 2200)['occurred_at_estimated'])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'private.sqlite3'
        self.store = bridge.Outbox(self.path)

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def test_events_survive_restart_and_deduplicate_by_identity(self):
        self.assertTrue(self.store.insert(event(), {'received_at': 'synthetic'}))
        self.store.close(); self.store = bridge.Outbox(self.path)
        self.assertFalse(self.store.insert(event(), {'received_at': 'later'}))
        self.assertEqual(self.store.next(0)[0], 'bootA-1')
        self.assertTrue(self.store.insert(event(seq=2), {}))  # Repeating the same spoken words is legitimate.

    def test_same_id_different_content_never_overwrites(self):
        self.store.insert(event(), {})
        with self.assertRaises(ValueError):
            self.store.insert(event(text='different'), {})
        self.assertEqual(json.loads(self.store.next(0)[1])['data']['text'], event()['data']['text'])

    def test_uncertain_serial_command_not_replayed_after_restart(self):
        self.assertTrue(self.store.claim_command(command()))
        self.store.close(); self.store = bridge.Outbox(self.path)
        self.assertFalse(self.store.claim_command(command()))
        with self.assertRaises(ValueError):
            self.store.claim_command(command(arg='different'))

    def test_exact_ack_required_and_network_retries(self):
        self.store.insert(event(), {})
        with patch.object(bridge, 'json_request', return_value=(200, {'status': 'accepted', 'event_id': 'wrong'})):
            bridge.deliver_one(self.store, 'http://127.0.0.1', 0)
        self.assertIsNone(self.store.next(1))
        self.assertIsNotNone(self.store.next(500))
        with patch.object(bridge, 'json_request', side_effect=OSError('offline')):
            bridge.deliver_one(self.store, 'http://127.0.0.1', 500)
        with patch.object(bridge, 'json_request', return_value=(409, {'status': 'duplicate', 'event_id': 'bootA-1'})):
            bridge.deliver_one(self.store, 'http://127.0.0.1', 1500)
        self.assertIsNone(self.store.next(100000))


class CommandTests(unittest.TestCase):
    def test_speech_utf8_hex_and_device_ttl(self):
        encoded = bridge.encode_command(command(arg='A\n"甲"'), 'synthetic_exp', 1000)
        fields = encoded.decode().strip().split()
        self.assertEqual(fields[:4], ['lab', 'speak', 'cmd_1', '1000'])
        self.assertEqual(bytes.fromhex(fields[4]).decode(), 'A\n"甲"')
        self.assertLess(len(encoded), 256)

    def test_bad_experiment_id_expiry_and_size(self):
        for changes in ({'experiment_id': 'other'}, {'command_id': 'injection\n'},
                        {'expires_at_ms': 1000}, {'expires_at_ms': 70000}, {'expires_at_ms': True},
                        {'argument': '中'*22}, {'argument': '\x00'}, {'argument': ''}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                bridge.encode_command(command(**changes), 'synthetic_exp', 1000)

    def test_state_and_cancel_have_correlatable_command_ids(self):
        for phase in bridge.PHASES:
            self.assertIn(f'lab mode cmd_1 {phase}'.encode(), bridge.encode_command(command('mode', phase), 'synthetic_exp', 1000))
        self.assertEqual(bridge.encode_command(command('cancel', None), 'synthetic_exp', 1000), b'lab cancel cmd_1\r\n')
        with self.assertRaises(ValueError):
            bridge.encode_command(command('mode', []), 'synthetic_exp', 1000)


class HTTPTests(unittest.TestCase):
    def test_actual_local_http_delivery(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append(data)
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps(dict(event_id=data['event_id'], status='accepted')).encode())
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server, tempfile.TemporaryDirectory() as temp:
            worker = threading.Thread(target=server.serve_forever); worker.start()
            store = bridge.Outbox(Path(temp)/'private.db')
            try:
                store.insert(event(), {'occurred_at_estimated': None})
                bridge.deliver_one(store, f'http://127.0.0.1:{server.server_port}', 0)
                self.assertIsNone(store.next(100000))
                self.assertEqual(len(seen), 1)
                self.assertFalse(seen[0]['data']['confirmed'])
            finally:
                store.close(); server.shutdown(); worker.join()


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.app = self.root/'apps/main'; (self.app/'b_device').mkdir(parents=True)
        (self.app/'b_device/b_device_runtime.c').write_text('existing B', encoding='utf-8')
        (self.app/'CMakeLists.txt').write_text(
            'set(B_DEVICE_PROFILE "off" CACHE STRING "B device profile: off, voice, integrated")\n'
            '# 闹钟：平台组件和应用层模块一起开关，CONFIG_QM_ALARM_SUPPORT 0 时两者都不编译\n'
            '    "./b_device"\nif(NOT B_DEVICE_PROFILE STREQUAL "off")\n    target_compile_definitions', encoding='utf-8')
        (self.app/'main.c').write_text('#include "b_device_runtime.h"\n#endif\n'
            '#if defined(CONFIG_APP_CAMERA_TEST) && CONFIG_APP_CAMERA_TEST\n    if (bsp_camera_early_init()', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_preserves_then_install_backs_up_and_repeat_refuses(self):
        original = (self.app/'main.c').read_bytes()
        with patch.object(prepare.subprocess, 'check_output', return_value=prepare.PIN):
            prepare.install(self.root, self.root/'backup', check=True)
            self.assertEqual((self.app/'main.c').read_bytes(), original)
            backup = prepare.install(self.root, self.root/'backup')
            self.assertEqual((backup/'main.c').read_bytes(), original)
            self.assertEqual((self.app/'b_device/b_device_runtime.c').read_text(), 'existing B')
            with self.assertRaises(ValueError):
                prepare.install(self.root, self.root/'backup')

    def test_unknown_anchor_or_revision_changes_nothing(self):
        before = (self.app/'CMakeLists.txt').read_bytes()
        (self.app/'main.c').write_text('unknown main', encoding='utf-8')
        with patch.object(prepare.subprocess, 'check_output', return_value=prepare.PIN), self.assertRaises(ValueError):
            prepare.install(self.root, self.root/'backup')
        self.assertEqual((self.app/'CMakeLists.txt').read_bytes(), before)
        self.assertFalse((self.app/'b_lab').exists())
        with patch.object(prepare.subprocess, 'check_output', return_value='wrong'), self.assertRaises(ValueError):
            prepare.install(self.root, self.root/'backup')


if __name__ == '__main__':
    unittest.main()
