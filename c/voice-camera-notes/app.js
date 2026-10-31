const $ = id => document.getElementById(id);
const cards = new Map();
let polling = false, cameraReady = false, lastNotice = null;
let visionBusy = false, visionConfigured = false;
async function askVision(noteId=null) {
  if(visionBusy)return;
  if(!$('uploadConsent').checked){say('请先勾选本次照片发送许可。',true);return;}
  const question=$('question').value.trim();
  if(!question){say('请先输入你想问的问题。',true);return;}
  visionBusy=true;$('askFrame').disabled=true;$('visionAnswer').textContent='';
  $('visionProgress').textContent=noteId?'正在发送这条记录的照片和口述……':'正在取一帧画面并发送问题……';
  try {
    const result=await post('/api/vision/ask',{question,upload_confirmed:true,...(noteId?{note_id:noteId}:{})});
    $('visionAnswer').textContent=result.answer;
    $('visionProgress').textContent='AI 生成 · '+(noteId?'记录照片':'本次画面')+'接收时间 '+new Date(result.photo_received_at).toLocaleString('zh-CN',{hour12:false})+' · 尚未经你核对';
  }catch(e){$('visionProgress').textContent=e.message;}
  finally{visionBusy=false;$('askFrame').disabled=!visionConfigured||!cameraReady;}
}
$('askFrame').onclick=()=>askVision();
$('preview').onerror=()=>{$('preview').removeAttribute('src');};
function say(text, error=false) { $('message').textContent=text; $('message').className=error?'error':''; }
async function post(path, body={}) {
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json(); if(!response.ok) throw new Error(data.error || '操作失败。'); return data;
}
$('start').onclick=async()=>{try{await post('/api/camera/start');say('正在开启相机，请确认取景。');}catch(e){say(e.message,true);}};
$('stop').onclick=async()=>{try{await post('/api/camera/stop');say('摄像头已关闭；已有记录仍保留。');}catch(e){say(e.message,true);}};
function showNote(note) {
  let card=cards.get(note.id);
  if(!card) {
    card=document.createElement('article');card.className='note';
    card.innerHTML='<img alt="该条口述关联的现场照片"><div class="note-body"><div class="note-head"><time></time><span class="state"></span></div><textarea aria-label="核对并修正口述"></textarea><small></small><details><summary>原始口述与来源</summary><p></p></details><button>确认保存这条</button></div>';
    card.querySelector('textarea').value=note.text;
    card.querySelector('details p').textContent='本人口述：'+note.raw_text;
    card.querySelector('button').onclick=async()=>{
      const button=card.querySelector('button');button.disabled=true;
      try {const saved=await post('/api/confirm',{id:note.id,text:card.querySelector('textarea').value,user_confirmed:true});showNote(saved);say('这条图文记录已确认保存。');}
      catch(e){say(e.message,true);button.disabled=false;}
    };
    const analyze=document.createElement('button');analyze.className='secondary';analyze.textContent='发送这条照片并提问';
    analyze.onclick=()=>askVision(note.id);analyze.disabled=!note.photo;
    card.querySelector('.note-body').append(analyze);
    cards.set(note.id,card);$('notes').prepend(card);
  }
  const image=card.querySelector('img');
  image.hidden=!note.photo;if(note.photo&&image.getAttribute('src')!='/photos/'+note.photo)image.src='/photos/'+note.photo;
  card.querySelector('time').textContent=new Date(note.created_at).toLocaleString('zh-CN',{hour12:false});
  const state=card.querySelector('.state');state.textContent=note.confirmed?'已确认':note.photo?'待确认':'拍照失败';state.className='state'+(note.confirmed?' confirmed':'');
  card.querySelector('small').textContent=note.capture_error || ('画面接收时间：'+new Date(note.photo_received_at).toLocaleTimeString('zh-CN',{hour12:false})+'；与转写接收相差 '+note.photo_offset_ms+' 毫秒。');
  card.querySelector('small').className=note.capture_error?'error':'';
  const input=card.querySelector('textarea');input.disabled=note.confirmed;
  if(note.confirmed) input.value=note.text;
  const button=card.querySelector('button');button.disabled=note.confirmed||!note.photo;button.textContent=note.confirmed?'已保存':'确认保存这条';
}
async function poll() {
  if(polling)return;polling=true;
  try {
    const response=await fetch('/api/state');if(!response.ok)throw new Error();
    const data=await response.json(),s=data.status;
    visionConfigured=Boolean(data.vision?.configured);
    $('visionStatus').textContent=visionConfigured?'模型已配置；实际识图能力仍需验证。':'尚未配置视觉模型；你仍可预览摄像头和保存记录。';
    const fresh=s.last_device_event && Date.now()-Date.parse(s.last_device_event)<45000;
    const ready=s.bridge_running&&s.record_mode_ack&&fresh;
    $('connection').textContent=ready?'设备已就绪':s.bridge_running?'等待设备就绪':'语音桥接未运行';$('connection').className='badge'+(ready?' ready':'');
    cameraReady=s.camera.ready;$('cameraBadge').textContent=cameraReady?'相机就绪 · '+s.camera.capture_fps+' 帧/秒':s.camera.running?'相机启动中':'摄像头未开启';
    $('askFrame').disabled=visionBusy||!visionConfigured||!cameraReady;
    if(cameraReady&&!$('preview').getAttribute('src'))$('preview').src='/api/stream?t='+Date.now();
    if(!cameraReady)$('preview').removeAttribute('src');
    $('preview').style.display=cameraReady?'block':'none';$('placeholder').hidden=cameraReady;
    $('start').disabled=s.camera.running;$('stop').disabled=!s.camera.running;
    if(s.camera.error)say(s.camera.error,true);
    if(s.notice&&s.notice.at!==lastNotice){lastNotice=s.notice.at;say(s.notice.text,true);}
    for(const note of [...data.notes].reverse())showNote(note);
    $('count').textContent=data.notes.length;$('empty').hidden=data.notes.length>0;
  }catch(e){$('connection').textContent='本机服务已断开';$('connection').className='badge';}
  finally{polling=false;}
}
poll();setInterval(poll,1000);
