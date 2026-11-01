"""Four-demo state, source-video evidence and confirmed measurements.

Media stays local. Import is a deliberate local browser upload, never a remote
URL fetch. Playback time is source time, not the time a physical action happened.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import uuid

from vision import VisionError


def now():
    return datetime.now(timezone.utc).isoformat()


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('数值或时间范围无效。')
    return float(value)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


UNITS = {'毫伏': ('voltage', 'mV'), '伏特': ('voltage', 'V'), '伏': ('voltage', 'V'),
         'mv': ('voltage', 'mV'), 'v': ('voltage', 'V'),
         '毫安': ('current', 'mA'), '安培': ('current', 'A'), '安': ('current', 'A'),
         'ma': ('current', 'mA'), 'a': ('current', 'A'),
         '千欧': ('resistance', 'kΩ'), '欧姆': ('resistance', 'Ω'), '欧': ('resistance', 'Ω'),
         'kω': ('resistance', 'kΩ'), 'ω': ('resistance', 'Ω')}


def measurement_fields(raw):
    """Deterministic first pass. Missing/ambiguous fields always need a human.

    No model may confirm or invent measurements. Keep literal original text.
    """
    text = raw.strip()
    point = re.search(r'(?i)(?<![A-Za-z0-9])(TP\s*\d+|VCC|GND|LED\s*\d*)(?![A-Za-z0-9])', text)
    if not point:
        point = re.search(r'(?:测量点|测点|位置)[是为：:\s]*([\w\u4e00-\u9fff]{1,16}?)(?=[，,。\s]|电压|电流|电阻|$)', text)
    point = re.sub(r'\s+', '', point.group(1)).upper() if point else ''
    unit_pattern = '|'.join(re.escape(x) for x in sorted(UNITS, key=len, reverse=True))
    values = list(re.finditer(r'(?i)([-+]?\d+(?:[.点]\d+)?)\s*(' + unit_pattern + r')(?![A-Za-z])', text))
    value = unit = quantity = ''
    if len(values) == 1:
        value = values[0].group(1).replace('点', '.')
        quantity, unit = UNITS[values[0].group(2).lower()]
    conditions = next((x for x in ('空载', '带载', '开关闭合', '开关断开', '断电', '通电') if x in text), '')
    missing = [label for label, val in [('测量位置', point), ('数值和单位', value), ('测量条件', conditions)] if not val]
    if len(values) > 1:
        missing.append('存在多组读数，请分别记录或人工核对')
    return dict(point=point, quantity=quantity, value=value, unit=unit, conditions=conditions,
                missing=missing, needs_review=True)


class Lab:
    def __init__(self, notes):
        self.notes = notes
        self.root = notes.root / 'media'
        self.root.mkdir(exist_ok=True)
        self.import_lock = threading.Lock()
        self.context = None
        with notes.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS demo_media(id TEXT PRIMARY KEY, experiment TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS demo_measurements(id TEXT PRIMARY KEY, experiment TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS demo_analyses(id TEXT PRIMARY KEY, experiment TEXT NOT NULL, body TEXT NOT NULL);
            ''')

    def list(self, table):
        if table not in ('demo_media', 'demo_measurements', 'demo_analyses'):
            raise ValueError('invalid table')
        with self.notes.db() as db:
            return [json.loads(row[0]) for row in db.execute(
                f'SELECT body FROM {table} WHERE experiment=? ORDER BY rowid DESC', (self.notes.experiment,))]

    def state(self):
        return {'media': self.list('demo_media'), 'measurements': self.list('demo_measurements'),
                'analyses': self.list('demo_analyses'), 'context': self.context,
                'voice_acceptance': '真人口述验收尚待执行；页面数据不自动证明实物通过'}

    def import_video(self, stream, size, meta):
        if not isinstance(meta, dict):
            raise ValueError('素材信息无效。')
        title = meta.get('title', '').strip()
        source_url = meta.get('source_url', '').strip()
        author = meta.get('author', '').strip()
        if not title or len(title) > 120 or not author or len(author) > 120 or not source_url.startswith('https://') or len(source_url) > 1000:
            raise ValueError('请填写标题、作者和 HTTPS 来源链接。')
        if meta.get('local_use_confirmed') is not True or not 0 < size <= 150 * 1024 * 1024:
            raise ValueError('需要确认素材可用于本次展示；视频上限 150 MB。')
        if not self.import_lock.acquire(blocking=False):
            raise ValueError('已有素材正在导入。')
        ident = 'v_' + uuid.uuid4().hex
        temp = self.root / (ident + '.part')
        try:
            remaining = size
            with temp.open('wb') as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('上传未完成。')
                    output.write(chunk); remaining -= len(chunk)
            import cv2
            cap = cv2.VideoCapture(str(temp))
            try:
                fps = cap.get(cv2.CAP_PROP_FPS)
                count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                ok, frame = cap.read()
                if not cap.isOpened() or not ok or not math.isfinite(fps) or not 0 < fps <= 240 or not 0 < count/fps <= 3600:
                    raise ValueError('视频不能解码或时长超过一小时。')
                duration = count/fps
                height, width = frame.shape[:2]
                if width*height > 3840*2160:
                    raise ValueError('视频分辨率过大，请先导出到 1080p 或 720p。')
            finally:
                cap.release()
            path = self.root / (ident + '.mp4')
            temp.replace(path)
            asset = dict(id=ident, title=title, source_url=source_url, author=author,
                         kind='imported_video', real_footage_claimed=meta.get('real_footage_confirmed') is True,
                         file=path.name, sha256=digest(path),
                         bytes=size, duration_seconds=duration, fps=fps, width=width, height=height,
                         registered_at=now(), local_use_confirmed=True, capture_time=None,
                         verification='导入可解码；素材内容尚需人工核验')
            with self.notes.db() as db:
                db.execute('INSERT INTO demo_media VALUES(?,?,?)', (ident, self.notes.experiment, json.dumps(asset, ensure_ascii=False)))
            return asset
        finally:
            if temp.exists():
                temp.unlink()
            self.import_lock.release()

    def asset(self, ident):
        asset = next((m for m in self.list('demo_media') if m['id'] == ident), None)
        if not asset:
            raise ValueError('素材不存在于当前实验。')
        path = self.root / asset['file']
        if not path.is_file() or path.stat().st_size != asset['bytes'] or digest(path) != asset['sha256']:
            raise ValueError('视频缺失或校验发生变化，已停止使用。')
        return asset, path

    def frame(self, ident, seconds):
        import cv2
        asset, path = self.asset(ident)
        seconds = number(seconds, 0, asset['duration_seconds'])
        cap = cv2.VideoCapture(str(path))
        try:
            # Seek by frame index. Never silently accept a later frame than asked.
            index = min(int(seconds*asset['fps']), round(asset['duration_seconds']*asset['fps'])-1)
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, index):
                raise ValueError('无法定位该视频帧。')
            ok, frame = cap.read()
            decoded_index = round(cap.get(cv2.CAP_PROP_POS_FRAMES))-1
            if not ok or decoded_index < 0 or decoded_index > index:
                raise ValueError('视频未返回请求范围内的画面。')
            height, width = frame.shape[:2]
            if width > 1280:
                frame = cv2.resize(frame, (1280, round(height*1280/width)))
            ok, image = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if not ok:
                raise ValueError('取帧编码失败。')
            image = image.tobytes()
            return image, dict(media_id=ident, seconds=decoded_index/asset['fps'],
                               frame_index=decoded_index, sha256=hashlib.sha256(image).hexdigest(),
                               source='imported_video', source_url=asset['source_url'])
        finally:
            cap.release()

    def set_context(self, body):
        asset, _ = self.asset(body.get('media_id'))
        pos = number(body.get('seconds'), 0, asset['duration_seconds'])
        self.context = dict(media_id=asset['id'], seconds=pos, selected_at=now(),
                            source='user_selected_video_position', source_url=asset['source_url'])
        return self.context

    def voice(self, event, db):
        """Called inside the Notes receipt transaction, after all provenance checks."""
        raw = event['data']['text']
        if not re.match(r'^(?:你好[，,\s]*小灵[，,。\s]*)?(?:请|帮我|请帮我)?[，,\s]*(?:记一下|记录|测量记录)', raw.strip()):
            return
        fields = measurement_fields(raw)
        # Non-measurement notes stay in the existing note path.
        if not fields['point'] and not fields['value'] and not any(x in raw for x in ('电压','电流','电阻','测量','测点')):
            return
        ident = 'm_' + uuid.uuid4().hex
        item = dict(id=ident, event_id=event['event_id'], raw_text=raw, source='user_reported',
                    input_channel='device_asr_final', created_at=now(), confirmed=False,
                    speech_received_at=event['received_at'], evidence=self.context,
                    **fields)
        db.execute('INSERT INTO demo_measurements VALUES(?,?,?)', (ident, self.notes.experiment, json.dumps(item, ensure_ascii=False)))

    def confirm_measurement(self, body):
        if body.get('user_confirmed') is not True:
            raise ValueError('需要本人明确确认。')
        point, conditions = body.get('point'), body.get('conditions')
        unit = body.get('unit')
        reverse = {'V':'voltage','mV':'voltage','A':'current','mA':'current','Ω':'resistance','kΩ':'resistance'}
        if not isinstance(point,str) or not 1 <= len(point.strip()) <= 100 or not isinstance(conditions,str) or not 1 <= len(conditions.strip()) <= 300 or unit not in reverse:
            raise ValueError('请补齐测量位置、单位和条件。')
        try:
            val = Decimal(str(body.get('value')))
            if not val.is_finite() or abs(val) > Decimal('1e12'):
                raise ValueError('数值无效。')
        except InvalidOperation:
            raise ValueError('数值无效。') from None
        with self.notes.lock, self.notes.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM demo_measurements WHERE id=? AND experiment=?', (body.get('id'), self.notes.experiment)).fetchone()
            if not row:
                raise ValueError('测量草稿不存在。')
            item=json.loads(row[0])
            updates=dict(point=point.strip(), quantity=reverse[unit], value=str(val), unit=unit, conditions=conditions.strip())
            if item['confirmed']:
                if any(item[k] != v for k,v in updates.items()):
                    raise ValueError('已确认记录不可覆盖，请重新口述更正。')
                return item
            item.update(**updates, confirmed=True, confirmed_at=now(), needs_review=False, missing=[],
                        confirmation_source='explicit_local_page_click')
            db.execute('UPDATE demo_measurements SET body=? WHERE id=?', (json.dumps(item,ensure_ascii=False),item['id']))
        return item

    def analyze(self, vision, body):
        if body.get('upload_confirmed') is not True:
            raise VisionError('需要明确同意发送本次视频画面。',400)
        mode=body.get('mode')
        if mode not in ('safety','wiring','history'):
            raise ValueError('请选择危险提醒、接线指导或历史排错。')
        question=body.get('question','').strip()
        if not question or len(question)>1500:
            raise ValueError('请输入本次问题。')
        asset,_=self.asset(body.get('media_id'))
        playhead=number(body.get('playhead'),0,asset['duration_seconds'])
        start=number(body.get('start',max(0,playhead-30)),0,playhead)
        count=3 if mode=='history' else 1
        times=sorted(set([start+(playhead-start)*i/(count-1) for i in range(count)] if count>1 else [playhead]))
        images=[]; evidence=[]
        for pos in times:
            image,ref=self.frame(asset['id'],pos)
            images.append(image);evidence.append(ref)
        confirmed=[{k:m[k] for k in ('point','quantity','value','unit','conditions','source')}
                   for m in self.list('demo_measurements') if m['confirmed']]
        task={
            'safety':'检查实拍焊接场景中电源线是否与烙铁金属加热段接触。仅凭视觉判断接触关系，不猜温度。'
                     '未出现目标风险并不等于现场安全。输出 JSON 对象：status 为 risk/clear/unknown，evidence 为可见依据，'
                     'message 为简短提醒，source_seconds 为所引画面时间。证据不足用 unknown。',
            'wiring':'依据可见连接与下述实验资料，解释下一步接线及核对方法。不能看见隐藏孔位或电气导通时明确未知。'
                     '不要宣布接线安全。引用所用画面时间。',
            'history':'结合当前与先前画面、已确认口述，回答本次异常问题。先列观察及原片时间，再列候选原因和一个优先验证步骤。'
                      '操作先后不自动证明因果。不足以定位故障时明确缺证据。'
        }[mode]
        materials=body.get('materials','')
        if not isinstance(materials,str) or len(materials)>4000:
            raise ValueError('资料过长。')
        prompt=task+'\n用户问题：'+question+'\n实验资料（仅背景，非本次观察）：'+materials+'\n已确认口述：'+json.dumps(confirmed[-10:],ensure_ascii=False)
        result=vision.ask_many(images,prompt,[ref['seconds'] for ref in evidence])
        alert=None
        if mode=='safety':
            try:
                text=result['answer'].strip()
                if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
                obj=json.loads(text)
                status=obj.get('status')
                if status not in ('risk','clear','unknown') or not isinstance(obj.get('evidence'),str) or not isinstance(obj.get('message'),str):
                    raise ValueError()
                alert={'status':status,'evidence':obj['evidence'],'message':obj['message']}
            except (ValueError,TypeError,AttributeError):
                alert={'status':'unknown','evidence':'响应未通过结构校验。','message':'无法判断目标风险，请人工核查。'}
        item=dict(id='a_'+uuid.uuid4().hex,mode=mode,question=question,answer=result['answer'],
                  model=result['model'],source='ai_generated',confirmed=False,created_at=now(),
                  media_id=asset['id'],playhead=playhead,evidence=evidence,alert=alert,
                  elapsed_seconds=result.get('elapsed_seconds'),
                  note='视频素材分析；不等于真实现场风险已被及时制止')
        with self.notes.db() as db:
            db.execute('INSERT INTO demo_analyses VALUES(?,?,?)',(item['id'],self.notes.experiment,json.dumps(item,ensure_ascii=False)))
        return item

    def export(self):
        lines=['# 实验演示记录', '', '实验编号：'+self.notes.experiment, '',
               '外部视频时间为原片位置，不是本机实验发生时间。测量为用户口述，AI 分析未经自动确认。', '', '## 已确认测量']
        for item in self.list('demo_measurements'):
            if item['confirmed']:
                lines.append(f"- {item['point']}：{item['value']} {item['unit']}；{item['conditions']}；口述事件 {item['event_id']}")
        lines+=['','## AI 分析（待核对）']
        for item in self.list('demo_analyses'):
            lines+=['',f"### {item['mode']} / {item['created_at']}",item['answer'],
                    '证据：'+', '.join(f"{r['media_id']} @ {r['seconds']:.3f}s" for r in item['evidence'])]
        return '\n'.join(lines)
