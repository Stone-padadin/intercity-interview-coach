const list=document.querySelector('.record-list');
if(list){
  list.replaceChildren();
  let records=[];
  try{records=JSON.parse(localStorage.getItem('practiceProjects')||'[]')}catch{}
  const current=localStorage.getItem('practiceProject');
  if(current){
    try{
      const project=JSON.parse(current);
      if(project?.session_id&&!records.some(record=>record.session_id===project.session_id))records.unshift(project);
    }catch{}
  }
  records.sort((a,b)=>new Date(b.updatedAt||0)-new Date(a.updatedAt||0));
  if(!records.length){
    const empty=document.createElement('div');empty.className='record-empty';
    const message=document.createElement('p');message.textContent='还没有保存的项目记录。';
    const link=document.createElement('a');link.href='resume.html';link.textContent='开始一次新练习 →';
    empty.append(message,link);list.append(empty);
  }else records.forEach(record=>{
    const card=document.createElement('div');card.className='record-card';
    const copy=document.createElement('div');copy.className='record-copy';
    const title=document.createElement('strong');title.textContent=record.projectName||record.project_name||'未命名项目';
    const detail=document.createElement('small');
    const date=record.updatedAt?new Date(record.updatedAt):null;
    const dateText=date&&!Number.isNaN(date.valueOf())?new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'long',day:'numeric'}).format(date):'日期未知';
    detail.textContent=[record.target||'未填写目标方向',record.professional||'',dateText].filter(Boolean).join(' · ');
    copy.append(title,detail);
    const open=document.createElement('a');open.href='direction.html';open.textContent='查看项目';
    open.addEventListener('click',()=>{
      localStorage.setItem('practiceProject',JSON.stringify(record));
      if(record.session_id)localStorage.setItem('session_id',record.session_id);
      if(record.id)localStorage.setItem('projectId',String(record.id));
      if(record.candidateName)localStorage.setItem('candidateName',record.candidateName);
    });
    card.append(copy,open);list.append(card);
  });
}
