"""Local experimental record service. Python 3.11+, standard library only."""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import contextmanager
from datetime import datetime, timezone
import uuid
import queue
import threading
import time
from urllib.parse import urlsplit, parse_qs

TOOLS = {
 'experiment_create': ('创建实验，不生成参考测量值', {'name': 'string', 'experiment_id': 'string', 'event_id': 'string'}, ['name']),
 'experiment_current': ('查询当前活动实验', {}, []),
 'experiment_end': ('结束指定实验', {'experiment_id': 'string', 'event_id': 'string'}, ['experiment_id']),
 'measurement_draft': ('保存用户口述测量草稿，尚未确认', {'experiment_id':'string','event_id':'string','point':'string','quantity':'string','value':'number','unit':'string','conditions':'string','raw_text':'string','occurred_at':'string'}, ['experiment_id','event_id','point','quantity','value','unit']),
 'measurement_confirm': ('用户明确确认后确认测量草稿', {'experiment_id':'string','event_id':'string','measurement_id':'string','user_confirmed':'boolean'}, ['experiment_id','event_id','measurement_id','user_confirmed']),
 'measurement_update': ('修改测量并恢复待确认，保留修订历史', {'experiment_id':'string','event_id':'string','measurement_id':'string','point':'string','quantity':'string','value':'number','unit':'string','conditions':'string','raw_text':'string'}, ['experiment_id','event_id','measurement_id']),
 'measurement_list': ('列出指定实验测量，默认仅已确认结果', {'experiment_id':'string','include_drafts':'boolean'}, ['experiment_id']),
 'evidence_register': ('登记服务端真实文件元数据，不分析视频', {'experiment_id':'string','event_id':'string','path':'string','description':'string','start_at':'string','end_at':'string'}, ['experiment_id','event_id','path']),
 'evidence_list': ('列出指定实验实际证据元数据', {'experiment_id':'string'}, ['experiment_id']),
 'evidence_query': ('按文字与时间筛选已登记证据元数据，不是视觉语义分析', {'experiment_id':'string','text':'string','start_at':'string','end_at':'string'}, ['experiment_id']),
}

def now(): return datetime.now(timezone.utc).isoformat()
def ident(prefix): return prefix + '_' + uuid.uuid4().hex
class Invalid(ValueError): pass

def timestamp(value):
 if not isinstance(value,str): raise Invalid('时间必须为带时区 ISO8601 字符串')
 try: d=datetime.fromisoformat(value.replace('Z','+00:00'))
 except ValueError: raise Invalid('无效 ISO8601 时间')
 if d.tzinfo is None: raise Invalid('时间必须包含时区')
 return d.astimezone(timezone.utc).isoformat()

