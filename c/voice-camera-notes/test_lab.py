"""Synthetic videos/ASR/provider only; these are not real-operation acceptance."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import request, error, parse
from unittest.mock import Mock
import cv2
import numpy as np
from app import Notes, make_server
from lab import Lab, measurement_fields
from test_app import CameraStub, event


class Tests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name)
        self.notes=Notes(self.root,'test_exp',CameraStub());self.lab=Lab(self.notes)
        self.notes.voice_handler=self.lab.voice
        path=self.root/'synthetic.mp4'
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10,(160,120))
        for i in range(20):writer.write(np.full((120,160,3),(i*10,20,40),dtype=np.uint8))
        writer.release();self.video=path.read_bytes()
        self.meta={'title':'合成测试','author':'test','source_url':'https://example.invalid/synthetic',
                   'local_use_confirmed':True,'real_footage_confirmed':False}

    def tearDown(self):self.folder.cleanup()

    def import_asset(self):return self.lab.import_video(io.BytesIO(self.video),len(self.video),self.meta)

    def test_voice_missing_fields_confirmation_idempotency_and_reopen(self):
        raw=event(text='记录，TP1电压3.27伏，空载')
        self.notes.ingest(raw);self.notes.ingest(raw)
        drafts=self.lab.list('demo_measurements');self.assertEqual(len(drafts),1)
        item=drafts[0];self.assertEqual(item['point'],'TP1');self.assertEqual(item['unit'],'V')
        self.assertEqual(item['input_channel'],'device_asr_final');self.assertFalse(item['confirmed'])
        form={k:item[k] for k in ('id','point','value','unit','conditions')}
        with self.assertRaises(ValueError):self.lab.confirm_measurement(form)
        form['user_confirmed']=True;self.lab.confirm_measurement(form)
        self.assertTrue(Lab(self.notes).list('demo_measurements')[0]['confirmed'])
        self.lab.confirm_measurement(form)
        with self.assertRaises(ValueError):self.lab.confirm_measurement(dict(form,value='9'))
        parsed=measurement_fields('记录，TP2电压，空载');self.assertIn('数值和单位',parsed['missing'])
        parsed=measurement_fields('记录 TP1 3V，TP2 5V 空载');self.assertEqual(parsed['value'],'')

    def test_unusable_voice_not_structured_and_confirmed_source_stays_reported(self):
        truncated=event(text='记录 TP1 3V 空载');truncated['data'].update(truncated=True,usable_for_confirmation=False)
        self.notes.ingest(truncated)
        self.assertEqual(self.lab.list('demo_measurements'),[])

    def test_split_natural_measurement_preserves_millivolts_and_provenance(self):
        self.notes.ingest(event(text='电压七十三点三毫伏，空载。'))
        self.notes.ingest(event(seq=2,text='测量点是led1。'))
        rows=self.lab.list('demo_measurements');self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['value'],'73.3');self.assertEqual(rows[0]['unit'],'mV')
        self.assertEqual(rows[0]['point'],'LED1');self.assertEqual(len(rows[0]['speech_events']),2)
        self.assertFalse(rows[0]['confirmed']);self.assertIn('七十三点三',rows[0]['raw_text'])
        self.notes.ingest(event(seq=3,text='不要记录电压3V。'))
        self.assertEqual(len(self.lab.list('demo_measurements')),1)

    def test_trimmed_media_keeps_original_time_and_local_seek_separate(self):
        self.meta['source_offset_seconds']=150
        asset=self.import_asset();_,ref=self.lab.frame(asset['id'],.5)
        self.assertAlmostEqual(ref['seconds'],.5);self.assertAlmostEqual(ref['source_seconds'],150.5)

    def test_wiring_uses_only_reviewed_step_template(self):
        asset=self.import_asset();vision=Mock()
        vision.ask_many.return_value={'answer':'{"visible_evidence":"可见透明LED","unknown":"极性不清","next_check":"polarity"}','model':'synthetic'}
        result=self.lab.analyze(vision,{'media_id':asset['id'],'mode':'wiring','playhead':.5,'question':'下一步','upload_confirmed':True})
        self.assertIn('不靠试接供电确定',result['answer']);self.assertIn('极性不清',result['answer'])
        self.notes.ingest(event(seq=2,text='请介绍一下自己'))
        self.assertEqual(self.lab.list('demo_measurements'),[])

    def test_video_integrity_time_and_no_future_frames(self):
        asset=self.import_asset();self.assertFalse(asset['real_footage_claimed'])
        image,ref=self.lab.frame(asset['id'],.15)
        self.assertTrue(image.startswith(b'\xff\xd8\xff'));self.assertLessEqual(ref['seconds'],.15)
        self.lab.frame(asset['id'],asset['duration_seconds'])
        with self.assertRaises(ValueError):self.lab.frame(asset['id'],-1)
        path=self.lab.root/asset['file'];path.write_bytes(path.read_bytes()+b'tampered')
        with self.assertRaises(ValueError):self.lab.frame(asset['id'],0)

    def test_analysis_references_and_consent_does_not_confirm_measurements(self):
        asset=self.import_asset();self.lab.set_context({'media_id':asset['id'],'seconds':.5})
        self.notes.ingest(event(text='记录 TP1 3V 空载'))
        draft=self.lab.list('demo_measurements')[0];self.assertEqual(draft['evidence']['seconds'],.5)
        vision=Mock();vision.ask_many.return_value={'answer':'合成分析','model':'test','elapsed_seconds':.1}
        body={'media_id':asset['id'],'mode':'history','playhead':1.0,'start':0,'question':'合成问题'}
        with self.assertRaises(Exception):self.lab.analyze(vision,body)
        vision.ask_many.assert_not_called()
        result=self.lab.analyze(vision,dict(body,upload_confirmed=True))
        self.assertEqual(len(result['evidence']),3)
        self.assertTrue(all(ref['seconds']<=1 for ref in result['evidence']))
        self.assertNotIn('"point": "TP1"',vision.ask_many.call_args.args[1]) # unconfirmed data excluded
        self.assertFalse(self.lab.list('demo_measurements')[0]['confirmed'])
        with self.assertRaises(ValueError):self.lab.analyze(vision,dict(body,upload_confirmed=True,start=1.5))

    def test_safety_invalid_json_becomes_unknown_not_clear(self):
        asset=self.import_asset();vision=Mock()
        vision.ask_many.return_value={'answer':'看起来安全','model':'synthetic'}
        body={'media_id':asset['id'],'mode':'safety','playhead':.5,'question':'检查','upload_confirmed':True}
        item=self.lab.analyze(vision,body);self.assertEqual(item['alert']['status'],'unknown')
        vision.ask_many.return_value={'answer':'{"status":"risk","evidence":"合成依据","message":"合成提醒"}','model':'synthetic'}
        self.assertEqual(self.lab.analyze(vision,body)['alert']['status'],'risk')

    def test_real_http_upload_range_and_cross_origin_rejection(self):
        server=make_server(self.notes,0);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            query=parse.urlencode({**self.meta,'local_use_confirmed':'true','real_footage_confirmed':'false'})
            req=request.Request(base+'/api/demo/media?'+query,data=self.video,headers={'Content-Type':'video/mp4'})
            with request.urlopen(req) as response:asset=json.load(response)
            req=request.Request(base+'/media/'+asset['id']+'.mp4',headers={'Range':'bytes=0-31'})
            with request.urlopen(req) as response:
                self.assertEqual(response.status,206);self.assertEqual(response.read(),self.video[:32])
            req=request.Request(base+'/api/demo/state',headers={'Origin':'https://example.invalid'})
            with self.assertRaises(error.HTTPError) as caught:request.urlopen(req)
            self.assertEqual(caught.exception.code,403)
        finally:server.shutdown();server.server_close();worker.join(3)


if __name__=='__main__':unittest.main()
