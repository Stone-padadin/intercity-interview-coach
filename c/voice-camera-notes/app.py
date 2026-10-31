"""Local voice-triggered photo notes; camera images and transcripts stay in .local."""
from __future__ import annotations
import argparse
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, parse_qs
import uuid
from vision import Vision, VisionError

HERE = Path(__file__).resolve().parent
ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
KINDS = {'asr.final', 'tts.final', 'agent.final', 'device.status', 'speech.status', 'clock.sync'}
PHASES = {'prepare', 'record', 'analysis', 'review', 'paused', 'ended'}

def now():
    return datetime.now(timezone.utc).isoformat()

def stamp(value):
    if not isinstance(value, str):
        raise ValueError('missing timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return result.timestamp()

def note_text(text):
    # A command must start the utterance. Mentioning, quoting or negating it is not an action.
    text = text.strip()
    match = re.match(r'^(?:你好[，,\s]*小灵[，,。\s]*)?(?:请[，,\s]*)?(?:帮我[，,\s]*)?记一下[，,：:\s。]*(.*)$', text)
    return match.group(1).strip() if match and match.group(1).strip() else None

def validate(event, experiment):
    if not isinstance(event, dict) or event.get('schema') != 'b.lab.v1':
        raise ValueError('invalid schema')
    for key in ('boot_id', 'event_id'):
        if not isinstance(event.get(key), str) or not ID.fullmatch(event[key]):
            raise ValueError('invalid event identity')
    if type(event.get('seq')) is not int or event['seq'] < 1 or event['event_id'] != f"{event['boot_id']}-{event['seq']}":
        raise ValueError('invalid event sequence')
    if type(event.get('device_ms')) is not int or event['device_ms'] < 0:
        raise ValueError('invalid device time')
    if event.get('kind') not in KINDS or event.get('phase') not in PHASES:
        raise ValueError('invalid event kind/phase')
    if event.get('experiment_id') not in ('', experiment) or not isinstance(event.get('data'), dict):
        raise ValueError('wrong experiment or data')
    data = event['data']
    if event['kind'] == 'asr.final':
        if event['experiment_id'] != experiment or data.get('final') is not True or data.get('confirmed') is not False or data.get('source') != 'user_reported':
            raise ValueError('invalid voice provenance')
        if not isinstance(data.get('text'), str) or len(data['text'].encode('utf-8')) > 191 or type(data.get('truncated')) is not bool:
            raise ValueError('invalid text snapshot')
        if data.get('usable_for_confirmation') is not (bool(data['text']) and not data['truncated']):
            raise ValueError('invalid completeness')
        stamp(event.get('received_at'))

class Camera:
    """Single owner, latest JPEG in RAM. No continuous recording or face analysis."""
    def __init__(self, index=0):
        self.index = index
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.stop = threading.Event()
        self.thread = None
        self.frame = None
        self.error = None
        self.sequence = 0
        self.frame_times = deque(maxlen=150)

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop.clear()
            self.error = None
            self.frame = None
            self.frame_times.clear()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self):
        camera = None
        try:
            import cv2
            camera = cv2.VideoCapture(self.index, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
            if not camera.isOpened():
                raise RuntimeError('相机打不开，请关闭其他占用相机的软件，并检查权限。')
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            camera.set(cv2.CAP_PROP_FPS, 30)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while not self.stop.is_set():
                started = time.monotonic()
                ok, image = camera.read()
                wall, mono = now(), time.monotonic()
                if not ok:
                    raise RuntimeError('相机没有返回画面。')
                ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 88])
                if not ok:
                    raise RuntimeError('照片编码失败。')
                with self.lock:
                    self.frame = (encoded.tobytes(), wall, mono)
                    self.sequence += 1
                    self.frame_times.append(mono)
                    self.changed.notify_all()
                # Bound encode/CPU use at 30fps; camera.read normally sets the pace.
                self.stop.wait(max(0, 1 / 30 - (time.monotonic() - started)))
        except Exception:
            with self.lock:
                self.error = '相机不可用：请检查占用、权限或安装 OpenCV。'
                self.frame = None
                self.changed.notify_all()
        finally:
            if camera is not None:
                camera.release()

    def snapshot(self):
        with self.lock:
            if not self.frame or self.stop.is_set() or time.monotonic() - self.frame[2] > 2:
                raise RuntimeError('没有新鲜画面；请开启相机并确认取景。')
            return self.frame[0], self.frame[1]

    def status(self):
        with self.lock:
            ready = bool(self.frame and not self.stop.is_set() and time.monotonic() - self.frame[2] <= 2)
            recent = [value for value in self.frame_times if time.monotonic() - value < 5]
            fps = (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) > 1 and recent[-1] > recent[0] else 0
            return {'ready': ready, 'running': bool(self.thread and self.thread.is_alive()), 'error': self.error,
                    'capture_fps': round(fps, 1), 'frame_sequence': self.sequence}

    def wait_frame(self, previous, timeout=2):
        with self.changed:
            self.changed.wait_for(lambda: self.sequence != previous or self.stop.is_set() or self.error, timeout)
            if self.stop.is_set() or self.error or not self.frame or self.sequence == previous:
                return None
            return self.sequence, self.frame[0]

    def close(self):
        self.stop.set()
        with self.changed:
            self.changed.notify_all()
        if self.thread:
            self.thread.join(3)
        with self.lock:
            self.frame = None

