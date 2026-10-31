const fileInput=document.querySelector('#file');
const drop=document.querySelector('#drop');
const uploaded=document.querySelector('#uploaded');
const toast=document.querySelector('#toast');
let toastTimer;
function showToast(message){if(!toast)return;toast.textContent=message;toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),2200)}
async function acceptFile(file){
  if(!file)return;
  if(!/[.]pdf$|[.]docx?$/.test(file.name.toLowerCase()))return showToast('请上传 PDF、DOC 或 DOCX 文件');
  if(file.size>10*1024*1024)return showToast('文件不能超过 10 MB');
  document.querySelector('#filename').textContent=file.name;
  document.querySelector('#meta').textContent=`${(file.size/1024/1024).toFixed(2)} MB · 正在解析…`;
  uploaded.classList.remove('hidden');drop.classList.add('hidden');showToast('正在解析简历…');
  async function parseWithRetry(attempt=0){
    const data=new FormData();data.append('resume',file);
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);
    try{
      const response=await fetch(window.InterviewPracticeApi.url('/api/resume/parse'),{method:'POST',body:data,signal:controller.signal});
      const result=await response.json().catch(()=>({error:'服务器返回了无法读取的响应'}));
      if(!response.ok){const error=new Error(result.error||`解析失败（HTTP ${response.status}）`);error.status=response.status;throw error}
      return result;
    }catch(error){
      const retryable=error.name==='AbortError'||!error.status||error.status===429||error.status>=500;
      if(attempt===0&&retryable){document.querySelector('#meta').textContent=`${(file.size/1024/1024).toFixed(2)} MB · 连接波动，正在重试…`;await new Promise(resolve=>setTimeout(resolve,900));return parseWithRetry(1)}
      if(error.name==='AbortError')throw new Error('解析请求超时（45 秒），请检查网络后重试');
      if(!error.status)throw new Error('暂时连接不到解析服务，请检查网络后重试');
      throw error;
    }finally{clearTimeout(timer)}
  }
  try{
    const result=await parseWithRetry();
    document.querySelector('#meta').textContent=`${(result.size/1024/1024).toFixed(2)} MB · 已解析 ${result.characters} 个字符`;
    let preview=document.querySelector('#resumePreview');
    if(!preview){preview=document.createElement('pre');preview.id='resumePreview';preview.className='resume-preview';uploaded.after(preview)}
    preview.textContent=result.text.slice(0,3000);
    document.querySelector('#retryParse')?.remove();
    localStorage.setItem('resumeParsed',JSON.stringify(result));
    if(result.candidateName){
      localStorage.setItem('candidateName',result.candidateName);
      document.querySelectorAll('.profile strong').forEach(node=>node.textContent=result.candidateName);
      document.querySelectorAll('.profile-avatar').forEach(node=>node.textContent=result.candidateName[0]);
    }
    showToast('简历解析完成');
  }catch(error){
    localStorage.removeItem('resumeParsed');
    document.querySelector('#meta').textContent=`${(file.size/1024/1024).toFixed(2)} MB · 解析失败，可重试`;
    let retry=document.querySelector('#retryParse');if(!retry){retry=document.createElement('button');retry.id='retryParse';retry.type='button';retry.className='quiet-button';retry.textContent='重试解析';document.querySelector('#uploaded').append(retry)}retry.onclick=()=>acceptFile(file);
    showToast(error.message||'解析失败，请重试');
  }
}
if(fileInput&&drop&&uploaded){drop.addEventListener('click',()=>fileInput.click());drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragging')});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('dragging');acceptFile(event.dataTransfer.files[0])});fileInput.addEventListener('change',()=>acceptFile(fileInput.files[0]));document.querySelector('#remove').addEventListener('click',()=>{fileInput.value='';uploaded.classList.add('hidden');drop.classList.remove('hidden');localStorage.removeItem('candidateName');localStorage.removeItem('resumeParsed');document.querySelectorAll('.profile strong').forEach(node=>node.textContent='');document.querySelectorAll('.profile-avatar').forEach(node=>node.textContent='');showToast('已移除简历')})}
const answerButton=document.querySelector('#answerButton');
if(answerButton)answerButton.addEventListener('click',event=>{event.currentTarget.textContent='录音中…';document.querySelector('#answerText').textContent='演示录音已开始，未来将接入语音识别。';showToast('演示录音已开始')});
