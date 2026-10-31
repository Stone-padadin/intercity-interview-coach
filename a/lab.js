'use strict';
const $ = id => document.getElementById(id);
const store = window.LabStore;
let state;
let pending = null;
let storage;
let locked = false;
const now = () => new Date().toISOString();
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
  $('notice').hidden = false;
}
function perform(action, message) {
  if (locked) { notice('记录已锁定，请先保留输入，再刷新页面。', true); return false; }
  try { state = action(); render(); notice(message); return true; }
  catch (error) { notice(error.message, true); return false; }
}
function clearDraft() { pending = null; $('confirmation').hidden = true; }
function formObject(id) { return Object.fromEntries(new FormData($(id))); }
function element(tag, content, className) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function render() {
  const experiment = store.active(state);
  const select = $('experiment-select');
  select.replaceChildren();
  select.disabled = !state.experiments.length;
  if (!state.experiments.length) select.append(new Option('还没有实验', ''));
  for (const item of state.experiments) select.append(new Option(item.name, item.id));
  select.value = experiment?.id || '';
  $('current-name').textContent = experiment?.name || '从一个真实实验开始';
  $('current-background').textContent = experiment ? (experiment.background || '未填写电路背景与目标。') : '创建实验后，在这里记录测量与复测。';
  $('measurement-fields').disabled = !experiment;
  $('review-fields').disabled = !experiment;
  $('export').disabled = !experiment;
  const records = experiment?.measurements || [];
  const activeCount = records.filter(item => !item.retracted_at).length;
  $('record-count').textContent = `${activeCount} 条有效 / ${records.length} 条记录`;
  $('empty-records').hidden = records.length > 0;
  $('records').replaceChildren();
  const previousRetest = $('retest-of').value;
  $('retest-of').replaceChildren(new Option('首次测量 / 不关联', ''));
  records.forEach((item, index) => {
    const label = `M${String(index + 1).padStart(2, '0')}`;
    const article = element('article', undefined, `record${item.retracted_at ? ' retracted' : ''}`);
    const header = element('div', undefined, 'record-header');
    header.append(element('small', `${label} · ${item.retracted_at ? '已撤销' : '手动输入 · 已确认'}`));
    const button = element('button', item.retracted_at ? '恢复记录' : '撤销记录', 'text-button');
    button.type = 'button';
    button.setAttribute('aria-label', `${item.retracted_at ? '恢复' : '撤销'} ${label}`);
    button.addEventListener('click', () => perform(() => store.retract(storage, experiment.id, item.id, now()), item.retracted_at ? '记录已恢复。' : '记录已撤销，仍保留在复盘中，可随时恢复。'));
    header.append(button);
    article.append(header, element('h3', `${item.point} · ${item.quantity} ${item.value} ${item.unit}`), element('p', `条件：${item.conditions}`), element('small', `记录时间：${new Date(item.recorded_at).toLocaleString('zh-CN', { hour12: false })}`));
    if (item.retest_of) {
      const parentIndex = records.findIndex(m => m.id === item.retest_of);
      article.append(element('p', `复测关联：M${String(parentIndex + 1).padStart(2, '0')}${records[parentIndex]?.retracted_at ? '（原记录已撤销）' : ''}`));
    }
    $('records').append(article);
    if (!item.retracted_at) $('retest-of').append(new Option(`${label} · ${item.point} · ${item.value} ${item.unit}`, item.id));
  });
  if (records.some(m => m.id === previousRetest && !m.retracted_at)) $('retest-of').value = previousRetest;
  // Do not overwrite unsaved review edits when another record is saved or retracted.
}
function loadReview() {
  const review = store.active(state)?.review;
  for (const key of ['issue', 'hypothesis', 'next_step', 'conclusion']) $('review-form').elements.namedItem(key).value = review?.[key] || '';
}
function hasUnsavedInput() {
  const experiment = store.active(state);
  const measurement = formObject('measurement-form');
  const review = formObject('review-form');
  return pending || Object.entries(measurement).some(([key, value]) => key !== 'retest_of' && value.trim()) ||
    Object.entries(review).some(([key, value]) => value !== (experiment?.review[key] || ''));
}
function canSwitch() { return !hasUnsavedInput() || window.confirm('当前有未保存的输入。切换实验会丢弃这些输入，是否继续？'); }
$('experiment-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!canSwitch()) return;
  if (perform(() => store.create(storage, formObject('experiment-form'), crypto.randomUUID(), now()), '实验已创建。填写一条测量，核对后保存。')) {
    $('experiment-form').reset(); $('measurement-form').reset(); clearDraft(); loadReview(); $('point').focus();
  }
});
$('experiment-select').addEventListener('change', () => {
  const id = $('experiment-select').value;
  if (!canSwitch()) { $('experiment-select').value = state.active_id; return; }
  if (perform(() => store.select(storage, id), '已切换实验。')) { $('measurement-form').reset(); clearDraft(); loadReview(); }
});
$('measurement-form').addEventListener('input', clearDraft);
$('measurement-form').addEventListener('change', clearDraft);
$('measurement-form').addEventListener('submit', event => {
  event.preventDefault();
  try {
    const input = store.measurement(formObject('measurement-form'));
    pending = { experimentId: state.active_id, id: crypto.randomUUID(), input };
    $('draft-summary').textContent = `${input.point}\n${input.quantity}：${input.value} ${input.unit}\n测量条件：${input.conditions}\n${input.retest_of ? '复测关联：' + $('retest-of').selectedOptions[0].textContent : '首次测量 / 不关联'}\n请核对后确认；现在尚未保存。`;
    $('confirmation').hidden = false; $('confirm').focus();
  } catch (error) { notice(error.message, true); }
});
$('revise').addEventListener('click', () => { clearDraft(); $('point').focus(); });
$('confirm').addEventListener('click', () => {
  if (!pending) return;
  const draft = pending;
  if (perform(() => store.add(storage, draft.experimentId, draft.input, draft.id, now()), '测量已确认并保存在当前浏览器。')) { $('measurement-form').reset(); clearDraft(); $('point').focus(); }
});
$('review-form').addEventListener('submit', event => {
  event.preventDefault();
  perform(() => store.review(storage, state.active_id, formObject('review-form'), now()), '人工复盘已保存。');
});
$('export').addEventListener('click', () => {
  if (hasUnsavedInput() && !window.confirm('未保存的测量和复盘不会包含在导出中。是否继续导出已保存内容？')) return;
  try {
    const experiment = store.active(store.read(storage));
    if (!experiment) throw new Error('没有可导出的实验。');
    const url = URL.createObjectURL(new Blob([store.markdown(experiment)], { type: 'text/markdown;charset=utf-8' }));
    const link = element('a'); link.href = url; link.download = `实验复盘-${experiment.id}.md`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notice('已导出保存的测量和人工复盘；请查看浏览器下载。');
  } catch (error) { notice(error.message, true); }
});
window.addEventListener('beforeunload', event => {
  if (state && hasUnsavedInput()) { event.preventDefault(); event.returnValue = ''; }
});
window.addEventListener('storage', event => {
  if (event.key === store.KEY || event.key === null) {
    // Keep this tab's current inputs and experiment context until the user reloads.
    locked = true;
    for (const control of document.querySelectorAll('button, fieldset, #experiment-select')) control.disabled = true;
    notice('另一个页面更改了实验记录。请先保留未保存输入，再刷新本页后继续。', true);
  }
});
try { storage = window.localStorage; state = store.read(storage); render(); loadReview(); }
catch (error) {
  locked = true;
  for (const control of document.querySelectorAll('button, fieldset, #experiment-select')) control.disabled = true;
  notice(error.message, true);
}
