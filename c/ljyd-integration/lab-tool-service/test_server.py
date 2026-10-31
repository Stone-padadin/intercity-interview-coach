import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch
from pathlib import Path
import uuid
import threading
import unittest
import urllib.request
import urllib.error
from server import Store, Invalid, make_server, assistant_execute

class ServiceTests(unittest.TestCase):
 def setUp(self):
  base=Path(__file__).parent/'.local'/'tests';base.mkdir(parents=True,exist_ok=True)
  self.root=base/('run_'+uuid.uuid4().hex);self.root.mkdir();self.db=self.root/'lab.db';self.store=Store(self.db,self.root)
  self.store.call('experiment_create',{'name':'真实电路待配置','experiment_id':'a'})
 def tearDown(self):pass  # isolated artifacts remain in ignored .local/tests
 def draft(self,eid='s1'):
  return self.store.call('measurement_draft',{'experiment_id':'a','event_id':eid,'point':'TP1','quantity':'voltage','value':3.27,'unit':'V','raw_text':'测试口述，非实际仪表数据'})
 def audit(self):
  return [json.loads(line) for line in (self.db.parent/'tool-audit.jsonl').read_text(encoding='utf-8').splitlines()]
 def test_audit_schema_privacy_and_invalid_names(self):
  secret='sensitive-argument-or-key-DO-NOT-LOG'
  self.store.call('experiment_end',{'experiment_id':'a'})
  self.store.call('experiment_create',{'name':secret,'experiment_id':'private-id'},transport='mcp')
  with self.assertRaises(Invalid):self.store.call('experiment_create',{'name':secret},transport='rest')
  with self.assertRaises(Invalid):self.store.call('experiment_current',secret,transport='mcp')
  before=self.audit()
  for action in (secret+'\nforged',None,{}):
   with self.assertRaises(Invalid):self.store.call(action,{'secret':secret})
  with self.assertRaises(Invalid):self.store.call('experiment_current',{},transport=secret)
  self.assertEqual(self.audit(),before)
  self.assertEqual([r['status'] for r in before],['success','success','success','failure','failure'])
  self.assertEqual([r['transport'] for r in before],['rest','rest','mcp','rest','mcp'])
  for record in before:
   self.assertEqual(set(record),{'timestamp','tool','status','transport'})
   self.assertIsNotNone(datetime.fromisoformat(record['timestamp']).tzinfo)
  raw=(self.db.parent/'tool-audit.jsonl').read_text(encoding='utf-8')
  for private in (secret,'private-id','created_at','已有活动实验'):
   self.assertNotIn(private,raw)
 def test_audit_failures_and_retries_preserve_transactions(self):
  draft=self.draft();self.draft()
  with self.assertRaises(Invalid):
   self.store.call('measurement_confirm',{'experiment_id':'a','event_id':'failed-confirm','measurement_id':draft['data']['id'],'user_confirmed':False})
  with self.store.connect() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],0)
   self.assertEqual(db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],1)
   self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
  self.assertEqual([r['status'] for r in self.audit()[-3:]],['success','success','failure'])
  with patch.object(self.store,'_call',side_effect=OSError('private-storage-error')):
   with self.assertRaises(OSError):self.store.call('experiment_current',{},transport='mcp')
  self.assertEqual(self.audit()[-1]['status'],'failure')
  self.assertNotIn('private-storage-error',(self.db.parent/'tool-audit.jsonl').read_text(encoding='utf-8'))
 def test_audit_io_failure_keeps_committed_result_and_original_error(self):
  with patch.object(Path,'open',side_effect=OSError('private-path')):
   with self.assertLogs('server',level='ERROR') as logs:
    ended=self.store.call('experiment_end',{'experiment_id':'a'})
    with self.assertRaises(Invalid):self.store.call('experiment_end',{'experiment_id':'missing'})
  self.assertEqual(ended['data']['status'],'ended')
  self.assertEqual(logs.output,['ERROR:server:Tool audit write failed']*2)
  with self.store.connect() as db:
   self.assertEqual(db.execute("SELECT status FROM experiments WHERE id='a'").fetchone()[0],'ended')
 def test_audit_concurrent_append_and_reopen(self):
  with ThreadPoolExecutor(max_workers=8) as pool:
   list(pool.map(lambda _:self.store.call('experiment_current',{},transport='mcp'),range(32)))
  reopened=Store(self.db,self.root);reopened.call('experiment_current',{},transport='rest')
  records=self.audit()
  self.assertEqual(len(records),34)
  self.assertEqual(sum(r['transport']=='mcp' for r in records),32)
  self.assertEqual(records[-1]['transport'],'rest')
  self.assertTrue(all(r['status']=='success' for r in records))
 def test_persistence_confirmation_revision_and_dedup(self):
  draft=self.draft();mid=draft['data']['id'];self.assertTrue(self.draft()['deduplicated'])
  self.assertEqual(self.store.call('measurement_list',{'experiment_id':'a'})['data'],[])
  args={'experiment_id':'a','event_id':'c1','measurement_id':mid,'user_confirmed':True}
  self.store.call('measurement_confirm',args)
  reopened=Store(self.db,self.root)
  self.assertEqual(len(reopened.call('measurement_list',{'experiment_id':'a'})['data']),1)
  reopened.call('measurement_update',{'experiment_id':'a','event_id':'u1','measurement_id':mid,'value':3.1})
  self.assertEqual(reopened.call('measurement_list',{'experiment_id':'a'})['data'],[])
  self.assertEqual(reopened.call('measurement_list',{'experiment_id':'a','include_drafts':True})['data'][0]['revision'],3)
  with reopened.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0],2)
 def test_explicit_user_confirmation(self):
  mid=self.draft()['data']['id']
  with self.assertRaises(Invalid):self.store.call('measurement_confirm',{'experiment_id':'a','event_id':'c','measurement_id':mid,'user_confirmed':False})
 def test_isolation_ended_and_event_collision(self):
  mid=self.draft()['data']['id'];self.store.call('experiment_end',{'experiment_id':'a'})
  with self.assertRaises(Invalid):self.draft('new')
  self.store.call('experiment_create',{'name':'第二实验','experiment_id':'b'})
  self.assertEqual(self.store.call('measurement_list',{'experiment_id':'b','include_drafts':True})['data'],[])
  with self.assertRaises(Invalid):self.store.call('measurement_confirm',{'experiment_id':'b','event_id':'c','measurement_id':mid,'user_confirmed':True})
  with self.assertRaises(Invalid):self.store.call('measurement_draft',{'experiment_id':'b','event_id':'s1','point':'TP1','quantity':'voltage','value':3.27,'unit':'V'})
 def test_no_ambiguous_current_experiment(self):
  with self.assertRaises(Invalid):self.store.call('experiment_create',{'name':'second'})
  self.assertEqual(self.store.call('experiment_current',{})['data']['id'],'a')
 def test_evidence_real_file_and_time_query(self):
  (self.root/'actual.txt').write_text('实际文件测试',encoding='utf-8')
  args={'experiment_id':'a','event_id':'ev1','path':'actual.txt','description':'接线操作标记','start_at':'2026-10-31T16:00:00+08:00','end_at':'2026-10-31T16:01:00+08:00'}
  ev=self.store.call('evidence_register',args)['data']
  self.assertEqual(ev['size_bytes'],len('实际文件测试'.encode()));self.assertEqual(ev['analysis_status'],'not_analyzed')
  self.assertEqual(len(ev['sha256']),64)
  result=self.store.call('evidence_query',{'experiment_id':'a','text':'接线','start_at':'2026-10-31T08:00:30Z'})
  self.assertEqual(len(result['data']),1)
  self.assertEqual(self.store.call('evidence_query',{'experiment_id':'a','start_at':'2026-10-31T09:00:00Z'})['data'],[])
  with self.assertRaises(Invalid):self.store.call('evidence_register',dict(args,event_id='ev2',path='missing.mp4'))
  with self.assertRaises(Invalid):self.store.call('evidence_register',dict(args,event_id='ev3',path='../outside'))
 def test_changed_retry_and_invalid_numeric(self):
  self.draft()
  with self.assertRaises(Invalid):self.store.call('measurement_draft',{'experiment_id':'a','event_id':'s1','point':'other','quantity':'voltage','value':4,'unit':'V'})
  with self.assertRaises(Invalid):self.store.call('measurement_draft',{'experiment_id':'a','event_id':'s2','point':'TP','quantity':'voltage','value':float('nan'),'unit':'V'})
 def test_assistant_http_confirmation_context_idempotency_and_isolation(self):
  token='assistant-test-token-01234567890123456789';server=make_server(self.store,token,port=0)
  thread=threading.Thread(target=server.serve_forever);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  def post(path,data,authorized=True):
   headers={'Content-Type':'application/json'}
   if authorized:headers['Authorization']='Bearer '+token
   req=urllib.request.Request(base+path,json.dumps(data).encode(),headers,method='POST')
   with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
  def failed(path,data,expected=400):
   with self.assertRaises(urllib.error.HTTPError) as e:post(path,data)
   self.assertEqual(e.exception.code,expected);return json.loads(e.exception.read())
  try:
   with self.assertRaises(urllib.error.HTTPError) as e:post('/v1/context',{},False)
   self.assertEqual(e.exception.code,401)
   context=post('/v1/context',{})['context']
   self.assertEqual(context['current_experiment']['id'],'a');self.assertEqual(context['records'],[]);self.assertEqual(context['pending'],[])
   self.assertEqual(post('/v1/assistant',{'action':'read','arguments':{},'user_text':'read only'})['context']['current_experiment']['id'],'a')
   failed('/v1/assistant',{'action':'create','arguments':{'name':'不可并行实验'},'user_text':'start','request_id':'create-a'})
   draft_args={'action':'draft','arguments':{'point':'TP-test','quantity':'voltage','value':2.37,'unit':'V'},'user_text':'测试口述2.37V（合成集成测试，不是实际读数）','request_id':'draft-a'}
   draft=post('/v1/assistant',draft_args);mid=draft['result']['data']['id']
   self.assertIn('合成集成测试',draft['context']['pending'][0]['raw_text'])
   failed('/v1/assistant',{'action':'confirm','arguments':{'measurement_id':mid},'user_text':'不要确认','request_id':'confirm-no'})
   failed('/v1/assistant',{'action':'confirm','arguments':{'measurement_id':mid},'user_text':'确认，但是先不要保存','request_id':'confirm-no2'})
   self.assertEqual(len(post('/v1/context',{})['context']['pending']),1)
   confirm={'action':'confirm','arguments':{'measurement_id':mid},'user_text':'确认保存','request_id':'confirm-yes'}
   result=post('/v1/assistant',confirm)
   self.assertEqual(len(result['context']['records']),1);self.assertEqual(result['context']['records'][0]['value'],2.37);self.assertEqual(result['context']['pending'],[])
   self.assertTrue(post('/v1/assistant',confirm)['result']['deduplicated'])
   failed('/v1/assistant',{'action':'end','arguments':{},'user_text':'还没结束，继续','request_id':'end-no'})
   ended=post('/v1/assistant',{'action':'end','arguments':{},'user_text':'确认结束实验','request_id':'end-yes'})
   self.assertIsNone(ended['context']['current_experiment'])
   second_args={'action':'create','arguments':{'name':'第二个合成测试实验'},'user_text':'开始第二测试','request_id':'create-b'}
   second=post('/v1/assistant',second_args)
   self.assertTrue(post('/v1/assistant',second_args)['result']['deduplicated'])
   self.assertNotEqual(second['context']['current_experiment']['id'],'a')
   self.assertEqual(second['context']['records'],[]);self.assertEqual(second['context']['pending'],[])
   failed('/v1/assistant',{'action':'draft','arguments':{'point':'TP','quantity':'voltage','value':1,'unit':'V','path':'../../secret'},'user_text':'do not use paths'})
   failed('/v1/assistant',{'action':'evidence_register','arguments':{'path':'video.mp4'},'user_text':'unsupported action'})
   names=[r['tool'] for r in self.audit()]
   self.assertIn('measurement_draft',names);self.assertIn('measurement_confirm',names);self.assertGreaterEqual(names.count('experiment_create'),3)
   self.assertTrue(all(r['transport']=='rest' for r in self.audit()))
  finally:server.shutdown();server.server_close();thread.join(timeout=5)

 def test_assistant_exact_user_commands_override_read_only_plan(self):
  self.draft()
  denied=assistant_execute(self.store,{'action':'read','arguments':{},'user_text':'不要确认保存'})
  self.assertEqual(denied['action'],'read');self.assertEqual(len(denied['context']['pending']),1)
  saved=assistant_execute(self.store,{'action':'read','arguments':{},'user_text':'确认保存。','request_id':'explicit-confirm'})
  self.assertEqual(saved['action'],'confirm');self.assertEqual(len(saved['context']['records']),1)
  self.assertTrue(assistant_execute(self.store,{'action':'read','arguments':{},'user_text':'确认保存。','request_id':'explicit-confirm'})['result']['deduplicated'])
  ended=assistant_execute(self.store,{'action':'read','arguments':{},'user_text':'结束实验。'})
  self.assertEqual(ended['action'],'end');self.assertIsNone(ended['context']['current_experiment'])

 def test_assistant_origin_rejection(self):
  token='assistant-test-token-01234567890123456789';server=make_server(self.store,token,port=0)
  thread=threading.Thread(target=server.serve_forever);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  try:
   req=urllib.request.Request(base+'/v1/assistant',json.dumps({'action':'read','arguments':{},'user_text':'x'}).encode(),{'Authorization':'Bearer '+token,'Content-Type':'application/json','Origin':'https://attacker.example'},method='POST')
   with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req,timeout=5)
   self.assertEqual(e.exception.code,403)
  finally:server.shutdown();server.server_close();thread.join(timeout=5)

 def test_http_auth_rest_and_mcp(self):
  token='test-only-token-01234567890123456789';server=make_server(self.store,token,port=0)
  thread=threading.Thread(target=server.serve_forever);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  def post(path,data,authorized=True):
   headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
   if authorized:headers['Authorization']='Bearer '+token
   req=urllib.request.Request(base+path,json.dumps(data).encode(),headers,method='POST')
   with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
  try:
   with urllib.request.urlopen(base+'/health') as r:self.assertTrue(json.load(r)['ok'])
   with self.assertRaises(urllib.error.HTTPError) as e:post('/v1/experiments/current',{},False)
   self.assertEqual(e.exception.code,401)
   self.assertEqual(post('/v1/experiments/current',{})['data']['id'],'a')
   initialized=post('/mcp',{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26'}})
   self.assertEqual(initialized['result']['protocolVersion'],'2025-03-26')
   listed=post('/mcp',{'jsonrpc':'2.0','id':2,'method':'tools/list'})
   self.assertEqual(len(listed['result']['tools']),10)
   called=post('/mcp',{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'experiment_current','arguments':{}}})
   self.assertFalse(called['result']['isError'])
   self.assertEqual(json.loads(called['result']['content'][0]['text'])['data']['id'],'a')
   failed=post('/mcp',{'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'experiment_end','arguments':{'experiment_id':'missing-private-id'}}})
   self.assertTrue(failed['result']['isError'])
   with self.assertRaises(urllib.error.HTTPError) as e:post('/v1/actions',{'action':'experiment_end','arguments':{'experiment_id':'missing-private-id'}})
   self.assertEqual(e.exception.code,400)
   self.assertEqual([(r['tool'],r['status'],r['transport']) for r in self.audit()[1:]],[
    ('experiment_current','success','rest'),('experiment_current','success','mcp'),
    ('experiment_end','failure','mcp'),('experiment_end','failure','rest')])
   audit_text=(self.db.parent/'tool-audit.jsonl').read_text(encoding='utf-8')
   self.assertNotIn(token,audit_text);self.assertNotIn('missing-private-id',audit_text)
  finally:server.shutdown();server.server_close();thread.join(timeout=5)

 def test_legacy_sse_discovery_and_measurement_calls(self):
  token='sse-test-only-token-012345678901234';server=make_server(self.store,token,port=0)
  thread=threading.Thread(target=server.serve_forever);thread.start();base=f'http://127.0.0.1:{server.server_port}';stream=None
  auth={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
  def event():
   kind='message';parts=[]
   while True:
    line=stream.readline().decode('utf-8').rstrip('\r\n')
    if line.startswith('event: '):kind=line[7:]
    elif line.startswith('data: '):parts.append(line[6:])
    elif not line and parts:return kind,'\n'.join(parts)
  def send(path,message,authorized=True):
   headers=auth if authorized else {'Content-Type':'application/json'}
   with urllib.request.urlopen(urllib.request.Request(base+path,json.dumps(message).encode(),headers,method='POST'),timeout=5) as r:self.assertEqual(r.status,202)
  def rpc(rid,method,params=None):
   send(endpoint,{'jsonrpc':'2.0','id':rid,'method':method,'params':params or {}})
   kind,data=event();self.assertEqual(kind,'message');response=json.loads(data);self.assertEqual(response['id'],rid);return response
  def call(rid,name,args):
   response=rpc(rid,'tools/call',{'name':name,'arguments':args});self.assertFalse(response['result']['isError']);return json.loads(response['result']['content'][0]['text'])
  try:
   with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(base+'/sse',timeout=5)
   self.assertEqual(e.exception.code,401)
   stream=urllib.request.urlopen(urllib.request.Request(base+'/sse',headers=auth),timeout=5)
   self.assertEqual(stream.headers.get_content_type(),'text/event-stream')
   kind,endpoint=event();self.assertEqual(kind,'endpoint');self.assertTrue(endpoint.startswith('/messages?session_id='))
   initialized=rpc(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'test','version':'1'}})
   self.assertEqual(initialized['result']['protocolVersion'],'2024-11-05')
   send(endpoint,{'jsonrpc':'2.0','method':'notifications/initialized'})
   self.assertEqual(len(rpc(2,'tools/list')['result']['tools']),10)
   draft=call(3,'measurement_draft',{'experiment_id':'a','event_id':'sse-draft','point':'TP-test','quantity':'voltage','value':2.37,'unit':'V'})
   self.assertEqual(call(4,'measurement_list',{'experiment_id':'a'})['data'],[])
   call(5,'measurement_confirm',{'experiment_id':'a','event_id':'sse-confirm','measurement_id':draft['data']['id'],'user_confirmed':True})
   self.assertEqual(call(6,'measurement_list',{'experiment_id':'a'})['data'][0]['value'],2.37)
   with self.assertRaises(urllib.error.HTTPError) as e:send(endpoint,{'jsonrpc':'2.0','id':7,'method':'ping'},False)
   self.assertEqual(e.exception.code,401)
   with self.assertRaises(urllib.error.HTTPError) as e:send('/messages?session_id=unknown',{'jsonrpc':'2.0','id':8,'method':'ping'})
   self.assertEqual(e.exception.code,404)
   self.assertEqual([(r['tool'],r['status'],r['transport']) for r in self.audit()[1:]],[
    ('measurement_draft','success','mcp'),('measurement_list','success','mcp'),
    ('measurement_confirm','success','mcp'),('measurement_list','success','mcp')])
   self.assertNotIn(token,(self.db.parent/'tool-audit.jsonl').read_text(encoding='utf-8'))
  finally:
   if stream:stream.close()
   server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':unittest.main(verbosity=2)