class Store:
 def __init__(self, path, evidence_root):
  self.path=str(path);self.root=Path(evidence_root).resolve()
  self.audit_path=Path(path).resolve().parent/'tool-audit.jsonl'
  self.audit_lock=threading.Lock()
  Path(path).parent.mkdir(parents=True,exist_ok=True)
  with self.connect() as db:
   db.executescript('''
   CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY,name TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,ended_at TEXT);
   CREATE TABLE IF NOT EXISTS measurements(id TEXT PRIMARY KEY,experiment_id TEXT NOT NULL,payload TEXT NOT NULL,confirmed INTEGER NOT NULL,revision INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,experiment_id TEXT NOT NULL,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,experiment_id TEXT NOT NULL,action TEXT NOT NULL,request TEXT NOT NULL,response TEXT NOT NULL,created_at TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY,measurement_id TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
   ''')
 @contextmanager
 def connect(self):
  db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
  try:
   with db:yield db
  finally:db.close()
 def call(self, action, args, *, transport='rest'):
  # Never log untrusted names, arguments, results, errors, or credentials.
  if not isinstance(action,str) or action not in TOOLS: raise Invalid('未知工具')
  if transport not in ('mcp','rest'):raise Invalid('未知传输')
  success=False
  try:
   result=self._call(action,args)
   success=True
   return result
  finally:
   self._audit(action,success,transport)
 def find_event(self,event_id):
  with self.connect() as db:
   row=db.execute('SELECT * FROM events WHERE event_id=?',(event_id,)).fetchone()
   return dict(row) if row else None
 def _audit(self, action, success, transport):
  record={'timestamp':now(),'tool':action,'status':'success' if success else 'failure','transport':transport}
  try:
   with self.audit_lock:
    with self.audit_path.open('a',encoding='utf-8') as file:
     file.write(json.dumps(record,ensure_ascii=True)+'\n')
  except OSError:
   # Audit I/O must not turn a committed write into an apparent failed call.
   logging.getLogger(__name__).error('Tool audit write failed')
 def _call(self, action, args):
  if not isinstance(args,dict):raise Invalid('参数必须是对象')
  for field,typ in TOOLS[action][1].items():
   if field not in args:continue
   v=args[field]
   valid=isinstance(v,str) if typ=='string' else isinstance(v,bool) if typ=='boolean' else isinstance(v,(int,float)) and not isinstance(v,bool)
   if not valid:raise Invalid('字段类型错误: '+field)
   if isinstance(v,str) and (len(v)>16000 or ('\x00' in v)):raise Invalid('字段过长或包含空字符')
   if typ=='number' and (v!=v or abs(v)==float('inf')):raise Invalid('数值必须有限')
  for field in TOOLS[action][2]:
   if field not in args or args[field] is None or args[field]=='':raise Invalid('缺少字段: '+field)
  extra=set(args)-set(TOOLS[action][1])
  if extra:raise Invalid('未知字段: '+','.join(sorted(extra)))
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   exp=args.get('experiment_id'); eid=args.get('event_id')
   request=json.dumps(args,sort_keys=True,ensure_ascii=False)
   if eid:
    old=db.execute('SELECT * FROM events WHERE event_id=?',(eid,)).fetchone()
    if old:
     if old['action']!=action or old['request']!=request:raise Invalid('event_id 已用于不同请求；拒绝跨实验或变更重放')
     return dict(json.loads(old['response']),deduplicated=True)
   if action=='experiment_create':
    exp=exp or ident('exp')
    if db.execute("SELECT 1 FROM experiments WHERE status='active'").fetchone():raise Invalid('已有活动实验，请先结束，避免设备会话归属不明确')
    try:db.execute('INSERT INTO experiments VALUES(?,?,?,?,NULL)',(exp,args['name'],'active',now()))
    except sqlite3.IntegrityError:raise Invalid('实验ID已存在')
    result=dict(db.execute('SELECT * FROM experiments WHERE id=?',(exp,)).fetchone())
   elif action=='experiment_current':
    row=db.execute("SELECT * FROM experiments WHERE status='active'").fetchone();result=dict(row) if row else None
   else:
    row=db.execute('SELECT * FROM experiments WHERE id=?',(exp,)).fetchone()
    if row is None:raise Invalid('实验不存在')
    writes=action not in ('measurement_list','evidence_list','evidence_query')
    if writes and row['status']!='active':raise Invalid('实验已结束，不允许写入')
    if action=='experiment_end':
     db.execute("UPDATE experiments SET status='ended',ended_at=? WHERE id=?",(now(),exp));result=dict(db.execute('SELECT * FROM experiments WHERE id=?',(exp,)).fetchone())
    elif action=='measurement_draft':
     mid=ident('m');payload={k:args[k] for k in ('point','quantity','value','unit','conditions','raw_text') if k in args}
     payload.update(id=mid,experiment_id=exp,source='user_reported',speech_event_id=eid,occurred_at=timestamp(args['occurred_at']) if args.get('occurred_at') else None,received_at=now(),confirmed=False,revision=1)
     db.execute('INSERT INTO measurements VALUES(?,?,?,?,?)',(mid,exp,json.dumps(payload,ensure_ascii=False),0,1));result=payload
    elif action in ('measurement_confirm','measurement_update'):
     row=db.execute('SELECT * FROM measurements WHERE id=? AND experiment_id=?',(args['measurement_id'],exp)).fetchone()
     if not row:raise Invalid('当前实验中不存在该测量')
     payload=json.loads(row['payload']);db.execute('INSERT INTO revisions(measurement_id,payload,created_at) VALUES(?,?,?)',(payload['id'],row['payload'],now()))
     if action=='measurement_confirm':
      if args['user_confirmed'] is not True:raise Invalid('需要用户明确确认')
      payload.update(confirmed=True,confirmed_at=now(),confirmation_event_id=eid)
     else:
      changes={k:v for k,v in args.items() if k not in ('experiment_id','event_id','measurement_id')}
      if not changes:raise Invalid('未提供修改字段')
      if any(changes.get(k)=='' for k in ('point','quantity','unit')):raise Invalid('位置、物理量与单位不能为空')
      payload.update(changes);payload.update(confirmed=False);payload.pop('confirmed_at',None);payload.pop('confirmation_event_id',None)
     payload.update(revision=row['revision']+1,updated_at=now())
     db.execute('UPDATE measurements SET payload=?,confirmed=?,revision=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),int(payload['confirmed']),payload['revision'],payload['id']));result=payload
    elif action=='measurement_list':
     sql='SELECT payload FROM measurements WHERE experiment_id=?'+('' if args.get('include_drafts',False) else ' AND confirmed=1')+' ORDER BY rowid'
     result=[json.loads(r[0]) for r in db.execute(sql,(exp,))]
    elif action=='evidence_register':
     path=Path(args['path']);path=(self.root/path).resolve() if not path.is_absolute() else path.resolve()
     if not path.is_relative_to(self.root):raise Invalid('文件必须位于配置的 evidence-root 内')
     if not path.is_file():raise Invalid('证据文件不存在')
     start=timestamp(args['start_at']) if args.get('start_at') else None;end=timestamp(args['end_at']) if args.get('end_at') else None
     if start and end and start>end:raise Invalid('证据开始时间晚于结束时间')
     stat=path.stat();digest=hashlib.sha256()
     with path.open('rb') as file:
      for chunk in iter(lambda:file.read(1024*1024),b''):digest.update(chunk)
     payload={'id':ident('ev'),'experiment_id':exp,'source':'registered_local_file','relative_path':str(path.relative_to(self.root)),'size_bytes':stat.st_size,'sha256':digest.hexdigest(),'file_modified_at':datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat(),'registered_at':now(),'event_id':eid,'description':args.get('description',''),'start_at':start,'end_at':end,'analysis_status':'not_analyzed','time_source':'user_supplied' if start or end else 'not_provided'}
     db.execute('INSERT INTO evidence VALUES(?,?,?)',(payload['id'],exp,json.dumps(payload,ensure_ascii=False)));result=payload
    else:
     result=[json.loads(r[0]) for r in db.execute('SELECT payload FROM evidence WHERE experiment_id=? ORDER BY rowid',(exp,))]
     if action=='evidence_query':
      text=args.get('text','').casefold();start=timestamp(args['start_at']) if args.get('start_at') else None;end=timestamp(args['end_at']) if args.get('end_at') else None
      if start and end and start>end:raise Invalid('查询开始时间晚于结束时间')
      result=[r for r in result if (not text or text in (r['description']+' '+r['relative_path']).casefold()) and (not start or (r['end_at'] or r['start_at'] or '')>=start) and (not end or bool(r['start_at'] or r['end_at']) and (r['start_at'] or r['end_at'])<=end)]
   response={'ok':True,'experiment_id':exp,'action':action,'data':result,'event_id':eid,'source':'lab_tool_service','received_at':now()}
   if eid:db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(eid,exp,action,request,json.dumps(response,ensure_ascii=False),now()))
   return response

