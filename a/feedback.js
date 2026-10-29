function readRuns(){try{return JSON.parse(localStorage.getItem('practiceRuns')||'[]')}catch{return []}}
const params=new URLSearchParams(location.search);
const runs=readRuns();
let currentRun=null;try{currentRun=JSON.parse(localStorage.getItem('practiceRun')||'null')}catch{}
const activeRun=runs.find(run=>run.id===params.get('runId'))||runs.find(run=>run.id===currentRun?.id);
const feedbackList=document.querySelector('#feedbackList');
if(!activeRun||activeRun.status!=='completed'){
  const empty=document.createElement('div');empty.className='flow-empty';
  const text=document.createElement('p');text.textContent='还没有完成的练习。完成一轮文字回答后，这里会显示本地演示反馈。';
  const link=document.createElement('a');link.href='practice.html';link.textContent='返回陪练 →';empty.append(text,link);feedbackList.append(empty);
}else{
  const name=activeRun.project?.projectName||activeRun.project?.project_name||'项目练习';
  document.querySelector('#feedbackTitle').textContent=`${name} · 本轮反馈`;
  document.querySelector('#feedbackMeta').textContent=`${activeRun.answers.filter(item=>item?.answer?.trim()).length} 道回答 · ${new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric'}).format(new Date(activeRun.completedAt))}`;
  document.querySelector('#reviewLink').href=`review.html?runId=${encodeURIComponent(activeRun.id)}`;
  activeRun.questions.forEach((prompt,index)=>{
    const card=document.createElement('section');card.className='flow-item';
    const heading=document.createElement('h2');heading.textContent=`${index+1}. ${prompt}`;card.append(heading);
    const answer=activeRun.answers[index]?.answer||'';
    const feedback=activeRun.feedback[index]||{};
    const fields=[['你的回答',answer||'本题未记录回答。'],['观察到的表达点',(feedback.strengths||[]).join(' ')],['可继续补充',feedback.issue||'暂无'],['建议练习',feedback.suggestion||'可结合项目细节进一步展开。']];
    fields.forEach(([label,value])=>{const wrapper=document.createElement('div');wrapper.className='flow-field';const title=document.createElement('strong');title.textContent=label;const content=document.createElement('p');content.textContent=value;wrapper.append(title,content);card.append(wrapper)});
    const severity=document.createElement('span');severity.className='flow-label';severity.textContent=feedback.severity||'演示提示';card.append(severity);
    feedbackList.append(card);
  });
  document.querySelector('#retryLink').addEventListener('click',()=>localStorage.setItem('practiceRun',JSON.stringify({...activeRun,status:'completed'})));
}
