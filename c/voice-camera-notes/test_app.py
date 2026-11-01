"""Synthetic boundary tests; these do not count as hardware or camera acceptance."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import request, error
from app import Notes, make_server, note_text, now

class CameraStub:
    def __init__(self):
        self.calls = 0
        self.fail = False
    def snapshot(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError('synthetic camera failure')
        return b'synthetic-not-a-real-photo', now()
    def status(self):
        return {'ready': not self.fail, 'running': True, 'error': None}
    def wait_frame(self, previous, timeout=2):
        return (1,b'synthetic-jpeg-payload') if previous < 1 else None

def event(seq=1, text='记一下，合成测试，刚才换了导线。'):
    return {'schema':'b.lab.v1','event_id':f'bootA-{seq}','boot_id':'bootA','seq':seq,'device_ms':1000,
            'experiment_id':'test_exp','phase':'record','kind':'asr.final','received_at':now(),
            'occurred_at_estimated':None,'clock_uncertainty_ms':None,
            'data':{'text':text,'final':True,'truncated':False,'usable_for_confirmation':True,
                    'confirmed':False,'source':'user_reported'}}

class Tests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.camera=CameraStub()
        self.notes=Notes(self.root,'test_exp',self.camera)
    def tearDown(self):
        self.folder.cleanup()

    def test_trigger_boundary(self):
        for text in ['不要记一下这个','你刚才说记一下了吗','记一下','确认保存','有人说“记一下”','请介绍一下自己']:
            self.assertIsNone(note_text(text), text)
        self.assertEqual(note_text('你好，小灵，请帮我记一下：合成操作'),'合成操作')

    def test_persist_draft_confirm_and_original_provenance(self):
        self.notes.ingest(event())
        draft=self.notes.list()[0]
        self.assertFalse(draft['confirmed'])
        self.assertEqual(draft['source'],'user_reported')
        self.assertEqual(draft['photo_sha256'],hashlib.sha256(b'synthetic-not-a-real-photo').hexdigest())
        self.notes.confirm(draft['id'],'人工纠正后的合成操作记录')
        reopened=Notes(self.root,'test_exp',self.camera)
        saved=reopened.list()[0]
        self.assertTrue(saved['confirmed'])
        self.assertEqual(saved['raw_text'],event()['data']['text'])
        self.assertEqual(saved['confirmation_source'],'explicit_local_page_click')
        self.notes.confirm(draft['id'],saved['text'])
        with self.assertRaises(ValueError):self.notes.confirm(draft['id'],'不可覆盖')

    def test_duplicate_is_idempotent_after_restart_and_conflict_rejected(self):
        original=event();self.notes.ingest(original)
        reopened=Notes(self.root,'test_exp',self.camera)
        self.assertEqual(reopened.ingest(original)['status'],'duplicate')
        self.assertEqual(self.camera.calls,1)
        self.assertEqual(len(reopened.list()),1)
        changed=copy.deepcopy(original);changed['data']['text']='记一下，变更的合成内容'
        with self.assertRaises(ValueError):reopened.ingest(changed)
        self.assertEqual(self.camera.calls,1)

    def test_stale_does_not_take_a_present_photo_for_past_speech(self):
        old=event();old['received_at']=(datetime.now(timezone.utc)-timedelta(seconds=20)).isoformat()
        self.assertEqual(self.notes.ingest(old)['outcome'],'rejected_stale')
        self.assertEqual(self.camera.calls,0)
        self.assertEqual(self.notes.list(),[])
        self.assertEqual(self.notes.ingest(old)['status'],'duplicate')

    def test_wrong_experiment_and_unfinal_source_are_rejected(self):
        for key,value in [('experiment_id','other_exp'),('phase','bad')]:
            bad=event();bad[key]=value
            with self.assertRaises(ValueError):self.notes.ingest(bad)
        for key,value in [('source','agent_generated'),('final',False),('confirmed',True)]:
            bad=event();bad['data'][key]=value
            with self.assertRaises(ValueError):self.notes.ingest(bad)
        self.assertEqual(self.camera.calls,0)

    def test_truncated_and_non_record_are_not_captured(self):
        truncated=event();truncated['data'].update(truncated=True,usable_for_confirmation=False)
        self.notes.ingest(truncated)
        inactive=event(2);inactive['phase']='paused';self.notes.ingest(inactive)
        self.assertEqual(self.camera.calls,0)

    def test_camera_failure_preserves_unconfirmed_text_without_fake_photo(self):
        self.camera.fail=True;self.notes.ingest(event());note=self.notes.list()[0]
        self.assertIsNone(note['photo'])
        self.assertFalse(note['confirmed'])
        self.assertIsNotNone(note['capture_error'])
        with self.assertRaises(ValueError):self.notes.confirm(note['id'],note['text'])

    def test_untriggered_speech_not_stored(self):
        self.notes.ingest(event(text='不属于记录的私人口述'))
        self.assertEqual(self.notes.list(),[])
        with self.notes.db() as db:
            row=db.execute('SELECT * FROM receipts').fetchone()
        self.assertNotIn('私人口述',str(row))
        self.assertEqual(self.camera.calls,0)

    def test_tts_cannot_trigger_capture_and_does_not_store_text(self):
        reply=event();reply['kind']='tts.final';reply['data']['source']='agent_generated'
        self.notes.ingest(reply)
        self.assertEqual(self.camera.calls,0)

    def test_missing_or_changed_photo_cannot_be_confirmed(self):
        self.notes.ingest(event());note=self.notes.list()[0]
        (self.root/'photos'/note['photo']).write_bytes(b'changed')
        with self.assertRaises(ValueError):self.notes.confirm(note['id'],note['text'])
        (self.root/'photos'/note['photo']).unlink()
        with self.assertRaises(ValueError):self.notes.confirm(note['id'],note['text'])

    def test_http_durable_ack_access_and_explicit_confirmation(self):
        server=make_server(self.notes,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        opener=request.build_opener(request.ProxyHandler({}))
        def post(path,body,headers=None):
            req=request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
            return opener.open(req,timeout=2)
        try:
            with post('/api/lab/device-events',event()) as result:
                self.assertEqual(json.load(result)['status'],'accepted')
            self.assertEqual(len(Notes(self.root,'test_exp',self.camera).list()),1)
            note=self.notes.list()[0]
            with self.assertRaises(error.HTTPError) as denied:post('/api/confirm',{'id':note['id'],'text':note['text'],'user_confirmed':False})
            self.assertEqual(denied.exception.code,400)
            with self.assertRaises(error.HTTPError) as denied:post('/api/camera/start',{}, {'Origin':'https://untrusted.example'})
            self.assertEqual(denied.exception.code,403)
            req=request.Request(base+'/api/state',headers={'Host':'untrusted.example'})
            with self.assertRaises(error.HTTPError) as denied:opener.open(req)
            self.assertEqual(denied.exception.code,403)
            with self.assertRaises(error.HTTPError) as denied:opener.open(base+'/photos/../../notes.sqlite3')
            self.assertEqual(denied.exception.code,404)
        finally:
            server.shutdown();server.server_close();thread.join(2)

    def test_record_mode_requires_ack(self):
        command=self.notes.commands()[0]
        self.assertFalse(self.notes.status()['record_mode_ack'])
        ack=event();ack['kind']='device.status';ack['data']={'command_id':command['command_id'],'status':'mode_set'}
        self.notes.ingest(ack)
        self.assertTrue(self.notes.status()['record_mode_ack'])
        self.assertEqual(self.notes.commands(),[])

    def test_preview_stream_framing_has_one_fresh_frame_without_duplicate_loop(self):
        server=make_server(self.notes,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        opener=request.build_opener(request.ProxyHandler({}))
        try:
            with opener.open(f'http://127.0.0.1:{server.server_port}/api/stream',timeout=2) as response:
                self.assertIn('multipart/x-mixed-replace',response.headers['Content-Type'])
                body=response.read()
            self.assertEqual(body.count(b'--frame'),1)
            self.assertIn(b'Content-Length: 22\r\n',body)
            self.assertIn(b'X-Frame-Sequence: 1\r\n',body)
            self.assertTrue(body.endswith(b'synthetic-jpeg-payload\r\n'))
        finally:
            server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':unittest.main()
