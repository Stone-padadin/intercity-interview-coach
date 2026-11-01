"""Real loopback/SQLite integration with explicitly synthetic ASR; no hardware."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib import request, error
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab_server import create_server, DEFAULT_EXPERIMENT, now

VALUES = dict(point='TP_TEST', quantity='voltage', value='2.70', unit='V', conditions='合成测试：空载', retest_of='')


class Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.server = create_server(self.root, 0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = request.build_opener(request.ProxyHandler({}))
        self.seq = 0

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(3)
        self.folder.cleanup()

    def get(self, path):
        with self.opener.open(self.base + path, timeout=5) as response:
            return json.load(response)

    def post(self, path, body, headers=None):
        req = request.Request(self.base + path, data=json.dumps(body).encode(),
                              headers={'Content-Type': 'application/json', **(headers or {})})
        with self.opener.open(req, timeout=5) as response:
            return json.load(response)

    def change(self, path, **body):
        self.seq += 1
        payload = dict(experiment_id=self.get('/api/workspace/state')['active_id'], request_id=f'test_{self.seq}')
        payload.update(body)
        return self.post('/api/workspace/' + path, payload)['result']

    def current(self):
        state = self.get('/api/workspace/state')
        return next(item for item in state['experiments'] if item['id'] == state['active_id'])

    def draft(self):
        return self.change('measurements/draft', **VALUES)

    def confirm(self, draft, **values):
        return self.change('measurements/confirm', id=draft['id'], revision=draft.get('revision', 0),
                           user_confirmed=True, **{**VALUES, **values})

    def voice(self, seq=1, text='记录，TP5电压2.7伏，空载（合成测试）'):
        return dict(schema='b.lab.v1', event_id=f'synthetic_boot-{seq}', boot_id='synthetic_boot', seq=seq,
                    experiment_id=DEFAULT_EXPERIMENT, device_ms=1000, phase='record', kind='asr.final', received_at=now(),
                    data=dict(text=text, final=True, truncated=False, usable_for_confirmation=True,
                              confirmed=False, source='user_reported'))

    def test_empty_initial_id_and_explicit_mismatch_rejected(self):
        state = self.get('/api/workspace/state')
        self.assertEqual(state['active_id'], DEFAULT_EXPERIMENT)
        self.assertEqual(self.current()['measurements'], [])
        self.assertFalse(self.get('/api/health')['voice_verified'])
        self.assertEqual(json.loads((self.root / 'session.json').read_text())['experiment_id'], DEFAULT_EXPERIMENT)
        with self.assertRaises(ValueError):
            create_server(self.root, 0, 'another')

    def test_manual_confirm_canonical_c_readback_export_and_reopen(self):
        draft = self.draft()
        self.assertFalse(draft['confirmed'])
        self.assertEqual(self.get('/api/demo/state')['measurements'][0]['id'], draft['id'])
        saved = self.confirm(draft)
        self.assertEqual(saved['source'], 'manual')
        self.assertTrue(self.get('/api/demo/state')['measurements'][0]['confirmed'])
        reopened = create_server(self.root, 0)
        try:
            self.assertEqual(reopened.workspace.state()['experiments'][0]['measurements'][0]['id'], draft['id'])
            output = reopened.workspace.export(DEFAULT_EXPERIMENT)
            self.assertIn('manual', output); self.assertIn('2.70', output)
        finally:
            reopened.server_close()

    def test_real_http_receipt_dedupe_original_voice_and_confirmation(self):
        event = self.voice()
        self.assertEqual(self.post('/api/lab/device-events', event)['status'], 'accepted')
        self.assertEqual(self.post('/api/lab/device-events', event)['status'], 'duplicate')
        draft = self.current()['measurements'][0]
        self.assertEqual(len(self.current()['measurements']), 1)
        self.assertFalse(draft['confirmed'])
        saved = self.confirm(draft, point='TP5', value='2.71', conditions='合成测试：人工核对')
        self.assertEqual(saved['raw_text'], event['data']['text'])
        self.assertEqual(saved['source'], 'user_reported')
        self.assertEqual(self.get('/api/demo/state')['measurements'][0]['value'], '2.71')

    def test_device_identity_conflict_truncation_and_wrong_experiment(self):
        event = self.voice(); self.post('/api/lab/device-events', event)
        changed = copy.deepcopy(event); changed['data']['text'] = '记录，TP5 9V 空载'
        with self.assertRaises(error.HTTPError): self.post('/api/lab/device-events', changed)
        wrong = self.voice(2); wrong['experiment_id'] = 'wrong'
        with self.assertRaises(error.HTTPError): self.post('/api/lab/device-events', wrong)
        truncated = self.voice(3); truncated['data'].update(truncated=True, usable_for_confirmation=False)
        self.post('/api/lab/device-events', truncated)
        self.assertEqual(len(self.current()['measurements']), 1)

    def test_confirm_requires_consent_valid_fields_and_cannot_overwrite(self):
        draft = self.draft()
        with self.assertRaises(error.HTTPError):
            self.change('measurements/confirm', id=draft['id'], revision=0, user_confirmed=False, **VALUES)
        for value in ['NaN', 'Infinity', '1e9999', '2V']:
            with self.assertRaises(error.HTTPError): self.confirm(draft, value=value)
        self.assertFalse(self.current()['measurements'][0]['confirmed'])
        self.confirm(draft)
        with self.assertRaises(error.HTTPError): self.confirm(draft, value='9')

    def test_request_retry_is_durable_and_conflict_is_rejected(self):
        body = dict(experiment_id=DEFAULT_EXPERIMENT, request_id='retry_1', **VALUES)
        first = self.post('/api/workspace/measurements/draft', body)
        second = self.post('/api/workspace/measurements/draft', body)
        self.assertEqual(first['result']['id'], second['result']['id']); self.assertTrue(second['deduplicated'])
        with self.assertRaises(error.HTTPError):
            self.post('/api/workspace/measurements/draft', dict(body, value='9'))
        self.assertEqual(len(self.current()['measurements']), 1)

    def test_experiment_isolation_retest_and_device_binding_lock(self):
        first = self.confirm(self.draft())
        second = self.change('experiments', expected_active_id=DEFAULT_EXPERIMENT, name='第二个合成实验', background='')
        self.assertRegex(second['id'], r'^exp_[a-f0-9]{32}$')
        self.assertEqual(self.current()['measurements'], [])
        with self.assertRaises(error.HTTPError):
            self.change('measurements/draft', **{**VALUES, 'retest_of': first['id']})
        self.change('select', expected_active_id=second['id'], experiment_id=DEFAULT_EXPERIMENT)
        self.post('/api/lab/device-events', self.voice())
        with self.assertRaises(error.HTTPError):
            self.change('select', expected_active_id=DEFAULT_EXPERIMENT, experiment_id=second['id'])

    def test_session_write_failure_keeps_binding_and_retry_does_not_duplicate(self):
        body = dict(experiment_id=DEFAULT_EXPERIMENT, expected_active_id=DEFAULT_EXPERIMENT,
                    request_id='session_write_failure', name='会话写入失败测试', background='')
        with patch.object(Path, 'replace', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(error.HTTPError) as caught:
                self.post('/api/workspace/experiments', body)
        self.assertEqual(caught.exception.code, 500)
        self.assertEqual(self.get('/api/workspace/state')['active_id'], DEFAULT_EXPERIMENT)
        self.assertEqual(json.loads((self.root/'session.json').read_text())['experiment_id'], DEFAULT_EXPERIMENT)
        result = self.post('/api/workspace/experiments', body)
        self.assertTrue(result['deduplicated'])
        self.assertEqual(len(self.get('/api/workspace/state')['experiments']), 2)
        self.assertEqual(self.get('/api/workspace/state')['active_id'], result['result']['id'])

    def test_retract_restore_revision_and_exclusion_from_model_context(self):
        saved = self.confirm(self.draft())
        hidden = self.change('measurements/retract', id=saved['id'], revision=saved['revision'], retracted=True)
        with self.assertRaises(error.HTTPError):
            self.change('measurements/retract', id=saved['id'], revision=saved['revision'], retracted=False)
        lab = self.server.workspace.lab
        vision = Mock(); vision.ask_many.return_value = dict(answer='合成回答', model='test')
        with patch.object(lab, 'asset', return_value=({'id':'v_test', 'duration_seconds':2}, None)), \
             patch.object(lab, 'frame', return_value=(b'synthetic', {'media_id':'v_test', 'seconds':0, 'source_seconds':0})):
            lab.analyze(vision, dict(media_id='v_test', mode='wiring', playhead=0, question='合成问题', upload_confirmed=True))
        self.assertNotIn('TP_TEST', vision.ask_many.call_args.args[1])
        self.assertIn('已撤销', lab.export())
        restored = self.change('measurements/retract', id=saved['id'], revision=hidden['revision'], retracted=False)
        self.assertIsNone(restored['retracted_at'])

    def test_review_rejects_stale_page_and_preserves_saved_review(self):
        review = dict(issue='合成观察', hypothesis='', next_step='', conclusion='')
        self.change('review', revision=0, review=review)
        with self.assertRaises(error.HTTPError): self.change('review', revision=0, review={**review, 'issue':'覆盖'})
        self.assertEqual(self.current()['review']['issue'], '合成观察')

    def legacy(self):
        return dict(version=1, active_id='old_uuid', experiments=[dict(id='old_uuid', name='浏览器合成测试', background='',
                    created_at=now(), review={key:'' for key in ('issue','hypothesis','next_step','conclusion')},
                    measurements=[dict(id='old_measurement', **VALUES, recorded_at=now(), source='manual', confirmed=True, retracted_at=None)])])

    def test_import_preserves_ids_and_rolls_back_entire_invalid_batch(self):
        data = self.legacy(); invalid = copy.deepcopy(data)
        invalid['experiments'].append({**invalid['experiments'][0], 'id':'bad', 'name':''})
        with self.assertRaises(error.HTTPError): self.change('import', data=invalid)
        self.assertEqual(len(self.get('/api/workspace/state')['experiments']), 1)
        self.change('import', data=data)
        old = next(item for item in self.get('/api/workspace/state')['experiments'] if item['id'] == 'old_uuid')
        self.assertEqual(old['measurements'][0]['id'], 'old_measurement')
        with self.assertRaises(error.HTTPError): self.change('import', data=data)
        self.assertEqual(len(self.get('/api/workspace/state')['experiments']), 2)

    def test_linked_photo_and_measurement_confirm_together(self):
        self.server.workspace.notes.camera.snapshot = lambda: (b'synthetic-not-real-jpeg', now())
        self.post('/api/lab/device-events', self.voice(text='记一下，TP5电压2.7伏，空载（合成测试）'))
        draft = self.current()['measurements'][0]
        self.confirm(draft)
        self.assertTrue(self.get('/api/state')['notes'][0]['confirmed'])

    def test_missing_photo_keeps_both_records_unconfirmed(self):
        self.post('/api/lab/device-events', self.voice(text='记一下，TP5电压2.7伏，空载（合成测试）'))
        with self.assertRaises(error.HTTPError): self.confirm(self.current()['measurements'][0])
        self.assertFalse(self.current()['measurements'][0]['confirmed'])
        self.assertFalse(self.get('/api/state')['notes'][0]['confirmed'])

    def test_natural_split_asr_preserves_mv_and_rejects_stale_confirmation(self):
        self.post('/api/lab/device-events', self.voice(text='电压七十三点三毫伏，空载。'))
        initial = self.current()['measurements'][0]
        self.post('/api/lab/device-events', self.voice(2, '测量点是LED1。'))
        draft = self.current()['measurements'][0]
        self.assertEqual(len(self.current()['measurements']), 1)
        self.assertEqual((draft['point'], draft['value'], draft['unit']), ('LED1', '73.3', 'mV'))
        self.assertEqual(len(draft['speech_events']), 2)
        with self.assertRaises(error.HTTPError) as caught:
            self.confirm(initial, point='LED1', value='73.3', unit='mV', conditions='空载')
        self.assertEqual(caught.exception.code, 409)
        saved = self.confirm(draft, point='LED1', value='73.3', unit='mV', conditions='空载')
        self.assertEqual(saved['unit'], 'mV'); self.assertIn('七十三点三', saved['raw_text'])

    def test_manual_draft_is_never_completed_by_device_speech(self):
        manual = self.draft()
        self.post('/api/lab/device-events', self.voice(text='电压七三点三毫伏，空载。'))
        rows = self.current()['measurements']
        self.assertEqual(len(rows), 2)
        old = next(item for item in rows if item['id'] == manual['id'])
        voice = next(item for item in rows if item['source'] == 'user_reported')
        self.assertEqual(old['raw_text'], ''); self.assertEqual(voice['value'], '73.3')

    def test_capture_confirmation_uses_same_transaction_and_export(self):
        draft = self.draft()
        saved = self.post('/api/demo/measurements/confirm', dict(id=draft['id'], **VALUES, user_confirmed=True))
        self.assertEqual(saved['source'], 'manual'); self.assertTrue(self.current()['measurements'][0]['confirmed'])
        a_path = '/api/workspace/export?experiment_id=' + DEFAULT_EXPERIMENT
        with self.opener.open(self.base + a_path) as response: a_text = response.read()
        with self.opener.open(self.base + '/api/demo/export') as response: c_text = response.read()
        self.assertEqual(a_text, c_text)

    def test_negated_natural_speech_after_wake_does_not_create_measurement(self):
        self.post('/api/lab/device-events', self.voice(text='你好，小灵，请不要记录电压73.3毫伏，空载。'))
        self.assertEqual(self.current()['measurements'], [])

    def test_loopback_origin_and_private_files(self):
        with self.assertRaises(error.HTTPError) as caught:
            self.post('/api/workspace/measurements/draft', {}, {'Origin':'https://untrusted.invalid'})
        self.assertEqual(caught.exception.code, 403)
        for path in ['/session.json', '/notes.sqlite3', '/lab_server.py', '/.local/session.json']:
            with self.assertRaises(error.HTTPError) as caught: self.get(path)
            self.assertEqual(caught.exception.code, 404)

    def test_model_wait_does_not_block_fresh_voice_but_pins_experiment(self):
        started, release = threading.Event(), threading.Event()
        def waiting_model(*args):
            started.set()
            if not release.wait(4):
                raise RuntimeError('test timed out')
            return {'id':'synthetic_analysis'}
        with patch.object(self.server.workspace.lab, 'analyze', side_effect=waiting_model), ThreadPoolExecutor(max_workers=2) as pool:
            analysis=pool.submit(self.post,'/api/demo/analyze',{'upload_confirmed':True})
            try:
                self.assertTrue(started.wait(1))
                self.assertEqual(self.get('/api/workspace/state')['active_id'],DEFAULT_EXPERIMENT)
                with self.assertRaises(error.HTTPError) as caught:
                    self.change('experiments',expected_active_id=DEFAULT_EXPERIMENT,name='blocked',background='')
                self.assertEqual(caught.exception.code,409)
                receipt=pool.submit(self.post,'/api/lab/device-events',self.voice()).result(timeout=1)
                self.assertEqual(receipt['status'],'accepted')
                self.assertEqual(len(self.current()['measurements']),1)
            finally:
                release.set()
            self.assertEqual(analysis.result(timeout=2)['id'],'synthetic_analysis')
        self.assertEqual(self.server.workspace.analysis_inflight,0)

    def test_superseded_trials_stay_stored_but_out_of_both_exports(self):
        item={'id':'a_old','mode':'wiring','answer':'REJECTED_TRIAL','evidence':[],'review_status':'superseded'}
        with self.server.workspace.notes.db() as db:
            db.execute('INSERT INTO demo_analyses VALUES(?,?,?)',('a_old',DEFAULT_EXPERIMENT,json.dumps(item)))
        self.assertEqual(self.current()['analyses'],[])
        with self.opener.open(self.base+'/api/workspace/export?experiment_id='+DEFAULT_EXPERIMENT) as r:
            self.assertNotIn(b'REJECTED_TRIAL',r.read())
        with self.opener.open(self.base+'/api/demo/export') as r:
            self.assertNotIn(b'REJECTED_TRIAL',r.read())
        with self.server.workspace.notes.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM demo_analyses').fetchone()[0],1)


if __name__ == '__main__':
    unittest.main()
