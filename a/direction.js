const savedResume=JSON.parse(localStorage.getItem('resumeParsed')||'null');
const savedProject=JSON.parse(localStorage.getItem('practiceProject')||'null');
const sessionId=localStorage.getItem('session_id')||crypto.randomUUID();
localStorage.setItem('session_id',sessionId);
const form=document.querySelector('.form-list');
const confirmLink=document.querySelector('a[href="practice.html"]');
const defaults={
  projectName:'智能温控器',
  contribution:'负责 STM32 主控程序、温湿度传感器驱动、OLED 页面和 PWM 风扇控制。',
  technicalPlan:'STM32F103 + C 语言 + FreeRTOS，接入 DHT11、OLED、PWM 和串口通信。',
  debugging:'增加超时重试和数据范围校验，通过串口日志定位任务调度问题。',
  result:'稳定完成温度采集、数据显示和阈值控制，连续运行测试 8 小时未死机。'
};
function extractResumeFields(text=''){
  const clean=text.replace(/\r/g,'');
  const line=(pattern,fallback)=>clean.match(pattern)?.[1]?.trim()||fallback;
  const projectName=line(/(?:^|\n)([^\n]{2,30}?)(?:\s*[|｜]\s*课程设计|\s*[（(]课程设计)/,'智能温控器');
  return {
    professional:line(/(?:专业方向|专业)\s*[：:]\s*([^\n]+)/,'电子信息工程'),
    target:line(/目标岗位\s*[：:]\s*([^\n]+)/,'嵌入式软件开发'),
    skills:line(/(?:编程与工具|技术栈|技能)\s*[：:]\s*([^\n]+)/,'STM32 · C语言 · FreeRTOS'),
    projectName,
    contribution:line(/个人贡献\s*[：:]\s*([\s\S]*?)(?=\n(?:技术方案|调试过程|项目结果)\s*[：:])/,'负责 STM32 主控程序、传感器驱动和控制逻辑。'),
    technicalPlan:line(/技术方案\s*[：:]\s*([\s\S]*?)(?=\n(?:调试过程|项目结果)\s*[：:])/,'STM32F103 + C语言 + FreeRTOS。'),
    debugging:line(/调试过程\s*[：:]\s*([\s\S]*?)(?=\n项目结果\s*[：:])/,'通过日志定位问题并增加异常重试。'),
    result:line(/项目结果\s*[：:]\s*([^\n]+)/,'完成稳定运行测试。')
  };
}
const extracted=extractResumeFields(savedResume?.text||'');
const sameResume=savedProject&&savedResume&&savedProject.resumeFile===savedResume.fileName;
const values=sameResume?{...extracted,...savedProject}:extracted;
function field(label,key,multiline=false){const wrapper=document.createElement('label');wrapper.className='project-field';wrapper.textContent=label;const input=document.createElement(multiline?'textarea':'input');input.name=key;input.value=values[key]||defaults[key];if(multiline)input.rows=3;wrapper.append(input);return wrapper}
if(form){
  const details=document.createElement('section');details.className='project-details';
  const heading=document.createElement('div');heading.className='details-heading';heading.innerHTML='<strong>项目经历确认</strong><span>可修改后保存</span>';details.append(heading);
  details.append(field('项目名称','projectName'));
  details.append(field('个人贡献','contribution',true));
  details.append(field('技术方案','technicalPlan',true));
  details.append(field('调试过程','debugging',true));
  details.append(field('项目结果','result',true));
  form.parentElement.append(details);
  const parsedNote=document.createElement('p');parsedNote.className='parsed-note';parsedNote.textContent=savedResume?'已读取刚刚上传的简历，可在这里核对识别结果。':'尚未读取简历，将使用演示项目内容。';details.prepend(parsedNote);
  const saveButton=document.createElement('button');saveButton.type='button';saveButton.className='quiet-button save-project';saveButton.textContent='保存修改';saveButton.addEventListener('click',async()=>{try{await saveProject();saveButton.textContent='已保存';setTimeout(()=>saveButton.textContent='保存修改',1600)}catch(error){saveButton.textContent='保存失败';setTimeout(()=>saveButton.textContent='保存修改',1600)}});details.append(saveButton);
}
async function saveProject(){
  const data={professional:extracted.professional,target:extracted.target,skills:extracted.skills};document.querySelectorAll('.project-field input,.project-field textarea').forEach(input=>{data[input.name]=input.value.trim()});
  data.resumeFile=savedResume?.fileName||'';data.candidateName=savedResume?.candidateName||localStorage.getItem('candidateName')||'';data.session_id=sessionId;data.updatedAt=new Date().toISOString();localStorage.setItem('practiceProject',JSON.stringify(data));
  const payload={...data,project_name:data.projectName};delete payload.projectName;
  let response;
  try{response=await fetch(window.InterviewPracticeApi.url('/api/projects'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});}
  catch(error){localStorage.setItem('demoMode','true');return {id:'demo',...data};}
  const result=await response.json();
  if(!response.ok){localStorage.setItem('demoMode','true');return {id:'demo',...data};}
  localStorage.setItem('projectId',String(result.id));
  return result;
}
if(confirmLink)confirmLink.addEventListener('click',async event=>{event.preventDefault();try{await saveProject();window.location.href=confirmLink.href}catch(error){alert(error.message)}});
