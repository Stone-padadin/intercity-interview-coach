const flowStyles=document.createElement('link');flowStyles.rel='stylesheet';flowStyles.href='practice-flow.css?v=20261029-pages';document.head.append(flowStyles);
const runStorageKey='practiceRun';
const runsStorageKey='practiceRuns';
const practiceToast=document.querySelector('#toast');
let practiceToastTimer;

function readStored(key,fallback){
  try{return JSON.parse(localStorage.getItem(key)||JSON.stringify(fallback))}catch{return fallback}
}
function saveRun(run){
  localStorage.setItem(runStorageKey,JSON.stringify(run));
  const runs=readStored(runsStorageKey,[]).filter(item=>item.id!==run.id);
  runs.unshift(run);
  localStorage.setItem(runsStorageKey,JSON.stringify(runs));
}
function showPracticeToast(message){
  if(!practiceToast)return;
  practiceToast.textContent=message;practiceToast.classList.add('show');
  clearTimeout(practiceToastTimer);practiceToastTimer=setTimeout(()=>practiceToast.classList.remove('show'),2400);
}
function questionsFor(project){
  const name=project.projectName||project.project_name||'已确认项目';
  return [
    `请结合「${name}」介绍你承担的具体工作，以及你负责的部分。`,
    `在「${name}」中，你选择了什么技术方案？当时考虑了哪些取舍？`,
    `你在「${name}」的调试过程中遇到过什么问题？请说明定位和解决过程。`,
    `「${name}」最终取得了什么结果？你如何验证这个结果？`
  ];
}
function startRun(project){
  const current=readStored(runStorageKey,null);
  if(current&&current.projectSessionId===project.session_id&&current.status==='in-progress')return current;
  return {id:crypto.randomUUID(),projectSessionId:project.session_id||'',project,startedAt:new Date().toISOString(),updatedAt:new Date().toISOString(),status:'in-progress',questionIndex:0,questions:questionsFor(project),answers:[],feedback:[],mode:'mock'};
}

const project=readStored('practiceProject',null);
const projectName=project?.projectName||project?.project_name||'';
const hasProject=Boolean(projectName);
const title=document.querySelector('#practiceTitle');
const breadcrumb=document.querySelector('#practiceBreadcrumb');
const question=document.querySelector('#practiceQuestion');
const answerArea=document.querySelector('.answer-area');
const backLink=document.querySelector('#projectBackLink');
const questionLabel=document.querySelector('.question-label');
let run;