REST={
 '/v1/experiments/create':'experiment_create','/v1/experiments/current':'experiment_current','/v1/experiments/end':'experiment_end',
 '/v1/measurements/draft':'measurement_draft','/v1/measurements/confirm':'measurement_confirm','/v1/measurements/update':'measurement_update','/v1/measurements/list':'measurement_list',
 '/v1/evidence/register':'evidence_register','/v1/evidence/list':'evidence_list','/v1/evidence/query':'evidence_query'}

ASSISTANT_ACTIONS={'read','create','draft','confirm','update','end'}

def _explicit_user_confirmation(text):
 if not isinstance(text,str) or len(text)>4000:return False
 compact=''.join(ch for ch in text.strip() if ch.isalnum())
 if not compact or any(word in compact for word in ('不要','不确认','别确认','不保存','别保存','不要保存','拒绝','取消','不是','错误','不对')):return False
 return compact in {'确认','确认保存','确认记录','我确认','我确认保存','正确','没错','对','是的','保存','保存这条','这条没错','数据正确','数值正确','确认无误'}

def _explicit_user_end(text):
 if not isinstance(text,str) or len(text)>4000:return False
 compact=''.join(ch for ch in text.strip() if ch.isalnum())
 if not compact or any(word in compact for word in ('不要','别','不结束','拒绝','取消','不是','继续','还没结束')):return False
 return compact in {'结束','结束实验','确认结束','结束本次实验','实验结束','完成实验','确认结束实验','是的结束'}

