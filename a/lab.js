'use strict';
const $ = id => document.getElementById(id);
const store = window.LabStore;
const reviewKeys = ['issue', 'hypothesis', 'next_step', 'conclusion'];
let state = null, pending = null, editing = null, busy = false, locked = false;
let reviewRevision = 0, generation = 0, legacy = null;
let renderedRecords = '';
const retries = new Map();
const active = () => state?.experiments.find(item => item.id === state.active_id);
const formObject = id => Object.fromEntries(new FormData($(id)));

function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
  $('notice').hidden = false;
}
function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}
async function request(path, body) {
  let response;
  try {
    response = await fetch(path, body === undefined ? { cache: 'no-store' } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
  } catch { throw new Error('实验服务连接失败。输入已保留，请检查服务后重试。'); }
  let result;
  try { result = await response.json(); }
  catch { throw new Error('当前入口没有连接统一实验服务，请使用 npm start 启动后的地址。'); }
  if (!response.ok) throw new Error(result.error || '操作未完成，请保留输入后重试。');
  return result;
}
async function mutate(path, body) {
  const payload = { experiment_id: state.active_id, ...body };
  const key = JSON.stringify([path, payload]);
  if (!retries.has(key)) retries.set(key, 'web_' + crypto.randomUUID());
  const result = await request(path, { ...payload, request_id: retries.get(key) });
  retries.delete(key);
  return result.result;
}
function controls() {
  const unavailable = busy || locked || !state;
  for (const node of document.querySelectorAll('button')) node.disabled = unavailable;
  $('measurement-fields').disabled = unavailable || !active();
  $('review-fields').disabled = unavailable || !active();
  $('experiment-select').disabled = unavailable || !!state?.status.last_device_event;
  $('experiment-form').querySelector('button').disabled = unavailable || !!state?.status.last_device_event;
  $('import-browser').disabled = unavailable || !legacy?.experiments.length;
}
async function run(action) {
  if (busy || locked || !state) return;
  busy = true; generation++; controls();
  try { await action(); }
  catch (error) { notice(error.message, true); }
  finally { busy = false; controls(); }
}
function hasUnsavedInput() {
  if (!state) return false;
  const values = id => [...$(id).elements].filter(node => node.name).map(node => [node.name, node.value]);
  return pending || values('measurement-form').some(([key, value]) => key !== 'retest_of' && value.trim()) ||
    values('review-form').some(([key, value]) => value !== (active()?.review[key] || ''));
}
function canSwitch() {
  return !hasUnsavedInput() || window.confirm('当前有未保存输入。切换实验会丢弃这些输入，是否继续？');
}
function clearDraft() { pending = null; $('confirmation').hidden = true; }
function newManual() {
  editing = null; clearDraft(); $('measurement-form').reset();
  $('raw-text').hidden = true; $('new-manual').hidden = true; $('input-source').textContent = '手动输入';
}
function loadReview() {
  const experiment = active();
  for (const key of reviewKeys) $('review-form').elements.namedItem(key).value = experiment?.review[key] || '';
  reviewRevision = experiment?.revision || 0;
}
function loadDraft(item) {
  if (!canSwitch()) return;
  newManual(); editing = { ...item };
  for (const key of ['point', 'quantity', 'value', 'unit', 'conditions', 'retest_of']) {
    $('measurement-form').elements.namedItem(key).value = item[key] || '';
  }
  $('input-source').textContent = item.source === 'user_reported' ? '开发板口述 · 待确认' : '手动草稿';
  $('raw-text').textContent = item.raw_text ? '原始口述：' + item.raw_text : '这条手动草稿尚未确认。';
  $('raw-text').hidden = false; $('new-manual').hidden = false;
  $('measurement-title').scrollIntoView({ block: 'center' }); $('point').focus();
}
function renderStatus() {
  $('storage-status').textContent = '记录保存在这台电脑';
  $('experiment-id').textContent = state.active_id;
  const bridgeFailed=state.status.bridge_managed&&!state.status.bridge_running;
  const stale=state.status.last_device_event && Date.now()-Date.parse(state.status.last_device_event)>90000;
  $('device-status').textContent = bridgeFailed || stale ? '语音连接已断开 · 记录已保留' : state.status.last_device_event
    ? (state.status.record_mode_ack ? '设备已回执记录模式 · 真人语音待验收' : '收到设备事件 · 等待记录模式回执')
    : '设备语音 · 等待 B 桥接';
  controls();
}
function render() {
  const experiment = active();
  renderStatus();
  $('experiment-select').replaceChildren(...state.experiments.map(item => new Option(item.name, item.id)));
  $('experiment-select').value = state.active_id;
  $('current-name').textContent = experiment?.name || '请选择实验';
  $('current-background').textContent = experiment?.background || '尚未填写电路背景与目标。';
  const all = experiment?.measurements || [];
  const records = all.filter(item => item.confirmed), drafts = all.filter(item => !item.confirmed);
  $('record-count').textContent = `${records.filter(item => !item.retracted_at).length} 条有效 / ${records.length} 条记录`;
  $('draft-count').textContent = drafts.length + ' 条';
  $('empty-records').hidden = !!records.length; $('empty-drafts').hidden = !!drafts.length;
  $('drafts').replaceChildren();
  for (const item of drafts) {
    const article = element('article', undefined, 'record');
    article.append(element('small', item.source === 'user_reported' ? '开发板最终转写 · 本人报告' : '手动输入 · 草稿'),
      element('h3', item.point || '测量点待补充'),
      element('p', item.raw_text || `${item.quantity} ${item.value} ${item.unit}；${item.conditions}`));
    if (item.missing?.length) article.append(element('p', '请补充：' + item.missing.join('、'), 'missing-fields'));
    const note = experiment.notes.find(note => note.event_id === item.event_id);
    if (note?.photo) {
      const image = element('img'); image.className = 'draft-photo'; image.alt = '本条口述关联的照片，请核对画面与记录是否一致';
      image.src = '/photos/' + encodeURIComponent(note.photo); article.append(image);
      article.append(element('small', `画面与转写接收相差 ${note.photo_offset_ms} 毫秒；不代表开口或曝光时间。`));
    } else if (note?.capture_error) article.append(element('p', note.capture_error, 'missing-fields'));
    const button = element('button', '补充并核对', 'button secondary'); button.type = 'button';
    button.addEventListener('click', () => loadDraft(item)); article.append(button); $('drafts').append(article);
  }
  $('records').replaceChildren();
  const previousRetest = $('retest-of').value;
  $('retest-of').replaceChildren(new Option('首次测量 / 不关联', ''));
  records.forEach((item, index) => {
    const label = `M${String(index + 1).padStart(2, '0')}`;
    const article = element('article', undefined, `record${item.retracted_at ? ' retracted' : ''}`);
    const header = element('div', undefined, 'record-header');
    const source = item.source === 'user_reported' ? '本人报告 · 开发板转写' : '手动输入';
    header.append(element('small', `${label} · ${item.retracted_at ? '已撤销' : source + ' · 已确认'}`));
    const button = element('button', item.retracted_at ? '恢复记录' : '撤销记录', 'text-button'); button.type = 'button';
    button.setAttribute('aria-label', `${item.retracted_at ? '恢复' : '撤销'} ${label}`);
    button.addEventListener('click', () => run(async () => {
      await mutate('/api/workspace/measurements/retract', { id: item.id, retracted: !item.retracted_at, revision: item.revision || 0 });
      await refresh(true); notice(item.retracted_at ? '记录已恢复。' : '已撤销，原记录仍保留，可恢复。');
    }));
    header.append(button);
    article.append(header, element('h3', `${item.point} · ${item.quantity} ${item.value} ${item.unit}`),
      element('p', '条件：' + item.conditions), element('small', '确认时间：' + new Date(item.confirmed_at).toLocaleString('zh-CN', { hour12: false })));
    if (item.raw_text) article.append(element('p', '原始口述：' + item.raw_text, 'source-text'));
    if (item.retest_of) {
      const parent = records.findIndex(record => record.id === item.retest_of);
      article.append(element('p', `复测关联：${parent >= 0 ? 'M' + String(parent + 1).padStart(2, '0') : item.retest_of}`));
    }
    if (item.evidence) {
      const link = element('a', '查看视频证据 · 原片 ' + (item.evidence.source_seconds ?? item.evidence.seconds).toFixed(3) + ' 秒');
      link.href = '/capture?' + new URLSearchParams({ media_id: item.evidence.media_id, seconds: item.evidence.seconds });
      link.target = '_blank'; link.rel = 'noopener'; article.append(link);
    }
    const note = experiment.notes.find(note => note.event_id === item.event_id && note.photo);
    if (note) {
      const link = element('a', '查看关联照片'); link.href = '/photos/' + encodeURIComponent(note.photo);
      link.target = '_blank'; link.rel = 'noopener'; article.append(link);
    }
    $('records').append(article);
    if (!item.retracted_at) $('retest-of').append(new Option(`${label} · ${item.point} · ${item.value} ${item.unit}`, item.id));
  });
  if (records.some(item => item.id === previousRetest && !item.retracted_at)) $('retest-of').value = previousRetest;
  const analyses=(experiment?.analyses || []).filter(item=>item.review_status!=='superseded').slice().reverse();
  $('empty-analyses').hidden=!!analyses.length;
  $('analyses').replaceChildren();
  for(const item of analyses) {
    const article=element('article',undefined,'record analysis-record');article.dataset.analysisId=item.id;
    article.append(element('h3',({safety:'危险提醒',wiring:'接线指导',history:'历史排错'}[item.mode]||item.mode)+' · 待核对'));
    const answer=item.alert ? '可见依据：'+item.alert.evidence+'\n提醒：'+item.alert.message : item.answer;
    article.append(element('p',answer),element('small','生成时间：'+new Date(item.created_at).toLocaleString('zh-CN',{hour12:false})+' · 请求耗时 '+(item.elapsed_seconds??'未知')+' 秒'));
    for(const ref of item.evidence || []) {
      const link=element('a','查看视频证据 · 原片 '+(ref.source_seconds??ref.seconds).toFixed(3)+' 秒');
      link.href='/capture?'+new URLSearchParams({media_id:ref.media_id,seconds:ref.seconds,mode:item.mode,...(item.risk_focus?{risk_focus:item.risk_focus}:{})});
      link.target='_blank';link.rel='noopener';article.append(link);
    }
    $('analyses').append(article);
  }
  controls();
}
async function refresh(force = false) {
  const started = generation;
  const incoming = await request('/api/workspace/state');
  if (!force && started !== generation) return;
  if (state && incoming.active_id !== state.active_id && hasUnsavedInput() && !force) {
    locked = true; controls(); notice('另一页面切换了实验。输入已保留，请先复制输入，再刷新本页。', true); return;
  }
  const first = !state, switched = state && incoming.active_id !== state.active_id;
  const nextRecords = JSON.stringify([incoming.active_id, incoming.experiments]);
  state = incoming;
  if (nextRecords !== renderedRecords) { render(); renderedRecords = nextRecords; }
  else renderStatus();
  if (first || switched) { newManual(); loadReview(); }
  else if (editing) {
    const latest = active().measurements.find(item => item.id === editing.id);
    if (latest && !latest.confirmed && (latest.revision || 0) !== (editing.revision || 0)) {
      for (const key of ['point', 'quantity', 'value', 'unit', 'conditions']) {
        const field = $('measurement-form').elements.namedItem(key);
        if (!field.value.trim() && latest[key]) field.value = latest[key];
      }
      editing = { ...latest }; clearDraft();
      $('raw-text').textContent = '原始口述：' + latest.raw_text;
      notice('收到补充口述，已补齐空白字段。请重新核对后确认。');
    }
  }
}
$('experiment-form').addEventListener('submit', event => {
  event.preventDefault(); if (!canSwitch()) return;
  const input = formObject('experiment-form');
  run(async () => {
    await mutate('/api/workspace/experiments', { ...input, expected_active_id: state.active_id });
    newManual(); await refresh(true); loadReview(); $('experiment-form').reset();
    notice('实验已创建并保存在本机。请复制当前实验 ID 给 B。'); $('point').focus();
  });
});
$('experiment-select').addEventListener('change', () => {
  const ident = $('experiment-select').value;
  if (!canSwitch()) { $('experiment-select').value = state.active_id; return; }
  run(async () => {
    await mutate('/api/workspace/select', { experiment_id: ident, expected_active_id: state.active_id });
    newManual(); await refresh(true); loadReview(); notice('已切换实验。');
  });
});
$('measurement-form').addEventListener('input', clearDraft);
$('measurement-form').addEventListener('change', clearDraft);
$('measurement-form').addEventListener('submit', event => {
  event.preventDefault();
  let input;
  try { input = store.measurement(formObject('measurement-form')); }
  catch (error) { notice(error.message, true); return; }
  run(async () => {
    if (!editing) editing = await mutate('/api/workspace/measurements/draft', input);
    pending = { experiment_id: state.active_id, id: editing.id, revision: editing.revision || 0, input };
    $('draft-summary').textContent = `${input.point}\n${input.quantity}：${input.value} ${input.unit}\n测量条件：${input.conditions}\n${editing.raw_text ? '原始口述：' + editing.raw_text + '\n' : ''}尚未确认；请核对后保存。`;
    $('confirmation').hidden = false; await refresh(true); $('confirm').focus();
  });
});
$('new-manual').addEventListener('click', () => { if (canSwitch()) newManual(); });
$('revise').addEventListener('click', () => { clearDraft(); $('point').focus(); });
$('confirm').addEventListener('click', () => {
  if (!pending) return;
  const draft = pending;
  run(async () => {
    await mutate('/api/workspace/measurements/confirm', { experiment_id: draft.experiment_id, id: draft.id,
      revision: draft.revision, ...draft.input, user_confirmed: true });
    newManual(); await refresh(true); notice('测量已确认并保存在这台电脑，刷新后可回读。'); $('point').focus();
  });
});
$('review-form').addEventListener('submit', event => {
  event.preventDefault(); const review = formObject('review-form');
  run(async () => {
    const saved = await mutate('/api/workspace/review', { review, revision: reviewRevision });
    reviewRevision = saved.revision; await refresh(true); notice('人工复盘已保存。');
  });
});
$('copy-id').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(state.active_id); notice('已复制实验 ID：' + state.active_id); }
  catch { notice('请选中左侧实验 ID 手动复制。', true); }
});
$('import-browser').addEventListener('click', () => {
  if (!legacy || !window.confirm(`将导入 ${legacy.experiments.length} 个旧实验，保留原编号。现有服务端记录不覆盖，浏览器原记录不删除。是否继续？`)) return;
  run(async () => {
    const result = await mutate('/api/workspace/import', { data: legacy });
    await refresh(true); legacy = null; $('import-status').textContent = '导入完成，浏览器原记录仍保留。';
    notice(`已导入 ${result.imported_experiments} 个实验、${result.imported_measurements} 条测量，可在左侧切换查看。`);
  });
});
$('export').addEventListener('click', () => {
  if (hasUnsavedInput() && !window.confirm('未确认测量和未保存复盘不会进入导出，是否继续？')) return;
  run(async () => {
    const response = await fetch('/api/workspace/export?experiment_id=' + encodeURIComponent(state.active_id));
    if (!response.ok) throw new Error('导出失败，请检查服务后重试。');
    const url = URL.createObjectURL(await response.blob()), link = element('a');
    link.href = url; link.download = '实验复盘-' + state.active_id + '.md'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000); notice('已导出服务端保存的测量、复盘和分析引用。');
  });
});
window.addEventListener('beforeunload', event => {
  if (hasUnsavedInput()) { event.preventDefault(); event.returnValue = ''; }
});
async function start() {
  controls();
  try { await refresh(); loadReview(); }
  catch (error) { $('storage-status').textContent = '实验服务未连接'; notice(error.message, true); }
  try {
    legacy = store.read(window.localStorage);
    $('import-status').textContent = legacy.experiments.length ? `发现 ${legacy.experiments.length} 个旧实验，尚未导入。` : '此浏览器没有旧版实验记录。';
  } catch { legacy = null; $('import-status').textContent = '旧记录无法读取，已保留原数据，请先备份。'; }
  controls();
}
start();
setInterval(async () => {
  if (busy || locked || document.hidden) return;
  try { await refresh(); }
  catch { $('storage-status').textContent = '服务暂时断开 · 输入已保留'; }
}, 2000);