class Notes:
    def __init__(self, root, experiment, camera):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'photos').mkdir(exist_ok=True)
        self.path = self.root / 'notes.sqlite3'
        self.experiment, self.camera = experiment, camera
        self.lock = threading.RLock()
        self.last_event = None
        self.last_voice = None
        self.phase = None
        self.bridge = None
        self.mode_command = None
        self.mode_ack = False
        self.notice = None
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, hash TEXT NOT NULL, outcome TEXT NOT NULL);'
                             'CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, experiment TEXT NOT NULL, body TEXT NOT NULL);')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, event):
        validate(event, self.experiment)
        digest = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        eid, data = event['event_id'], event['data']
        with self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT hash FROM receipts WHERE id=?', (eid,)).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError('event identity conflict')
                return {'event_id': eid, 'status': 'duplicate'}
            outcome = 'ignored'
            if event['experiment_id'] == self.experiment:
                self.last_event = now()
                self.phase = event['phase']
            if self.mode_command and event['kind'] == 'device.status' and data.get('command_id') == self.mode_command['command_id'] and data.get('status') == 'mode_set' and event['phase'] == 'record':
                self.mode_ack = True
            if event['kind'] == 'asr.final':
                self.last_voice = now()
                text = note_text(data['text'])
                if text:
                    outcome = 'rejected_incomplete'
                    if data['usable_for_confirmation'] and event['phase'] == 'record':
                        age = time.time() - stamp(event['received_at'])
                        outcome = 'rejected_stale' if not -1 <= age <= 5 else 'note_created'
                        if outcome == 'note_created':
                            note = {'id': 'n_' + uuid.uuid4().hex, 'event_id': eid, 'experiment_id': self.experiment,
                                    'text': text, 'raw_text': data['text'], 'source': 'user_reported',
                                    'confirmed': False, 'created_at': now(), 'speech_received_at': event['received_at'],
                                    'device_event_at_estimated': event.get('occurred_at_estimated'),
                                    'clock_uncertainty_ms': event.get('clock_uncertainty_ms'), 'photo': None,
                                    'photo_received_at': None, 'capture_error': None,
                                    'timing': 'host frame reception near final ASR receipt; not speech onset or sensor exposure'}
                            try:
                                image, captured_at = self.camera.snapshot()
                                name = hashlib.sha256(eid.encode()).hexdigest() + '.jpg'
                                path = self.root / 'photos' / name
                                temp = path.with_suffix('.part')
                                temp.write_bytes(image)
                                temp.replace(path)
                                note.update(photo=name, photo_received_at=captured_at,
                                            photo_sha256=hashlib.sha256(image).hexdigest(),
                                            photo_offset_ms=round((stamp(captured_at)-stamp(event['received_at']))*1000))
                            except Exception:
                                note['capture_error'] = '拍照失败，这条记录尚不完整。请先检查相机，再重新说一条新记录。'
                            db.execute('INSERT INTO notes VALUES(?,?,?)', (note['id'], self.experiment, json.dumps(note, ensure_ascii=False)))
                    if outcome in ('rejected_incomplete', 'rejected_stale'):
                        self.notice = {'at': now(), 'text': '这条口述不完整或到达太晚，未拍照。请等设备就绪后重新说一条短记录。'}
            db.execute('INSERT INTO receipts VALUES(?,?,?)', (eid, digest, outcome))
        return {'event_id': eid, 'status': 'accepted', 'outcome': outcome}

    def list(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT body FROM notes WHERE experiment=? ORDER BY rowid DESC', (self.experiment,))]

    def confirm(self, ident, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError('请输入有效记录内容。')
        with self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM notes WHERE id=? AND experiment=?', (ident, self.experiment)).fetchone()
            if not row:
                raise ValueError('记录不存在。')
            note = json.loads(row[0])
            if not note['photo']:
                raise ValueError('缺少照片，不能确认完整图文记录。')
            photo = self.root / 'photos' / note['photo']
            if not photo.is_file() or hashlib.sha256(photo.read_bytes()).hexdigest() != note['photo_sha256']:
                raise ValueError('照片文件缺失或校验不一致，不能确认。')
            if note['confirmed']:
                if note['text'] != text.strip():
                    raise ValueError('已确认记录不可在此覆盖。')
                return note
            note.update(text=text.strip(), confirmed=True, confirmed_at=now(), confirmation_source='explicit_local_page_click')
            db.execute('UPDATE notes SET body=? WHERE id=?', (json.dumps(note, ensure_ascii=False), ident))
            return note

    def commands(self):
        with self.lock:
            if self.mode_ack:
                return []
            if self.mode_command is None:
                self.mode_command = {'schema': 'b.lab.command.v1', 'command_id': 'record_' + uuid.uuid4().hex[:20],
                                     'experiment_id': self.experiment, 'operation': 'mode', 'argument': 'record',
                                     'expires_at_ms': int(time.time()*1000) + 45000}
            return [self.mode_command] if self.mode_command['expires_at_ms'] > time.time()*1000 else []

    def status(self):
        return {'experiment_id': self.experiment, 'camera': self.camera.status(), 'last_device_event': self.last_event,
                'last_voice_event': self.last_voice, 'device_phase': self.phase, 'record_mode_ack': self.mode_ack,
                'notice': self.notice,
                'bridge_running': self.bridge is not None and self.bridge.poll() is None}

def make_server(notes, port, vision=None):
    vision = vision or Vision(notes.root / 'vision-config.json')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            origin = self.headers.get('Origin')
            return self.headers.get('Host') in allowed and (not origin or origin in {'http://' + host for host in allowed}) and self.headers.get('Sec-Fetch-Site') != 'cross-site'

        def reply(self, code, value, kind='application/json; charset=utf-8'):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {'error': '仅允许本机页面访问。'})
            url = urlsplit(self.path)
            if url.path in ('/', '/app.js', '/style.css'):
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[url.path]
                kind = {'/': 'text/html', '/app.js': 'text/javascript', '/style.css': 'text/css'}[url.path]
                return self.reply(200, (HERE / name).read_bytes(), kind + '; charset=utf-8')
            if url.path == '/api/state':
                return self.reply(200, {'status': notes.status(), 'notes': notes.list(), 'vision': vision.status()})
            if url.path == '/api/preview':
                try:
                    return self.reply(200, notes.camera.snapshot()[0], 'image/jpeg')
                except RuntimeError:
                    return self.reply(503, {'error': '暂无画面。'})
            if url.path == '/api/stream':
                if not notes.camera.status()['ready']:
                    return self.reply(503, {'error': '相机尚未就绪。'})
                self.send_response(200)
                self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                previous = -1
                try:
                    while True:
                        frame = notes.camera.wait_frame(previous)
                        if frame is None:
                            break
                        previous, image = frame
                        header = f'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(image)}\r\nX-Frame-Sequence: {previous}\r\n\r\n'.encode('ascii')
                        self.wfile.write(header + image + b'\r\n')
                        self.wfile.flush()
                except (ConnectionError, OSError):
                    pass
                self.close_connection = True
                return
            if url.path == '/api/lab/device-commands':
                if parse_qs(url.query).get('experiment_id') != [notes.experiment]:
                    return self.reply(400, {'error': 'wrong experiment'})
                return self.reply(200, {'commands': notes.commands()})
            match = re.fullmatch(r'/photos/([a-f0-9]{64}\.jpg)', url.path)
            if match:
                path = notes.root / 'photos' / match[1]
                if path.is_file():
                    return self.reply(200, path.read_bytes(), 'image/jpeg')
            self.reply(404, {'error': '未找到。'})

        def do_POST(self):
            if not self.allowed():
                return self.reply(403, {'error': '仅允许本机页面访问。'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': '需要 JSON。'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16384:
                    raise ValueError('invalid body length')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('invalid body')
                if self.path == '/api/lab/device-events':
                    return self.reply(200, notes.ingest(body))
                if self.path == '/api/camera/start':
                    notes.camera.start()
                    return self.reply(200, {'status': 'starting'})
                if self.path == '/api/camera/stop':
                    notes.camera.close()
                    return self.reply(200, {'status': 'stopped'})
                if self.path == '/api/vision/ask':
                    if body.get('upload_confirmed') is not True:
                        raise VisionError('请明确同意发送本次照片。', 400)
                    question = body.get('question')
                    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
                        raise VisionError('请输入不超过 2000 字的问题。', 400)
                    vision.config()  # No camera capture if the provider is not configured.
                    ident = body.get('note_id')
                    if ident is not None:
                        note = next((item for item in notes.list() if item['id'] == ident), None)
                        if not note or not note['photo']:
                            raise VisionError('这条记录没有可用照片。', 400)
                        path = notes.root / 'photos' / note['photo']
                        if not path.is_file():
                            raise VisionError('照片文件缺失。', 400)
                        image = path.read_bytes()
                        if hashlib.sha256(image).hexdigest() != note['photo_sha256']:
                            raise VisionError('照片校验不一致，已停止发送。', 400)
                        captured_at = note['photo_received_at']
                        question = '用户口述（本人报告）：' + note['text'] + '\n用户问题：' + question
                    else:
                        try:
                            image, captured_at = notes.camera.snapshot()
                        except RuntimeError:
                            raise VisionError('没有新鲜画面，请先开启摄像头。', 400) from None
                    result = vision.ask(image, question)
                    result.update(note_id=ident, photo_received_at=captured_at)
                    return self.reply(200, result)
                if self.path == '/api/confirm':
                    if body.get('user_confirmed') is not True:
                        raise ValueError('需要明确确认。')
                    return self.reply(200, notes.confirm(body.get('id'), body.get('text')))
                return self.reply(404, {'error': '未找到。'})
            except VisionError as exc:
                return self.reply(exc.status, {'error': str(exc)})
            except (ValueError, TypeError, KeyError):
                return self.reply(400, {'error': '请求无效；请检查记录状态与内容。'})
            except Exception:
                return self.reply(500, {'error': '本机存储失败，未确认保存成功。'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--camera-index', type=int, default=0)
    parser.add_argument('--data-dir', type=Path, default=HERE / '.local')
    parser.add_argument('--bridge-source', type=Path)
    parser.add_argument('--serial-port', default='COM7')
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    session = args.data_dir / 'session.json'
    if session.exists():
        experiment = json.loads(session.read_text(encoding='utf-8'))['experiment_id']
    else:
        experiment = 'photo_' + uuid.uuid4().hex[:20]
        session.write_text(json.dumps({'experiment_id': experiment}), encoding='utf-8')
    if not ID.fullmatch(experiment):
        parser.error('invalid local session')
    if args.bridge_source and not args.bridge_source.is_file():
        parser.error('bridge source missing; use reviewed B b/lab/bridge.py')
    camera = Camera(args.camera_index)
    notes = Notes(args.data_dir, experiment, camera)
    server = make_server(notes, args.port)
    if args.bridge_source:
        notes.bridge = subprocess.Popen([sys.executable, str(args.bridge_source.resolve()), '--port', args.serial_port,
            '--experiment-id', experiment, '--service', f'http://127.0.0.1:{server.server_port}',
            '--database', str(args.data_dir.resolve() / 'bridge.sqlite3')], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    print(f'Open http://127.0.0.1:{server.server_port} (local notes; enable camera on page).', flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        camera.close()
        if notes.bridge and notes.bridge.poll() is None:
            notes.bridge.terminate()
            notes.bridge.wait(5)

if __name__ == '__main__':
    main()