def _assistant_context(store):
 current=store.call('experiment_current',{})['data']
 measurements=[]
 evidence=[]
 if current is not None:
  measurements=store.call('measurement_list',{'experiment_id':current['id'],'include_drafts':True})['data']
  evidence=store.call('evidence_list',{'experiment_id':current['id']})['data']
 confirmed=[m for m in measurements if m.get('confirmed')]
 pending=[m for m in measurements if not m.get('confirmed')]
 return {'current_experiment':current,'records':confirmed,'pending':pending,'evidence':evidence}

def _assistant_replay(store, action, args, user_text, event_id):
 previous=store.find_event(event_id)
 if previous is None:return None
 tool={'create':'experiment_create','draft':'measurement_draft','confirm':'measurement_confirm','update':'measurement_update','end':'experiment_end'}[action]
 if previous['action']!=tool:raise Invalid('request_id已用于不同操作')
 old=json.loads(previous['request'])
 if action=='create':same=old.get('name')==args.get('name','').strip()
 elif action=='draft':same=old.get('raw_text')==user_text.strip() and all(old.get(k)==v for k,v in args.items())
 elif action=='confirm':same=old.get('user_confirmed') is True and (args.get('measurement_id') is None or old.get('measurement_id')==args['measurement_id'])
 elif action=='update':same=old.get('raw_text')==user_text.strip() and (args.get('measurement_id') is None or old.get('measurement_id')==args['measurement_id']) and all(old.get(k)==v for k,v in args.items() if k!='measurement_id')
 else:same=not args
 if not same:raise Invalid('request_id已用于不同内容')
 return dict(json.loads(previous['response']),deduplicated=True)

def assistant_execute(store, data):
 if not isinstance(data,dict) or set(data)-{'action','arguments','user_text','request_id'}:raise Invalid('assistant请求字段不合法')
 action=data.get('action');args=data.get('arguments',{});user_text=data.get('user_text','')
 if action not in ASSISTANT_ACTIONS:raise Invalid('assistant action不支持')
 if not isinstance(args,dict):raise Invalid('arguments必须为对象')
 if not isinstance(user_text,str) or len(user_text)>4000 or '\x00' in user_text:raise Invalid('user_text不合法')
 # Exact affirmative/finish phrases are deterministic user commands. A model
 # choosing read must not prevent an explicit confirmation from taking effect.
 if action=='read' and not args:
  if _explicit_user_confirmation(user_text):action='confirm'
  elif _explicit_user_end(user_text):action='end'
 request_id=data.get('request_id')
 if request_id is None:request_id=ident('req')
 if not isinstance(request_id,str) or not request_id or len(request_id)>160 or '\\x00' in request_id:raise Invalid('request_id不合法')
 event_id='assistant:'+request_id+':'+action
 result=None
 context=None
 if action!='read':
  if action=='confirm' and not _explicit_user_confirmation(user_text):raise Invalid('需要用户明确肯定确认，当前请求未执行')
  if action=='end' and not _explicit_user_end(user_text):raise Invalid('需要用户明确结束实验，当前请求未执行')
  replay=_assistant_replay(store,action,args,user_text,event_id)
  if replay is not None:return {'ok':True,'action':action,'request_id':request_id,'result':replay,'context':_assistant_context(store),'source':'lab_tool_service'}
 if action=='read':
  if args:raise Invalid('read不接受arguments')
  context=_assistant_context(store)
 elif action=='create':
  if set(args)-{'name'} or not isinstance(args.get('name'),str) or not args['name'].strip():raise Invalid('create需要实验名称name')
  result=store.call('experiment_create',{'name':args['name'].strip(),'event_id':event_id})
  context=_assistant_context(store)
 elif action=='draft':
  allowed={'point','quantity','value','unit','conditions'}
  if set(args)-allowed:raise Invalid('draft仅接受测量字段')
  if not user_text.strip():raise Invalid('draft必须附真实用户口述user_text')
  current=store.call('experiment_current',{})['data']
  if current is None:raise Invalid('没有活动实验，请先创建实验')
  tool_args={'experiment_id':current['id'],'event_id':event_id,'raw_text':user_text.strip(),**args}
  result=store.call('measurement_draft',tool_args)
  context=_assistant_context(store)
 elif action=='confirm':
  if set(args)-{'measurement_id'}:raise Invalid('confirm只接受measurement_id')
  if not _explicit_user_confirmation(user_text):raise Invalid('需要用户明确肯定确认，当前请求未执行')
  context=_assistant_context(store)
  current=context['current_experiment']
  if current is None:raise Invalid('没有活动实验，无测量可确认')
  pending=context['pending']
  measurement_id=args.get('measurement_id') or (pending[-1]['id'] if pending else None)
  target=next((m for m in pending if m['id']==measurement_id),None)
  if target is None:raise Invalid('只能确认当前实验中的待确认测量')
  result=store.call('measurement_confirm',{'experiment_id':current['id'],'event_id':event_id,'measurement_id':measurement_id,'user_confirmed':True})
  context=_assistant_context(store)
 elif action=='update':
  allowed={'measurement_id','point','quantity','value','unit','conditions'}
  if set(args)-allowed:raise Invalid('update仅接受测量字段')
  if not (set(args)&{'point','quantity','value','unit','conditions'}):raise Invalid('update至少需要一个修改字段')
  if not user_text.strip():raise Invalid('update必须附真实用户更正user_text')
  context=_assistant_context(store);current=context['current_experiment']
  if current is None:raise Invalid('没有活动实验，无测量可修改')
  all_current=context['records']+context['pending']
  measurement_id=args.get('measurement_id') or (context['pending'][-1]['id'] if context['pending'] else context['records'][-1]['id'] if context['records'] else None)
  if not measurement_id or not any(m['id']==measurement_id for m in all_current):raise Invalid('只能修改当前实验中的测量')
  changes={k:v for k,v in args.items() if k!='measurement_id'}
  changes['raw_text']=user_text.strip()
  result=store.call('measurement_update',{'experiment_id':current['id'],'event_id':event_id,'measurement_id':measurement_id,**changes})
  context=_assistant_context(store)
 elif action=='end':
  if args:raise Invalid('end不接受arguments')
  if not _explicit_user_end(user_text):raise Invalid('需要用户明确结束实验，当前请求未执行')
  current=store.call('experiment_current',{})['data']
  if current is None:raise Invalid('没有活动实验')
  result=store.call('experiment_end',{'experiment_id':current['id'],'event_id':event_id})
  context=_assistant_context(store)
 return {'ok':True,'action':action,'request_id':request_id,'result':result,'context':context,'source':'lab_tool_service'}

