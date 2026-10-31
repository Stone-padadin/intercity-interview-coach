function readReviewRuns(){try{return JSON.parse(localStorage.getItem('practiceRuns')||'[]').filter(run=>run.status==='completed')}catch{return []}}
const completedRuns=readReviewRuns();
const reviewParams=new URLSearchParams(location.search);
const selectedRun=completedRuns.find(run=>run.id===reviewParams.get('runId'))||completedRuns[0];
const reviewList=document.querySelector('#reviewList');
const runSelector=document.querySelector('#runSelector');
if(!completedRuns.length){
  const empty=document.createElement('div');empty.className='flow-empty';
  const text=document.createElement('p');text.textContent='还没有完成的练习复盘。先完成一轮文字陪练。';
  const link=document.createElement('a');link.href='practice.html';link.textContent='开始文字陪练 →';empty.append(text,link);reviewList.append(empty);
}else{
  completedRuns.forEach(run=>{
    const item=document.createElement('a');item.className=`run-link${run.id===selectedRun.id?' active':''}`;item.href=`review.html?runId=${encodeURIComponent(run.id)}`;
    const copy=document.createElement('span');const name=document.createElement('strong');name.textContent=run.project?.projectName||run.project?.project_name||'项目练习';
    const date=document.createElement('small');date.textContent=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric'}).format(new Date(run.completedAt));copy.append(name,date);
    const count=document.createElement('b');count.textContent=`${run.answers.filter(answer=>answer?.answer?.trim()).length} 道回答`;item.append(copy,count);runSelector.append(item);
  });
  const projectName=selectedRun.project?.projectName||selectedRun.project?.project_name||'项目练习';
  document.querySelector('#reviewSubtitle').textContent=`${projectName} · 查看每道问题、你的回答和本轮演示反馈。`;
  document.querySelector('#reviewMeta').textContent=`完成于 ${new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(selectedRun.completedAt))}`;
  document.querySelector('#retryLink').addEventListener('click',()=>localStorage.setItem('practiceRun',JSON.stringify({...selectedRun,status:'completed'})));
  selectedRun.questions.forEach((prompt,index)=>{
    const card=document.createElement('section');card.className='flow-item';
    const heading=document.createElement('h2');heading.textContent=`${index+1}. ${prompt}`;card.append(heading);
    const answer=document.createElement('div');answer.className='flow-field';const answerLabel=document.createElement('strong');answerLabel.textContent='你的回答';const answerText=document.createElement('p');answerText.textContent=selectedRun.answers[index]?.answer||'本题未记录回答。';answer.append(answerLabel,answerText);card.append(answer);
    const feedback=selectedRun.feedback[index]||{};
    const fields=[['表达亮点',(feedback.strengths||[]).join(' ')||'本轮没有生成演示反馈。'],['可继续补充',feedback.issue||'暂无'],['下一次尝试',feedback.suggestion||'结合项目细节继续练习。']];
    fields.forEach(([label,value])=>{const wrapper=document.createElement('div');wrapper.className='flow-field';const title=document.createElement('strong');title.textContent=label;const text=document.createElement('p');text.textContent=value;wrapper.append(title,text);card.append(wrapper)});
    reviewList.append(card);
  });
}
