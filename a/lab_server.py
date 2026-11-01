"""A workspace using C's camera, device receipts and canonical SQLite records.

No serial port, camera or model request starts merely by opening this service.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import sys
import threading
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
CAPTURE = HERE.parent / 'c' / 'voice-camera-notes'
sys.path.insert(0, str(CAPTURE))
from app import Camera, ID, Notes, make_server, now, stamp
from lab import Lab
from decimal import Decimal, InvalidOperation

DEFAULT_EXPERIMENT = 'exp_a_20261101_01'
REVIEW_KEYS = ('issue', 'hypothesis', 'next_step', 'conclusion')
FIELDS = ('point', 'quantity', 'value', 'unit', 'conditions', 'retest_of')


class Conflict(ValueError):
    pass


def text(value, label, maximum, required=True):
    if not isinstance(value, str) or len(value.strip()) > maximum or (required and not value.strip()):
        raise ValueError('请检查' + label + '。')
    return value.strip()


def identity(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('实验或事件编号无效。')
    return value


def fields(body):
    result = {key: text(body.get(key, ''), label, maximum, key != 'retest_of')
              for key, label, maximum in [('point', '测量点', 100), ('quantity', '物理量', 60),
                  ('value', '数值', 60), ('unit', '单位', 30), ('conditions', '测量条件', 500),
                  ('retest_of', '复测关联', 64)]}
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', result['value']):
        raise ValueError('数值须为有限数字，单位请单独填写。')
    try:
        value = Decimal(result['value'])
        if not value.is_finite() or value.copy_abs() > Decimal('1e12'):
            raise ValueError('数值超出本轮记录范围。')
    except InvalidOperation:
        raise ValueError('数值无效。') from None
    return result


def markdown_text(value):
    return re.sub(r'([\\`*_{}\[\]()<>#!|~])', r'\\\1', str(value)).replace('\n', '  \n')


class Workspace:
    def __init__(self, notes, lab):
        self.notes, self.lab = notes, lab
        with notes.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS a_experiments(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS a_operations(id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT NOT NULL);
            ''')
            self.ensure(db, notes.experiment)
            # Adopt C experiments already present in this exact database.
            for table in ('notes', 'demo_measurements', 'demo_media', 'demo_analyses'):
                for row in db.execute(f'SELECT DISTINCT experiment FROM {table}').fetchall():
                    self.ensure(db, row[0])

    def ensure(self, db, ident, name=None, background=''):
        identity(ident)
        row = db.execute('SELECT body FROM a_experiments WHERE id=?', (ident,)).fetchone()
        if row:
            return json.loads(row[0])
        item = dict(id=ident, name=name or 'A 联调实验（待录入）', background=background,
                    created_at=now(), review={key: '' for key in REVIEW_KEYS}, revision=0)
        self.save_experiment(db, item)
        return item

    def save_experiment(self, db, item):
        db.execute('INSERT OR REPLACE INTO a_experiments VALUES(?,?)',
                   (item['id'], json.dumps(item, ensure_ascii=False)))

    def experiment(self, db, ident):
        row = db.execute('SELECT body FROM a_experiments WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('实验不存在，请刷新页面。')
        return json.loads(row[0])

    def rows(self, db, table, ident):
        return [json.loads(row[0]) for row in db.execute(
            f'SELECT body FROM {table} WHERE experiment=? ORDER BY rowid', (ident,))]

    def state(self):
        with self.notes.lock, self.notes.db() as db:
            experiments = []
            for row in db.execute('SELECT body FROM a_experiments ORDER BY rowid'):
                item = json.loads(row[0])
                item['measurements'] = self.rows(db, 'demo_measurements', item['id'])
                item['notes'] = self.rows(db, 'notes', item['id'])
                item['analyses'] = self.rows(db, 'demo_analyses', item['id'])
                experiments.append(item)
            return dict(version=2, active_id=self.notes.experiment, experiments=experiments,
                        status=self.notes.status(), storage='server-sqlite',
                        voice_acceptance='真人开发板口述仍待验收')

    def measurement(self, db, ident):
        row = db.execute('SELECT body FROM demo_measurements WHERE id=? AND experiment=?',
                         (ident, self.notes.experiment)).fetchone()
        if not row:
            raise ValueError('测量不属于当前实验。')
        return json.loads(row[0])

    def save_measurement(self, db, item):
        db.execute('INSERT OR REPLACE INTO demo_measurements VALUES(?,?,?)',
                   (item['id'], self.notes.experiment, json.dumps(item, ensure_ascii=False)))

    def check_retest(self, db, parent, ident=None):
        if not parent:
            return
        item = self.measurement(db, parent)
        if parent == ident or not item.get('confirmed') or item.get('retracted_at'):
            raise ValueError('复测只能关联本实验已确认且未撤销的测量。')

    def switch(self, target):
        if target == self.notes.experiment:
            return
        if self.notes.last_event or (self.notes.bridge and self.notes.bridge.poll() is None):
            raise Conflict('设备已绑定本实验。请停止桥接后重启服务选择实验，避免口述串入其他实验。')
        session = self.notes.root / 'session.json'
        temporary = session.with_suffix('.json.tmp')
        temporary.write_text(json.dumps({'experiment_id': target}), encoding='utf-8')
        temporary.replace(session)
        self.notes.experiment = target
        self.notes.mode_command = None
        self.notes.mode_ack = False
        self.notes.phase = None
        self.lab.context = None

    def mutate(self, action, body):
        if action in ('create', 'select') and 'expected_active_id' not in body:
            raise ValueError('缺少当前实验编号，请刷新后重试。')
        request_id = identity(body.get('request_id'))
        signature = hashlib.sha256(json.dumps([action, body], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.notes.lock:
            with self.notes.db() as db:
                db.execute('BEGIN IMMEDIATE')
                receipt = db.execute('SELECT digest,result FROM a_operations WHERE id=?', (request_id,)).fetchone()
                if receipt:
                    if receipt[0] != signature:
                        raise Conflict('同一请求编号的内容发生变化，已拒绝覆盖。')
                    result = json.loads(receipt[1])
                else:
                    if body.get('expected_active_id', body.get('experiment_id')) != self.notes.experiment:
                        raise Conflict('当前实验已经变化。输入已保留，请刷新后核对。')
                    if action not in ('select', 'create') and body.get('experiment_id') != self.notes.experiment:
                        raise Conflict('请求不属于当前实验，未写入记录。')
                    result = self._mutate(db, action, body)
                    db.execute('INSERT INTO a_operations VALUES(?,?,?)',
                               (request_id, signature, json.dumps(result, ensure_ascii=False)))
            # Commit metadata before changing the persisted session binding.
            # If the atomic file replacement fails, keep the old binding and let
            # the same request retry selection without creating another experiment.
            if action in ('create', 'select'):
                if self.notes.experiment not in (body['expected_active_id'], result['id']):
                    raise Conflict('其他页面已切换实验，请刷新后核对。')
                self.switch(result['id'])
            return dict(result=result, **({'deduplicated': True} if receipt else {}))

    def _mutate(self, db, action, body):
        if action == 'create':
            name = text(body.get('name'), '实验名称', 100)
            background = text(body.get('background', ''), '实验背景', 2000, False)
            ident = 'exp_' + uuid.uuid4().hex
            if self.notes.last_event or (self.notes.bridge and self.notes.bridge.poll() is None):
                raise Conflict('设备已绑定当前实验，请停止桥接并重启服务后再新建实验。')
            item = self.ensure(db, ident, name, background)
            return item
        if action == 'select':
            item = self.experiment(db, identity(body.get('experiment_id')))
            return item
        experiment = self.experiment(db, self.notes.experiment)
        if action == 'draft':
            values = fields(body)
            self.check_retest(db, values['retest_of'])
            item = dict(id='m_' + uuid.uuid4().hex, event_id=body['request_id'],
                        experiment_id=self.notes.experiment, source='manual', input_channel='local_page',
                        raw_text='', created_at=now(), confirmed=False, revision=0,
                        needs_review=True, missing=[], evidence=None, **values)
            self.save_measurement(db, item)
            return item
        if action in ('confirm', 'retract'):
            item = self.measurement(db, identity(body.get('id')))
            if action == 'confirm':
                if body.get('user_confirmed') is not True:
                    raise ValueError('需要本人明确点击确认。')
                values = fields(body)
                self.check_retest(db, values['retest_of'], item['id'])
                if item.get('confirmed'):
                    if any(item.get(key, '') != value for key, value in values.items()):
                        raise Conflict('已确认测量不能覆盖，请另记一条更正或复测。')
                    return item
                if body.get('revision') != item.get('revision', 0):
                    raise Conflict('这条草稿已被其他页面修改，请刷新核对。')
                # A single confirmation also confirms a linked C photo note.
                for note in self.rows(db, 'notes', self.notes.experiment):
                    if note['event_id'] != item['event_id']:
                        continue
                    if not note.get('photo'):
                        raise ValueError('关联照片缺失，无法确认完整图文记录。请重新记录并核对取景。')
                    path = self.notes.root / 'photos' / note['photo']
                    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != note['photo_sha256']:
                        raise ValueError('关联照片缺失或发生变化，已停止确认。')
                    note.update(confirmed=True, confirmed_at=now(), confirmation_source='explicit_a_page_click')
                    db.execute('UPDATE notes SET body=? WHERE id=?', (json.dumps(note, ensure_ascii=False), note['id']))
                item.update(**values, confirmed=True, confirmed_at=now(), needs_review=False, missing=[],
                            confirmation_source='explicit_a_page_click', revision=item.get('revision', 0) + 1)
            else:
                if not item.get('confirmed') or type(body.get('retracted')) is not bool:
                    raise ValueError('只能撤销或恢复已确认测量。')
                if body.get('revision') != item.get('revision', 0):
                    raise Conflict('记录状态已变化，请刷新后重试。')
                item.update(retracted_at=now() if body['retracted'] else None, revision=item.get('revision', 0) + 1)
            self.save_measurement(db, item)
            return item
        if action == 'review':
            if body.get('revision') != experiment.get('revision', 0):
                raise Conflict('复盘已被其他页面修改，输入已保留，请刷新核对。')
            review = body.get('review')
            if not isinstance(review, dict):
                raise ValueError('复盘内容无效。')
            experiment.update(review={**{key: text(review.get(key, ''), '复盘', 2000, False) for key in REVIEW_KEYS},
                                      'source': 'manual', 'updated_at': now()}, revision=experiment['revision'] + 1)
            self.save_experiment(db, experiment)
            return experiment
        if action == 'import':
            return self.import_browser(db, body.get('data'))
        raise ValueError('未知操作。')

    def import_browser(self, db, data):
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('experiments'), list) or len(data['experiments']) > 200:
            raise ValueError('旧浏览器记录格式无效，原数据未修改。')
        count = 0
        for old in data['experiments']:
            ident = identity(old.get('id'))
            if db.execute('SELECT 1 FROM a_experiments WHERE id=?', (ident,)).fetchone():
                raise Conflict('实验编号已存在，未覆盖任何记录。')
            name = text(old.get('name'), '实验名称', 100)
            background = text(old.get('background'), '实验背景', 2000, False)
            stamp(old.get('created_at'))
            review = old.get('review')
            records = old.get('measurements')
            if not isinstance(review, dict) or not isinstance(records, list) or len(records) > 10000:
                raise ValueError('旧实验内容不完整。')
            item = self.ensure(db, ident, name, background)
            item.update(created_at=old['created_at'], imported_at=now(),
                        review={key: text(review.get(key), '复盘', 2000, False) for key in REVIEW_KEYS})
            self.save_experiment(db, item)
            known = set()
            for record in records:
                mid = identity(record.get('id'))
                values = fields(record)
                if values['retest_of'] and values['retest_of'] not in known:
                    raise ValueError('旧记录的复测关联无效。')
                if record.get('confirmed') is not True or record.get('source') != 'manual':
                    raise ValueError('只导入已确认且标明手动来源的旧测量。')
                stamp(record.get('recorded_at'))
                if record.get('retracted_at'):
                    stamp(record['retracted_at'])
                if db.execute('SELECT 1 FROM demo_measurements WHERE id=?', (mid,)).fetchone():
                    raise Conflict('测量编号已存在，未覆盖记录。')
                payload = dict(id=mid, experiment_id=ident, event_id='import_' + hashlib.sha256(mid.encode()).hexdigest()[:32],
                               source='manual', input_channel='browser_import', raw_text='', confirmed=True,
                               confirmed_at=record['recorded_at'], created_at=record['recorded_at'],
                               confirmation_source='historical_browser_confirmation', imported_at=now(),
                               revision=0, retracted_at=record.get('retracted_at'), evidence=None, **values)
                db.execute('INSERT INTO demo_measurements VALUES(?,?,?)', (mid, ident, json.dumps(payload, ensure_ascii=False)))
                known.add(mid)
                count += 1
        return {'imported_experiments': len(data['experiments']), 'imported_measurements': count}

    def export(self, ident):
        with self.notes.lock, self.notes.db() as db:
            experiment = self.experiment(db, identity(ident))
            measurements = self.rows(db, 'demo_measurements', ident)
            notes = self.rows(db, 'notes', ident)
            analyses = self.rows(db, 'demo_analyses', ident)
        esc = markdown_text
        lines = ['# ' + esc(experiment['name']), '', '实验编号：' + ident, '',
                 esc(experiment['background']), '', '## 已确认测量', '',
                 '口述和手动输入均非仪器自动采样；确认时间不是测量发生时间。']
        confirmed = [item for item in measurements if item.get('confirmed')]
        labels = {item['id']: f'M{i + 1:02}' for i, item in enumerate(confirmed)}
        for item in confirmed:
            lines += ['', f"### {labels[item['id']]} · {esc(item['point'])}" + ('（已撤销）' if item.get('retracted_at') else ''),
                      f"- {esc(item['quantity'])}：{esc(item['value'])} {esc(item['unit'])}",
                      '- 条件：' + esc(item['conditions']), '- 来源：' + esc(item['source']),
                      '- 测量编号：' + item['id'], '- 事件编号：' + esc(item.get('event_id', '')),
                      '- 确认时间：' + esc(item.get('confirmed_at', ''))]
            if item.get('raw_text'):
                lines.append('- 原始口述：' + esc(item['raw_text']))
            if item.get('speech_events'):
                lines.append('- 转写事件：' + ', '.join(esc(event) for event in item['speech_events']))
            if item.get('retest_of'):
                lines.append('- 复测关联：' + esc(item['retest_of']))
            evidence = item.get('evidence')
            if evidence:
                lines.append('- 视频证据：' + esc(evidence['media_id']) + ' @ 导入片段 ' + str(evidence['seconds']) + 's / 来源原片 ' + str(evidence.get('source_seconds', evidence['seconds'])) + 's')
            for note in notes:
                if note['event_id'] == item.get('event_id') and note.get('photo'):
                    lines.append('- 关联照片：' + esc(note['photo']) + '；SHA256：' + esc(note.get('photo_sha256', '')))
        for key, label in zip(REVIEW_KEYS, ('观察到的问题', '候选原因（人工推断）', '下一项验证', '复测后的发现')):
            lines += ['', '## ' + label, '', esc(experiment['review'].get(key, '')) or '未填写']
        lines += ['', '## AI 分析（待核对）']
        for analysis in analyses:
            lines += ['', '### ' + esc(analysis['mode']), esc(analysis['answer']),
                      '证据：' + ', '.join(esc(ref['media_id']) + ' @ 导入片段 ' + str(ref['seconds']) + 's / 来源原片 ' + str(ref.get('source_seconds', ref['seconds'])) + 's' for ref in analysis['evidence'])]
        lines += ['', '未确认草稿不作为正式测量导出。语音、模型和硬件验收状态需另行核实。']
        return '\n'.join(lines)


def create_server(root, port=8765, experiment_id=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    session = root / 'session.json'
    if session.exists():
        ident = identity(json.loads(session.read_text(encoding='utf-8-sig'))['experiment_id'])
        if experiment_id and experiment_id != ident:
            raise ValueError('数据目录已有其他实验，请沿用原编号或使用新的数据目录。')
    else:
        ident = identity(experiment_id or DEFAULT_EXPERIMENT)
        temporary = session.with_suffix('.json.tmp')
        temporary.write_text(json.dumps({'experiment_id': ident}), encoding='utf-8')
        temporary.replace(session)
    notes = Notes(root, ident, Camera())
    lab = Lab(notes)
    workspace = Workspace(notes, lab)
    server = make_server(notes, port, lab=lab)
    base = server.RequestHandlerClass
    assets = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'),
              '/lab.js': ('lab.js', 'text/javascript'), '/lab-store.js': ('lab-store.js', 'text/javascript'),
              '/lab.css': ('lab.css', 'text/css')}
    actions = {'/api/workspace/experiments': 'create', '/api/workspace/select': 'select',
               '/api/workspace/measurements/draft': 'draft', '/api/workspace/measurements/confirm': 'confirm',
               '/api/workspace/measurements/retract': 'retract', '/api/workspace/review': 'review',
               '/api/workspace/import': 'import'}

    class Handler(base):
        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {'error': '仅允许本机页面访问。'})
            path = urlsplit(self.path).path
            if path in assets:
                name, kind = assets[path]
                return self.reply(200, (HERE / name).read_bytes(), kind + '; charset=utf-8')
            if path == '/capture':
                html = (CAPTURE / 'index.html').read_text(encoding='utf-8')
                html = html.replace('<nav class="demo-nav">', '<p><a href="/">返回实验工作区</a> · 当前实验：<span id="workspaceExperiment"></span></p><nav class="demo-nav">')
                return self.reply(200, html.encode('utf-8'), 'text/html; charset=utf-8')
            if path == '/api/health':
                return self.reply(200, dict(ok=True, service='a-unified-workspace', storage='server-sqlite',
                    experiment_id=notes.experiment, device_events_received=bool(notes.last_event),
                    voice_verified=False, camera_ready=notes.camera.status()['ready']))
            if path == '/api/workspace/state':
                return self.reply(200, workspace.state())
            if path in ('/api/workspace/export', '/api/demo/export'):
                try:
                    ident = notes.experiment if path == '/api/demo/export' else parse_qs(urlsplit(self.path).query).get('experiment_id', [''])[0]
                    return self.reply(200, workspace.export(ident).encode('utf-8'), 'text/markdown; charset=utf-8')
                except ValueError as error:
                    return self.reply(400, {'error': str(error)})
            if path.startswith('/api/demo/'):
                with notes.lock:
                    return super().do_GET()
            return super().do_GET()

        def do_POST(self):
            action = actions.get(self.path)
            capture_confirmation = self.path == '/api/demo/measurements/confirm'
            if capture_confirmation:
                action = 'confirm'
            if not action:
                # Bind C's entire operation to the active experiment until it finishes.
                with notes.lock:
                    return super().do_POST()
            if not self.allowed():
                return self.reply(403, {'error': '仅允许本机页面访问。'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'error': '需要 JSON。'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2 * 1024 * 1024:
                    raise ValueError('请求过大或为空。')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('请求格式无效。')
                if capture_confirmation:
                    with notes.lock, notes.db() as db:
                        item = workspace.measurement(db, body.get('id'))
                        original = body
                        body = dict(experiment_id=notes.experiment, request_id='capture_' + uuid.uuid4().hex,
                                    revision=item.get('revision', 0),
                                    **{key: item.get(key, '') for key in FIELDS})
                        body.update({key: original[key] for key in ('id', 'point', 'value', 'unit', 'conditions', 'user_confirmed') if key in original})
                        if item['source'] == 'user_reported':
                            body['quantity'] = {'V':'voltage', 'mV':'voltage', 'A':'current', 'mA':'current', 'Ω':'resistance', 'kΩ':'resistance'}.get(body['unit'], body['quantity'])
                        result = workspace.mutate(action, body)['result']
                    return self.reply(200, result)
                return self.reply(200, workspace.mutate(action, body))
            except Conflict as error:
                return self.reply(409, {'error': str(error)})
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                message = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else '请求字段无效。'
                return self.reply(400, {'error': message})
            except (OSError, sqlite3.Error):
                return self.reply(500, {'error': '保存失败，请保留输入，检查本机数据目录后重试。'})

    server.RequestHandlerClass = Handler
    server.workspace = workspace
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=CAPTURE / '.local')
    parser.add_argument('--experiment-id')
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    server = create_server(args.data_dir, args.port, args.experiment_id)
    print(f'Open http://127.0.0.1:{server.server_port}/ ; experiment_id={server.workspace.notes.experiment}', flush=True)
    if args.open_browser:
        # Binding succeeded before the browser opens, so an occupied port never
        # silently opens an unrelated old service.
        threading.Timer(.4, lambda: webbrowser.open(f'http://127.0.0.1:{server.server_port}/')).start()
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.workspace.notes.camera.close()
        server.server_close()


if __name__ == '__main__':
    main()
