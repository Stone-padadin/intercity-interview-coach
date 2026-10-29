const candidateName=localStorage.getItem('candidateName');
const apiKey='interviewPracticeApiBase';
const apiConfigured=(localStorage.getItem(apiKey)||'').trim().replace(/\/$/,'');
const apiIsLocal=location.hostname==='localhost'||location.hostname==='127.0.0.1';
window.InterviewPracticeApi=window.InterviewPracticeApi||{base:apiConfigured||(apiIsLocal?location.origin:''),url(path){return `${this.base}${path}`},isConfigured:Boolean(apiConfigured||(apiIsLocal?location.origin:'')),save(value){const next=String(value||'').trim().replace(/\/$/,'');if(next)localStorage.setItem(apiKey,next);else localStorage.removeItem(apiKey);location.reload()}};
if(location.pathname.endsWith('settings.html')){
  const list=document.querySelector('.settings-list');
  if(list){const row=document.createElement('div');row.innerHTML='<strong>后端地址</strong><span>公网部署时填写独立 Node.js 后端地址；留空使用演示模式</span><input id="apiBase" type="url" placeholder="https://your-backend.example.com"><button id="saveApi" type="button">保存地址</button><small id="apiStatus"></small>';list.append(row);const input=row.querySelector('#apiBase');const status=row.querySelector('#apiStatus');input.value=window.InterviewPracticeApi.base||'';status.textContent=window.InterviewPracticeApi.isConfigured?'已配置后端':'当前为演示模式';row.querySelector('#saveApi').addEventListener('click',()=>window.InterviewPracticeApi.save(input.value));}
}
if(location.pathname.endsWith('history.html')){
  const script=document.createElement('script');
  script.src='history.js?v=20261029-pages';
  document.body.append(script);
}
function renderCandidateName(name){
  document.querySelectorAll('.profile strong').forEach(node=>node.textContent=name||'');
  document.querySelectorAll('.profile-avatar').forEach(node=>node.textContent=name?name[0]:'');
}
if(candidateName){
  document.querySelectorAll('.profile strong').forEach(node=>node.textContent=candidateName);
  document.querySelectorAll('.profile-avatar').forEach(node=>node.textContent=candidateName[0]);
}
document.querySelectorAll('.new-button').forEach(button=>button.addEventListener('click',()=>{
  localStorage.removeItem('candidateName');
  localStorage.removeItem('resumeParsed');
  localStorage.removeItem('practiceProject');
  localStorage.removeItem('session_id');
  localStorage.removeItem('projectId');
  renderCandidateName('');
}));
