const practiceProject=(()=>{
  try{return JSON.parse(localStorage.getItem('practiceProject')||'null')}catch{return null}
})();
const projectName=practiceProject?.projectName||practiceProject?.project_name||'';
const hasProject=Boolean(projectName);
const title=document.querySelector('#practiceTitle');
const breadcrumb=document.querySelector('#practiceBreadcrumb');
const question=document.querySelector('#practiceQuestion');
const answerButton=document.querySelector('#answerButton');
const backLink=document.querySelector('#projectBackLink');
const questionLabel=document.querySelector('.question-label');
if(hasProject){
  const target=practiceProject.target||'目标岗位';
  const contribution=practiceProject.contribution||'';
  const prompts=[
    `请结合你在「${projectName}」中的经历，介绍你承担的具体工作。`,
    `在「${projectName}」中，你采用了什么技术方案？为什么这样选择？`,
    `你在「${projectName}」的调试过程中遇到过什么问题，又是如何定位的？`,
    `「${projectName}」最终取得了什么结果？你如何验证它达到了目标？`
  ];
  if(title)title.textContent=`${projectName} · 项目深挖`;
  if(breadcrumb)breadcrumb.textContent=`${projectName} · 项目陪练`;
  if(question)question.textContent=prompts[0];
  if(questionLabel)questionLabel.textContent=`AI 面试官 · ${target}`;
  if(contribution&&question)question.dataset.context=contribution;
}else{
  if(title)title.textContent='尚未确认练习项目';
  if(breadcrumb)breadcrumb.textContent='等待确认项目';
  if(question)question.textContent='先返回项目确认页，选择并保存一个项目后再开始陪练。';
  if(questionLabel)questionLabel.textContent='AI 面试官';
  if(answerButton){answerButton.disabled=true;answerButton.textContent='等待项目确认';}
  if(backLink){backLink.textContent='去确认项目';backLink.href='direction.html';}
}
if(answerButton&&!hasProject)answerButton.setAttribute('aria-disabled','true');