def tools():return [{'name':name,'description':description,'inputSchema':{'type':'object','properties':{k:{'type':v} for k,v in fields.items()},'required':required,'additionalProperties':False}} for name,(description,fields,required) in TOOLS.items()]
def rpc_response(store, data, legacy=False):
 rid=data.get('id')
 if data.get('jsonrpc')!='2.0':return {'jsonrpc':'2.0','id':rid,'error':{'code':-32600,'message':'Invalid Request'}}
 method=data.get('method');params=data.get('params',{})
 if not isinstance(params,dict):return {'jsonrpc':'2.0','id':rid,'error':{'code':-32602,'message':'Invalid params'}}
 if rid is None:return None
 if method=='initialize':
  supported=('2024-11-05','2025-03-26','2025-06-18')
  requested=params.get('protocolVersion')
  version=requested if requested in supported else ('2024-11-05' if legacy else '2025-03-26')
  result={'protocolVersion':version,'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'lab-tool-service','version':'1.1.0'}}
 elif method=='ping':result={}
 elif method=='tools/list':result={'tools':tools()}
 elif method=='tools/call':
  try:
   value=store.call(params.get('name'),params.get('arguments',{}),transport='mcp');result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
  except (Invalid,ValueError,TypeError):result={'content':[{'type':'text','text':'请求未通过校验，请检查实验ID、字段和用户确认状态。'}],'isError':True}
  except (OSError,sqlite3.Error):result={'content':[{'type':'text','text':'存储或证据文件操作失败。'}],'isError':True}
 else:return {'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}}
 return {'jsonrpc':'2.0','id':rid,'result':result}

def make_server(store,token,host='127.0.0.1',port=8765):
 sessions={};sessions_lock=threading.Lock()
 class Handler(BaseHTTPRequestHandler):
  server_version='LabTools/1.0'
  def log_message(self,format,*args):pass  # no headers, measurements, paths or credentials in logs
  def reply(self,status,data):
   body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
  def authorized(self):
   return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
  def do_GET(self):
   if self.path=='/health' and self.client_address[0] in ('127.0.0.1','::1'):
    self.reply(200,{'ok':True,'service':'lab-tool-service','visual_analysis':False});return
   if not self.authorized():self.reply(401,{'ok':False,'error':'unauthorized'});return
   if self.headers.get('Origin'):self.reply(403,{'ok':False,'error':'browser origins not permitted'});return
   if urlsplit(self.path).path=='/sse':self.sse();return
   self.reply(405,{'ok':False,'error':'Use POST /mcp or GET /sse'})
  def sse(self):
   sid=secrets.token_urlsafe(32);inbox=queue.Queue(maxsize=64)
   with sessions_lock:
    if len(sessions)>=32:self.reply(503,{'ok':False,'error':'session_limit'});return
    sessions[sid]=inbox
   self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache, no-store');self.send_header('X-Accel-Buffering','no');self.end_headers()
   def emit(event,data):
    self.wfile.write(('event: '+event+'\ndata: '+data+'\n\n').encode('utf-8'));self.wfile.flush()
   try:
    emit('endpoint','/messages?session_id='+sid)
    deadline=time.monotonic()+1800
    while time.monotonic()<deadline:
     try:response=inbox.get(timeout=1)
     except queue.Empty:self.wfile.write(b': keepalive\n\n');self.wfile.flush();continue
     emit('message',json.dumps(response,ensure_ascii=False,allow_nan=False))
   except (OSError,ConnectionError):pass
   finally:
    with sessions_lock:sessions.pop(sid,None)
  def do_POST(self):
   if not self.authorized():self.reply(401,{'ok':False,'error':'unauthorized'});return
   if self.headers.get('Origin'):
    # Local HTTP server is intended for server-to-server calls, not arbitrary websites.
    self.reply(403,{'ok':False,'error':'browser origins not permitted'});return
   try:
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=1048576:raise Invalid('请求体长度不合法')
    data=json.loads(self.rfile.read(length),parse_constant=lambda x:(_ for _ in ()).throw(Invalid('数值不合法')))
    if not isinstance(data,dict):raise Invalid('请求必须为对象')
    path=urlsplit(self.path).path
    if path=='/v1/assistant':self.reply(200,assistant_execute(store,data));return
    if path=='/v1/context':
     if data:raise Invalid('context不接受请求字段')
     self.reply(200,{'ok':True,'action':'read','context':_assistant_context(store),'source':'lab_tool_service'});return
    if self.path=='/mcp':self.mcp(data);return
    if urlsplit(self.path).path=='/messages':
     query=parse_qs(urlsplit(self.path).query);sid=query.get('session_id',[''])[0]
     with sessions_lock:inbox=sessions.get(sid)
     if inbox is None:self.reply(404,{'ok':False,'error':'unknown_or_expired_session'});return
     response=rpc_response(store,data,legacy=True)
     if response is not None:
      try:inbox.put_nowait(response)
      except queue.Full:self.reply(503,{'ok':False,'error':'session_queue_full'});return
     self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
    action=REST.get(path)
    if path=='/v1/actions':action=data.get('action');data=data.get('arguments',{})
    if not action:self.reply(404,{'ok':False,'error':'not_found'});return
    self.reply(200,store.call(action,data,transport='rest'))
   except (Invalid,ValueError,TypeError) as e:self.reply(400,{'ok':False,'error':str(e)})
   except (OSError,sqlite3.Error):self.reply(500,{'ok':False,'error':'storage_or_file_error'})
  def mcp(self,data):
   response=rpc_response(store,data)
   if response is None:
    self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
   self.reply(200,response)
 return ThreadingHTTPServer((host,port),Handler)

def main():
 p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8765);p.add_argument('--data-dir',default=str(Path(__file__).parent/'.local'));p.add_argument('--evidence-root');a=p.parse_args()
 if a.host not in ('127.0.0.1','localhost'):p.error('仅支持本机监听；公网接入由部署代理另行配置')
 local=Path(a.data_dir);local.mkdir(parents=True,exist_ok=True)
 token=os.environ.get('LAB_TOOL_TOKEN')
 if not token:
  key=local/'token'
  if not key.exists():
   fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32))
  token=key.read_text().strip()
 if len(token)<24:p.error('LAB_TOOL_TOKEN 必须至少24字符')
 root=Path(a.evidence_root) if a.evidence_root else local/'evidence';root.mkdir(parents=True,exist_ok=True)
 server=make_server(Store(local/'lab.sqlite3',root),token,a.host,a.port)
 print(f'Lab tools listening on http://{a.host}:{a.port}; auth required; token not printed.',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()
