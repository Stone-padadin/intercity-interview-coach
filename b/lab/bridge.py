"""Single serial owner, private durable outbox and loopback experiment-service client."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import queue
import re
import sqlite3
import threading
import time
from pathlib import Path
from urllib import request, error, parse
import uuid

SCHEMA = 'b.lab.v1'
ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
KINDS = {'asr.final', 'tts.final', 'agent.final', 'device.status', 'speech.status', 'clock.sync'}
PHASES = {'prepare', 'record', 'analysis', 'review', 'paused', 'ended'}


def decode_frame(line):
    """Ignore SDK logs/echoes; malformed private payloads are never echoed to the terminal."""
    if not line.startswith(b'BLAB1 '):
        return None
    if len(line) > 4096:
        raise ValueError('oversized lab frame')
    event = json.loads(line[6:].decode('utf-8'))
    if not isinstance(event, dict) or event.get('schema') != SCHEMA:
        raise ValueError('unsupported schema')
    for key in ('boot_id', 'event_id'):
        if not isinstance(event.get(key), str) or not ID.fullmatch(event[key]):
            raise ValueError('invalid identity')
    exp = event.get('experiment_id')
    if not isinstance(exp, str) or (exp and not ID.fullmatch(exp)):
        raise ValueError('invalid experiment')
    for key in ('seq', 'device_ms'):
        if type(event.get(key)) is not int or not 0 <= event[key] <= 2**53-1:
            raise ValueError('invalid device clock/sequence')
    if event['seq'] < 1 or event['event_id'] != f"{event['boot_id']}-{event['seq']}":
        raise ValueError('event identity mismatch')
    if not isinstance(event.get('kind'), str) or event['kind'] not in KINDS or \
            not isinstance(event.get('phase'), str) or event['phase'] not in PHASES:
        raise ValueError('unsupported event')
    data = event.get('data')
    if not isinstance(data, dict):
        raise ValueError('invalid payload')
    if event['kind'].endswith('.final'):
        if not exp or data.get('final') is not True or data.get('confirmed') is not False:
            raise ValueError('text must be final and unconfirmed')
        if not isinstance(data.get('text'), str) or len(data['text'].encode('utf-8')) > 191:
            raise ValueError('invalid text snapshot')
        if type(data.get('truncated')) is not bool:
            raise ValueError('missing truncation flag')
        if data.get('usable_for_confirmation') is not (bool(data['text']) and not data['truncated']):
            raise ValueError('invalid completeness')
        expected = 'user_reported' if event['kind'] == 'asr.final' else 'agent_generated'
        if data.get('source') != expected:
            raise ValueError('invalid provenance')
    return event


class Clock:
    def __init__(self):
        self.pending = {}
        self.boot = None
        self.mapping = None
        self.last_host = None

    def sent(self, nonce, wall_ms, mono_ms):
        self.pending = {nonce: (wall_ms, mono_ms)}

    def observe(self, event, wall_ms, mono_ms):
        if self.last_host:
            wall_delta, mono_delta = wall_ms-self.last_host[0], mono_ms-self.last_host[1]
            if mono_delta < 0 or abs(wall_delta-mono_delta) > 100:
                self.mapping = None
        self.last_host = wall_ms, mono_ms
        if event['boot_id'] != self.boot:
            self.boot, self.mapping = event['boot_id'], None
        if event['kind'] == 'clock.sync':
            nonce = event['data'].get('nonce')
            sent = self.pending.pop(nonce, None) if isinstance(nonce, str) else None
            if sent:
                rtt = mono_ms - sent[1]
                if 0 <= rtt <= 5000 and abs(wall_ms-sent[0]-rtt) <= 100:
                    self.mapping = (sent[0]+rtt/2-event['device_ms'], rtt/2, mono_ms)
        result = {'received_at': datetime.fromtimestamp(wall_ms/1000, timezone.utc).isoformat(),
                  'occurred_at_estimated': None, 'clock_uncertainty_ms': None}
        if self.mapping and mono_ms-self.mapping[2] <= 60000:
            offset, uncertainty, _ = self.mapping
            result.update(occurred_at_estimated=datetime.fromtimestamp(
                (event['device_ms']+offset)/1000, timezone.utc).isoformat(),
                clock_uncertainty_ms=uncertainty)
        return result


class Outbox:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, hash TEXT NOT NULL, '
                        'body TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, '
                        'next_ms REAL NOT NULL DEFAULT 0)')
        self.db.execute('CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL)')
        self.db.commit()

    def insert(self, event, timing):
        canonical = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with self.lock, self.db:
            found = self.db.execute('SELECT hash FROM events WHERE id=?', (event['event_id'],)).fetchone()
            if found:
                if found[0] != digest:
                    raise ValueError('event ID collision; experiment data not overwritten')
                return False
            body = json.dumps({**event, **timing}, ensure_ascii=False)
            self.db.execute('INSERT INTO events(id,hash,body) VALUES(?,?,?)', (event['event_id'], digest, body))
        return True

    def next(self, now):
        with self.lock:
            return self.db.execute('SELECT id,body,attempts FROM events WHERE delivered=0 AND next_ms<=? '
                                   'ORDER BY rowid LIMIT 1', (now,)).fetchone()

    def finish(self, event_id, delivered, attempts, now):
        with self.lock, self.db:
            self.db.execute('UPDATE events SET delivered=?,attempts=?,next_ms=? WHERE id=?',
                            (int(delivered), attempts+1, now+min(30000, 500*2**min(attempts, 6)), event_id))

    def claim_command(self, command):
        """Persist before serial write. An uncertain write is not automatically spoken twice."""
        body = json.dumps(command, sort_keys=True, ensure_ascii=False)
        with self.lock, self.db:
            row = self.db.execute('SELECT body FROM commands WHERE id=?', (command['command_id'],)).fetchone()
            if row:
                if row[0] != body:
                    raise ValueError('command ID collision')
                return False
            self.db.execute('INSERT INTO commands VALUES(?,?,?)', (command['command_id'], body, 'write_pending'))
            return True

    def command_state(self, ident, state):
        with self.lock, self.db:
            self.db.execute('UPDATE commands SET state=? WHERE id=?', (state, ident))

    def close(self):
        self.db.close()


def encode_command(command, experiment, now):
    if not isinstance(command, dict) or command.get('schema') != 'b.lab.command.v1':
        raise ValueError('invalid command schema')
    ident = command.get('command_id', '')
    if not isinstance(ident, str) or not ID.fullmatch(ident) or len(ident) > 32:
        raise ValueError('invalid command ID')
    if command.get('experiment_id') != experiment:
        raise ValueError('wrong experiment')
    expires = command.get('expires_at_ms')
    if type(expires) is not int or not now < expires <= now+60000:
        raise ValueError('expired or unbounded command')
    op, arg = command.get('operation'), command.get('argument')
    if op == 'mode' and isinstance(arg, str) and arg in PHASES:
        line = f'lab mode {ident} {arg}'
    elif op == 'cancel' and arg is None:
        line = f'lab cancel {ident}'
    elif op == 'speak' and isinstance(arg, str) and 0 < len(arg.encode('utf-8')) <= 64:
        if '\x00' in arg:
            raise ValueError('NUL in speech')
        line = f'lab speak {ident} {expires-now} {arg.encode("utf-8").hex()}'
    else:
        raise ValueError('unsupported command')
    return (line+'\r\n').encode('ascii')


def json_request(url, body=None):
    data = None if body is None else body.encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json'},
                          method='GET' if data is None else 'POST')
    # Do not follow redirects with experiment data, even from the local service.
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = request.build_opener(request.ProxyHandler({}), NoRedirect)
    try:
        with opener.open(req, timeout=2) as response:
            status, payload = response.status, response.read(65537)
    except error.HTTPError as exc:
        status, payload = exc.code, exc.read(65537)
    if len(payload) > 65536:
        raise ValueError('oversized service response')
    return status, json.loads(payload)


def deliver_one(store, base, now):
    row = store.next(now)
    if not row:
        return False
    ident, body, attempts = row
    success = False
    try:
        code, result = json_request(base+'/api/lab/device-events', body)
        success = (200 <= code < 300 or code == 409) and isinstance(result, dict) and \
            result.get('event_id') == ident and result.get('status') in ('accepted', 'duplicate')
    except (OSError, ValueError):
        pass
    store.finish(ident, success, attempts, now)
    return True


def run(port, base, experiment, database):
    import serial
    store, clock, outgoing, done = Outbox(database), Clock(), queue.Queue(maxsize=16), threading.Event()
    ready = threading.Event()
    def service():
        last_poll = 0
        while not done.is_set():
            stamp = int(time.time()*1000)
            deliver_one(store, base, stamp)
            if ready.is_set() and stamp-last_poll >= 500:
                last_poll = stamp
                try:
                    url = base+'/api/lab/device-commands?'+parse.urlencode({'experiment_id': experiment})
                    code, result = json_request(url)
                    if code == 200 and isinstance(result, dict) and isinstance(result.get('commands'), list):
                        for command in result['commands'][:16]:
                            encoded = encode_command(command, experiment, int(time.time()*1000))
                            if outgoing.full():
                                break
                            if store.claim_command(command):
                                outgoing.put_nowait((command, encoded))
                except (OSError, ValueError, queue.Full):
                    pass
            done.wait(.05)
    device = serial.Serial(port=None, baudrate=115200, timeout=.1, write_timeout=1)
    device.dtr = False; device.rts = False; device.port = port
    worker = None
    try:
        with device:
            device.write(b'echo off\r\n')  # CLI character echo must not split async JSON frames.
            device.write(f'lab bind {experiment}\r\n'.encode('ascii'))
            buffer, last_sync, boot = bytearray(), -30000, None
            worker = threading.Thread(target=service, daemon=True); worker.start()
            while True:
                mono, wall = time.monotonic()*1000, time.time()*1000
                if mono-last_sync > 30000:
                    nonce = uuid.uuid4().hex
                    clock.sent(nonce, wall, mono)
                    device.write(f'lab sync {nonce}\r\n'.encode()); last_sync = mono
                try:
                    cmd, data = outgoing.get_nowait()
                    # Check expiry again: queued work must not become stale speech.
                    data = encode_command(cmd, experiment, int(time.time()*1000))
                    device.write(data); store.command_state(cmd['command_id'], 'written_unconfirmed')
                except queue.Empty:
                    pass
                except ValueError:
                    store.command_state(cmd['command_id'], 'expired_before_write')
                buffer.extend(device.read(max(1, min(device.in_waiting, 4096))))
                while b'\n' in buffer:
                    raw, _, buffer = buffer.partition(b'\n')
                    try:
                        event = decode_frame(raw.rstrip(b'\r'))
                        if event is None:
                            continue
                        if boot is not None and boot != event['boot_id']:
                            # Never silently rebind/replay commands after a physical reset.
                            raise RuntimeError('Device rebooted; close the experiment and restart the bridge explicitly')
                        boot = event['boot_id']
                        if event['experiment_id'] not in ('', experiment):
                            raise RuntimeError('Device bound to another experiment')
                        if event['kind'] == 'device.status' and event['data'].get('status') == 'bound' and event['experiment_id'] == experiment:
                            ready.set()
                        timing = clock.observe(event, time.time()*1000, time.monotonic()*1000)
                        store.insert(event, timing)
                    except (ValueError, UnicodeError):
                        print('Rejected malformed lab frame; private content omitted.', flush=True)
                if len(buffer) > 4096:
                    buffer.clear()
                    print('Serial line exceeded limit; discarded without printing.', flush=True)
    finally:
        done.set()
        if worker:
            worker.join(6)
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--experiment-id', required=True)
    parser.add_argument('--service', default='http://127.0.0.1:8000')
    parser.add_argument('--database', type=Path, default=Path('.local/lab/bridge.sqlite3'))
    args = parser.parse_args()
    url = parse.urlsplit(args.service)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost', '::1') or \
            url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        parser.error('--service must be a loopback HTTP origin without credentials, path or query')
    if not ID.fullmatch(args.experiment_id):
        parser.error('experiment ID must be 1-64 ASCII letters/digits/underscore/hyphen')
    try:
        run(args.port, args.service.rstrip('/'), args.experiment_id, args.database)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
