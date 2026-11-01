/* All video playback is muted. No speech synthesis or device-output calls. */
(() => {
  const el = id => document.getElementById(id), video = el('sourceVideo');
  let assets = [], active = '', busy = false, watching = false, watchCalls = 0;
  const measurements = new Map(), analyses = new Set();
  video.muted = true;
  video.onvolumechange = () => { if (!video.muted) video.muted = true; };
  const status = text => { el('demoProgress').textContent = text; };
  async function post(path, body) {
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '操作未完成。');
    return result;
  }
  function stopWatch() { watching=false;el('watchSafety').disabled=false;el('stopSafety').disabled=true; }
  function clearRisk() { el('riskBanner').textContent='';el('riskBanner').className=''; }
  for(const id of ['analysisMode','riskFocus']) el(id).onchange=()=>{stopWatch();clearRisk();status('检查目标已更改；旧分析保留在下方证据卡片。');};
  el('stopSafety').onclick=stopWatch;
  el('mediaSelect').onchange=()=>{
    stopWatch();clearRisk();video.pause();status('');active=el('mediaSelect').value;video.muted=true;
    const asset=assets.find(item=>item.id===active);
    if(asset) {
      video.src='/media/'+active+'.mp4';
      el('mediaInfo').textContent=asset.title+' · '+asset.author+' · '+asset.duration_seconds.toFixed(1)+' 秒 · 原片起点 '+(asset.source_offset_seconds||0)+' 秒 · '+(asset.real_footage_claimed?'用户标记实拍，内容仍须核验':'素材类型待核验');
    } else {video.removeAttribute('src');el('mediaInfo').textContent='';}
  };
  video.onerror=()=>{stopWatch();status('视频不能播放。请使用 H.264 编码的 MP4，并检查文件是否缺失。');};
  el('importMedia').onclick=async()=>{
    const file=el('mediaFile').files[0];
    if(!file||!el('mediaPermission').checked){status('请选择 MP4 并确认来源与使用方式。');return;}
    const button=el('importMedia');button.disabled=true;
    try {
      const query=new URLSearchParams({title:el('mediaTitle').value,author:el('mediaAuthor').value,source_url:el('mediaSource').value,local_use_confirmed:'true',real_footage_confirmed:'true'});
      status('正在导入并检查视频解码……');
      const response=await fetch('/api/demo/media?'+query,{method:'POST',headers:{'Content-Type':'video/mp4'},body:file});
      const data=await response.json();if(!response.ok)throw new Error(data.error);
      await refresh();el('mediaSelect').value=data.id;el('mediaSelect').onchange();status('已导入本机；尚未发送给模型。');
    }catch(e){status(e.message);}finally{button.disabled=false;}
  };
  el('bindVideo').onclick=async()=>{
    try {
      if(!active)throw new Error('请先选择视频。');
      const data=await post('/api/demo/context',{media_id:active,seconds:video.currentTime});
      el('boundContext').textContent='下一条口述关联：原片 '+data.source_seconds.toFixed(3)+' 秒（用户选定，不是实时拍摄时刻）。';
    }catch(e){status(e.message);}
  };
  function showAnalysis(item) {
    if(analyses.has(item.id))return;analyses.add(item.id);
    const article=document.createElement('article');article.className='analysis-card';
    const title=document.createElement('h3');title.textContent=({safety:'危险提醒',wiring:'接线指导',history:'历史排错'}[item.mode]||item.mode)+' · AI 生成待核对';article.append(title);
    const body=document.createElement('pre');body.textContent=item.alert
      ? '检查结果：'+({risk:'发现目标风险',clear:'当前帧未见目标风险',unknown:'无法判断'}[item.alert.status]||'无法判断')+'\n可见依据：'+item.alert.evidence+'\n提醒：'+item.alert.message
      : item.answer;article.append(body);
    const time=document.createElement('p');time.textContent='实际请求耗时 '+(item.elapsed_seconds??'未知')+' 秒；原片播放位置 '+(item.source_playhead??item.playhead).toFixed(3)+' 秒';article.append(time);
    for(const ref of item.evidence) {
      const button=document.createElement('button');button.className='secondary';button.textContent='查看原片证据 '+(ref.source_seconds??ref.seconds).toFixed(3)+' 秒';
      button.onclick=()=>{stopWatch();video.pause();el('mediaSelect').value=ref.media_id;el('mediaSelect').onchange();video.addEventListener('loadedmetadata',()=>{video.currentTime=ref.seconds;},{once:true});};
      const image=document.createElement('img');image.alt='分析所用证据，原片 '+(ref.source_seconds??ref.seconds).toFixed(3)+' 秒';image.src='/api/demo/frame?id='+encodeURIComponent(ref.media_id)+'&seconds='+ref.seconds;
      article.append(button,image);
    }
    el('analysisResults').prepend(article);
  }
  async function analyze(mode) {
    if(busy)return;
    if(!active||!el('demoConsent').checked){stopWatch();status('先选择视频并明确允许发送画面。');return;}
    busy=true;el('analyzeVideo').disabled=true;
    for(const id of ['mediaSelect','analysisMode','riskFocus'])el(id).disabled=true;
    const requested=video.currentTime;
    try {
      status('正在分析原片 '+requested.toFixed(3)+' 秒；只使用此前已出现的画面……');
      const data=await post('/api/demo/analyze',{media_id:active,mode,risk_focus:el('riskFocus').value,playhead:requested,start:mode==='history'?Number(el('historyStart').value):requested,question:el('demoQuestion').value,materials:el('demoMaterials').value,upload_confirmed:true});
      showAnalysis(data);
      status('分析完成，用时 '+data.elapsed_seconds+' 秒。');
      if(mode==='safety'&&data.media_id===active&&data.risk_focus===el('riskFocus').value) {
        const alert=data.alert;el('riskBanner').textContent=alert.message+' '+alert.evidence;
        el('riskBanner').className='risk-'+alert.status;
        if(alert.status!=='clear') {video.pause();stopWatch();}
      }
    }catch(e){stopWatch();status(e.message);}
    finally{busy=false;el('analyzeVideo').disabled=false;for(const id of ['mediaSelect','analysisMode','riskFocus'])el(id).disabled=false;}
  }
  el('analyzeVideo').onclick=()=>analyze(el('analysisMode').value);
  el('watchSafety').onclick=async()=>{
    if(busy||!active||!el('demoConsent').checked){status('先选择视频、允许画面发送，并等待当前分析结束。');return;}
    watching=true;watchCalls=0;el('watchSafety').disabled=true;el('stopSafety').disabled=false;
    try{video.muted=true;await video.play();}catch(e){stopWatch();status('请先手动播放视频。');return;}
    while(watching&&!video.ended&&watchCalls<5) {
      watchCalls++;await analyze('safety');
      if(watching)await new Promise(resolve=>setTimeout(resolve,1000));
    }
    if(watching)status('本次顺序检查已结束（最多 5 次调用）；未检查的画面不表示安全。');
    stopWatch();
  };
  function showMeasurement(item) {
    let card=measurements.get(item.id);
    if(!card) {
      card=document.createElement('article');card.className='measurement-card';
      const heading=document.createElement('h3');heading.textContent='开发板最终转写 · 待本人确认';card.append(heading);
      const raw=document.createElement('p');raw.className='raw-transcript';raw.textContent='原始口述：'+item.raw_text;card.append(raw);
      const missing=document.createElement('p');missing.className='missing';card.append(missing);
      for(const [key,label] of [['point','测量位置'],['value','数值'],['unit','单位（V/mV/A/mA/Ω/kΩ）'],['conditions','测量条件']]) {
        const field=document.createElement('label');field.textContent=label;
        const input=document.createElement('input');input.dataset.field=key;input.value=item[key]??'';field.append(input);card.append(field);
      }
      const button=document.createElement('button');button.textContent='我已核对，确认保存';
      button.onclick=async()=>{
        const fields=Object.fromEntries([...card.querySelectorAll('input')].map(input=>[input.dataset.field,input.value]));
        try{button.disabled=true;const saved=await post('/api/demo/measurements/confirm',{id:item.id,...fields,user_confirmed:true});showMeasurement(saved);status('测量已确认保存。');}
        catch(e){button.disabled=false;status(e.message);}
      };
      card.append(button);measurements.set(item.id,card);
      if(measurements.size===1)el('measurements').replaceChildren();
      el('measurements').prepend(card);
    }
    card.querySelector('.missing').textContent=item.confirmed?'已确认 · 来源仍为用户口述':item.missing.length?'需要补充：'+item.missing.join('、'):'字段已提取，请核对原片与口述后确认。';
    card.querySelector('.raw-transcript').textContent='原始口述：'+item.raw_text;
    if(!item.confirmed)for(const input of card.querySelectorAll('input'))if(!input.value&&document.activeElement!==input)input.value=item[input.dataset.field]??'';
    if(item.confirmed) {
      card.querySelector('h3').textContent='已确认测量 · 可刷新回读';
      for(const input of card.querySelectorAll('input')){input.value=item[input.dataset.field];input.disabled=true;}
      card.querySelector('button').disabled=true;
    }
  }
  el('exportDemo').onclick=async()=>{
    const response=await fetch('/api/demo/export');if(!response.ok){status('导出失败。');return;}
    const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='实验记录与证据.md';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  let refreshing=false;
  async function refresh() {
    if(refreshing)return;refreshing=true;
    try {
      const response=await fetch('/api/demo/state');if(!response.ok)throw new Error();const data=await response.json();
      if(JSON.stringify(data.media.map(a=>a.id))!==JSON.stringify(assets.map(a=>a.id))) {
        assets=data.media;el('mediaSelect').replaceChildren(new Option('请选择素材',''),...assets.map(a=>new Option(a.title,a.id)));el('mediaSelect').value=active;
      }
      for(const item of [...data.measurements].reverse())showMeasurement(item);
      for(const item of [...data.analyses].reverse())showAnalysis(item);
    }catch(e){status('演示服务未响应，请检查本机程序。');}finally{refreshing=false;}
  }
  refresh();setInterval(refresh,1500);
})();