if(hasProject&&answerArea){
  run=startRun(project);
  run.questionIndex=Math.min(run.questionIndex||0,run.questions.length-1);
  saveRun(run);
  if(title)title.textContent=`${projectName} · 项目深挖`;
  if(breadcrumb)breadcrumb.textContent=`${projectName} · 项目陪练`;
  if(questionLabel)questionLabel.textContent=`文字陪练 · ${project.target||'项目追问'}`;
  const deviceLabel=document.querySelector('.device-area strong');
  const deviceStatus=document.querySelector('.device-area small');
  if(deviceLabel)deviceLabel.textContent='硬件输入区域';
  if(deviceStatus)deviceStatus.innerHTML='摄像头 / 麦克风 / 设备状态<br>等待队友模块接入';

  const textarea=document.createElement('textarea');
  textarea.id='writtenAnswer';textarea.rows=6;textarea.maxLength=5000;
  textarea.placeholder='写下你的回答…';textarea.setAttribute('aria-label','输入本题回答');
  const counter=document.createElement('small');counter.id='answerCounter';counter.textContent='0 / 5000';
  const controls=document.createElement('div');controls.className='answer-controls';
  const previous=document.createElement('button');previous.type='button';previous.className='quiet-button';previous.textContent='上一题';
  const next=document.createElement('button');next.type='button';next.className='primary-button';next.id='nextQuestion';
  const saveStatus=document.createElement('span');saveStatus.className='answer-save-status';saveStatus.textContent='自动保存到此浏览器';
  controls.append(previous,next,saveStatus);
  answerArea.replaceChildren(textarea,counter,controls);

  function renderQuestion(){
    const index=run.questionIndex;
    question.textContent=run.questions[index];
    textarea.value=run.answers[index]?.answer||'';
    counter.textContent=`${textarea.value.length} / 5000`;
    document.querySelector('#questionIndex').textContent=String(index+1);
    previous.disabled=index===0;
    next.textContent=index===run.questions.length-1?'完成本轮并查看反馈':'下一题';
  }
  textarea.addEventListener('input',()=>{
    const answer=textarea.value;
    run.answers[run.questionIndex]={question:run.questions[run.questionIndex],answer,updatedAt:new Date().toISOString()};
    run.updatedAt=new Date().toISOString();saveRun(run);
    counter.textContent=`${answer.length} / 5000`;
  });
  previous.addEventListener('click',()=>{run.questionIndex--;run.updatedAt=new Date().toISOString();saveRun(run);renderQuestion()});
  next.addEventListener('click',()=>{
    if(!textarea.value.trim()){showPracticeToast('先写下本题回答，再继续。');textarea.focus();return}
    if(run.questionIndex<run.questions.length-1){run.questionIndex++;run.updatedAt=new Date().toISOString();saveRun(run);renderQuestion();return}
    run.status='completed';run.completedAt=new Date().toISOString();
    run.feedback=run.questions.map((prompt,index)=>makeMockFeedback(prompt,run.answers[index]?.answer||'',run.project));
    saveRun(run);location.href=`feedback.html?runId=${encodeURIComponent(run.id)}`;
  });
  renderQuestion();
}else{
  if(title)title.textContent='尚未确认练习项目';
  if(breadcrumb)breadcrumb.textContent='等待确认项目';
  if(question)question.textContent='先返回项目确认页，选择并保存一个项目后再开始陪练。';
  if(questionLabel)questionLabel.textContent='文字陪练';
  const answerButton=document.querySelector('#answerButton');
  if(answerButton){answerButton.disabled=true;answerButton.textContent='等待项目确认';}
  if(backLink){backLink.textContent='去确认项目';backLink.href='direction.html';}
}

function makeMockFeedback(prompt,answer,projectData){
  const trimmed=answer.trim();
  const mentionsOwnership=/我(负责|主要|参与|完成|设计|实现|承担)/.test(trimmed);
  const hasEvidence=/\d+\s*(%|％|ms|秒|小时|次|个|项|人|℃|°C)/i.test(trimmed);
  const hasReason=/因为|因此|所以|通过|为了|采用|验证|对比/.test(trimmed);
  const strengths=[];
  if(mentionsOwnership)strengths.push('回答提到了个人承担的工作，有助于区分个人贡献与团队成果。');
  if(hasEvidence)strengths.push('回答包含可核对的数字或结果，可以继续说明测量条件和验证方法。');
  if(hasReason)strengths.push('回答说明了做法与原因，建议补充关键决策依据。');
  if(!strengths.length)strengths.push('已记录本题回答。可以进一步补充你亲自负责的内容和具体例子。');
  const gaps=[];
  if(!mentionsOwnership)gaps.push('个人贡献还不够明确。');
  if(!hasEvidence)gaps.push('缺少可验证的数据或结果。');
  if(!hasReason)gaps.push('问题处理或技术选择的原因尚未展开。');
  const suggestion=mentionsOwnership&&hasEvidence&&hasReason
    ?'尝试按“背景与目标、个人行动、验证结果”组织表达，并准备一个可以继续追问的技术细节。'
    :`围绕「${projectData.projectName||projectData.project_name||'该项目'}」补充一段具体例子：当时的问题是什么、你做了什么、结果如何验证。`;
  return {quote:trimmed,issue:gaps.length?gaps.join(' '):'当前演示检查未发现上述表达要素的明显缺项。',suggestion,severity:gaps.length?'建议补充':'表达较完整',strengths,createdAt:new Date().toISOString(),mode:'mock'};
}
