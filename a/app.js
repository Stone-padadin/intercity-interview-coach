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
  const data=new FormData();data.append('resume',file);
  try{
    const response=await fetch(window.InterviewPracticeApi.url('/api/resume/parse'),{method:'POST',body:data});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'解析失败');
    document.querySelector('#meta').textContent=`${(result.size/1024/1024).toFixed(2)} MB · 已解析 ${result.characters} 个字符`;
    let preview=document.querySelector('#resumePreview');
    if(!preview){preview=document.createElement('pre');preview.id='resumePreview';preview.className='resume-preview';uploaded.after(preview)}
    preview.textContent=result.text.slice(0,3000);
    localStorage.setItem('resumeParsed',JSON.stringify(result));
    if(result.candidateName){
      localStorage.setItem('candidateName',result.candidateName);
      document.querySelectorAll('.profile strong').forEach(node=>node.textContent=result.candidateName);
      document.querySelectorAll('.profile-avatar').forEach(node=>node.textContent=result.candidateName[0]);
    }
    showToast('简历解析完成');
  }catch(error){
    const demo={fileName:file.name,text:'演示模式：暂未连接简历解析后端。\n请在设置页填写独立后端地址后重试。',size:file.size,characters:0,candidateName:''};
    localStorage.setItem('resumeParsed',JSON.stringify(demo));
    document.querySelector('#meta').textContent=`${(file.size/1024/1024).toFixed(2)} MB · 演示模式`;
    showToast('后端不可用，已切换到演示模式');
  }
}
if(fileInput&&drop&&uploaded){drop.addEventListener('click',()=>fileInput.click());drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragging')});drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('dragging');acceptFile(event.dataTransfer.files[0])});fileInput.addEventListener('change',()=>acceptFile(fileInput.files[0]));document.querySelector('#remove').addEventListener('click',()=>{fileInput.value='';uploaded.classList.add('hidden');drop.classList.remove('hidden');localStorage.removeItem('candidateName');localStorage.removeItem('resumeParsed');document.querySelectorAll('.profile strong').forEach(node=>node.textContent='');document.querySelectorAll('.profile-avatar').forEach(node=>node.textContent='');showToast('已移除简历')})}
const answerButton=document.querySelector('#answerButton');
if(answerButton)answerButton.addEventListener('click',event=>{event.currentTarget.textContent='录音中…';document.querySelector('#answerText').textContent='演示录音已开始，未来将接入语音识别。';showToast('演示录音已开始')});
