const savedResume=JSON.parse(localStorage.getItem('resumeParsed')||'null');
const savedProject=JSON.parse(localStorage.getItem('practiceProject')||'null');
const sessionId=localStorage.getItem('session_id')||crypto.randomUUID();
localStorage.setItem('session_id',sessionId);
const form=document.querySelector('.form-list');
const confirmLink=document.querySelector('a[href="practice.html"]');
function extractResumeFields(text=''){
  const clean=text.replace(/\r/g,'');
  const line=pattern=>clean.match(pattern)?.[1]?.trim()||'';
  const projectName=line(/(?:^|\n)([^\n]{2,30}?)(?:\s*[|｜]\s*课程设计|\s*[（(]课程设计)/);
  return {
    professional:line(/(?:专业方向|专业)\s*[：:]\s*([^\n]+)/),
    target:line(/目标岗位\s*[：:]\s*([^\n]+)/),
    skills:line(/(?:编程与工具|技术栈|技能)\s*[：:]\s*([^\n]+)/),
    projectName,
    contribution:line(/个人贡献\s*[：:]\s*([\s\S]*?)(?=\n(?:技术方案|调试过程|项目结果)\s*[：:])/),
    technicalPlan:line(/技术方案\s*[：:]\s*([\s\S]*?)(?=\n(?:调试过程|项目结果)\s*[：:])/),
    debugging:line(/调试过程\s*[：:]\s*([\s\S]*?)(?=\n项目结果\s*[：:])/),
    result:line(/项目结果\s*[：:]\s*([^\n]+)/)
  };
}
const extracted=extractResumeFields(savedResume?.text||'');
const sameResume=!!savedResume&&savedProject?.resumeFile===savedResume.fileName;
const values=sameResume?{...extracted,...savedProject}:extracted;
document.querySelectorAll('.form-list input[name]').forEach(input=>{input.value=values[input.name]||''});
const projectSummary=document.querySelector('.selected-project');
if(projectSummary){
  projectSummary.querySelector('h2').textContent=values.projectName||'';
  projectSummary.querySelector('p').textContent=values.technicalPlan||'';
  const tags=projectSummary.querySelector('.tags');
  tags.replaceChildren(...(values.skills||'').split(/[、,，·\s]+/).filter(Boolean).map(skill=>{const tag=document.createElement('span');tag.textContent=skill;return tag}));
}
function field(label,key,multiline=false){const wrapper=document.createElement('label');wrapper.className='project-field';wrapper.textContent=label;const input=document.createElement(multiline?'textarea':'input');input.name=key;input.value=values[key]||'';if(key==='projectName')input.placeholder='请填写项目名称';if(multiline)input.rows=3;wrapper.append(input);return wrapper}
let projectError;
function showProjectError(message){
  if(!projectError){projectError=document.createElement('p');projectError.className='project-error';projectError.setAttribute('role','alert');document.querySelector('.project-details')?.prepend(projectError)}
  projectError.textContent=message;
}
if(form){
  const details=document.createElement('section');details.className='project-details';
  const heading=document.createElement('div');heading.className='details-heading';heading.innerHTML='<strong>项目经历确认</strong><span>可修改后保存</span>';details.append(heading);
  details.append(field('项目名称','projectName'));
  details.append(field('个人贡献','contribution',true));
  details.append(field('技术方案','technicalPlan',true));
  details.append(field('调试过程','debugging',true));
  details.append(field('项目结果','result',true));
  form.parentElement.append(details);
  const parsedNote=document.createElement('p');parsedNote.className='parsed-note';parsedNote.textContent=savedResume?'已读取刚刚上传的简历，可在这里核对识别结果。':'尚未导入简历，确认信息为空白。';details.prepend(parsedNote);
  const saveButton=document.createElement('button');saveButton.type='button';saveButton.className='quiet-button save-project';saveButton.textContent='保存修改';saveButton.addEventListener('click',async()=>{try{await saveProject();showProjectError('');saveButton.textContent='已保存';setTimeout(()=>saveButton.textContent='保存修改',1600)}catch(error){showProjectError(error.message);saveButton.textContent='保存失败';setTimeout(()=>saveButton.textContent='保存修改',1600)}});details.append(saveButton);
}
async function saveProject(){
  const data={};document.querySelectorAll('.form-list input[name],.project-field input,.project-field textarea').forEach(input=>{data[input.name]=input.value.trim()});
  if(!data.projectName){document.querySelector('.project-field input[name="projectName"]')?.focus();throw new Error('请先填写项目名称，再开始陪练。')}
  data.resumeFile=savedResume?.fileName||'';data.candidateName=savedResume?.candidateName||localStorage.getItem('candidateName')||'';data.session_id=sessionId;data.updatedAt=new Date().toISOString();localStorage.setItem('practiceProject',JSON.stringify(data));
  const records=JSON.parse(localStorage.getItem('practiceProjects')||'[]');
  const existingIndex=records.findIndex(record=>record.session_id===sessionId);
  if(existingIndex>=0)records[existingIndex]={...records[existingIndex],...data};
  else records.unshift(data);
  localStorage.setItem('practiceProjects',JSON.stringify(records));
  const payload={...data,project_name:data.projectName};delete payload.projectName;
  let response;
  try{response=await fetch(window.InterviewPracticeApi.url('/api/projects'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});}
  catch(error){localStorage.setItem('demoMode','true');return {id:'demo',...data};}
  const result=await response.json();
  if(!response.ok){localStorage.setItem('demoMode','true');return {id:'demo',...data};}
  localStorage.setItem('projectId',String(result.id));
  return result;
}
if(confirmLink)confirmLink.addEventListener('click',async event=>{event.preventDefault();try{await saveProject();showProjectError('');window.location.href=confirmLink.href}catch(error){showProjectError(error.message)}});
