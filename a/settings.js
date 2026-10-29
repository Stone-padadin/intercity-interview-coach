const apiInput=document.querySelector('#apiBase');
const apiStatus=document.querySelector('#apiStatus');
if(apiInput&&window.InterviewPracticeApi){
  apiInput.value=window.InterviewPracticeApi.base||'';
  apiStatus.textContent=window.InterviewPracticeApi.isConfigured?'已配置后端':'当前为演示模式';
  document.querySelector('#saveApi').addEventListener('click',()=>window.InterviewPracticeApi.save(apiInput.value));
}
