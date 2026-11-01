(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.LabStore = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const KEY = 'intercity.lab-assistant.v1';
  const reviewKeys = ['issue', 'hypothesis', 'next_step', 'conclusion'];
  function text(value, label, max, required = true) {
    if (typeof value !== 'string' || value.trim().length > max || (required && !value.trim())) throw new Error(`请检查${label}。`);
    return value.trim();
  }
  function read(storage) {
    const raw = storage.getItem(KEY);
    if (raw === null) return { version: 1, active_id: '', experiments: [] };
    let state;
    try { state = JSON.parse(raw); } catch { throw new Error('本地记录无法读取，已停止写入以保留原始数据。请先备份浏览器网站数据。'); }
    if (state?.version !== 1 || !Array.isArray(state.experiments) || typeof state.active_id !== 'string' ||
        !state.experiments.every(e => typeof e.id === 'string' && typeof e.name === 'string' && typeof e.background === 'string' && typeof e.created_at === 'string' && Array.isArray(e.measurements) &&
          e.measurements.every(m => ['id', 'point', 'quantity', 'value', 'unit', 'conditions', 'recorded_at'].every(k => typeof m[k] === 'string')) && e.review && reviewKeys.every(k => typeof e.review[k] === 'string'))) {
      throw new Error('本地记录版本或格式不兼容，已停止写入。请先备份原始数据。');
    }
    return state;
  }
  function active(state) { return state.experiments.find(e => e.id === state.active_id); }
  function mutate(storage, action) {
    const state = read(storage);
    action(state);
    try { storage.setItem(KEY, JSON.stringify(state)); }
    catch { throw new Error('保存失败：浏览器存储不可用或已满。输入仍保留，请导出已有记录。'); }
    return state;
  }
  function create(storage, input, id, now) {
    const name = text(input.name, '实验名称', 100);
    const background = text(input.background, '实验背景', 2000, false);
    return mutate(storage, state => {
      if (state.experiments.some(e => e.id === id)) throw new Error('实验编号重复，请重试。');
      state.experiments.push({ id, name, background, created_at: now, measurements: [], review: { issue: '', hypothesis: '', next_step: '', conclusion: '' } });
      state.active_id = id;
    });
  }
  function select(storage, id) {
    return mutate(storage, state => {
      if (!state.experiments.some(e => e.id === id)) throw new Error('实验不存在，请刷新页面。');
      state.active_id = id;
    });
  }
  function measurement(input) {
    const result = {};
    for (const [key, label, max] of [['point', '测量点', 100], ['quantity', '物理量', 60], ['value', '数值', 60], ['unit', '单位', 30], ['conditions', '测量条件', 500]]) result[key] = text(input[key], label, max);
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(result.value) || !Number.isFinite(Number(result.value))) throw new Error('数值须为有限数字，可使用负数、小数或科学计数法；单位请单独填写。');
    result.retest_of = text(input.retest_of || '', '复测关联', 100, false);
    return result;
  }
  function add(storage, experimentId, input, id, now) {
    const entry = measurement(input);
    return mutate(storage, state => {
      const experiment = state.experiments.find(e => e.id === experimentId);
      if (!experiment) throw new Error('原实验不存在，测量尚未保存。');
      if (state.experiments.some(e => e.measurements.some(m => m.id === id))) return;
      if (entry.retest_of && !experiment.measurements.some(m => m.id === entry.retest_of && !m.retracted_at)) throw new Error('复测只能关联本实验中未撤销的测量。');
      experiment.measurements.push({ ...entry, id, recorded_at: now, source: 'manual', confirmed: true, retracted_at: null });
    });
  }
  function retract(storage, experimentId, id, now) {
    return mutate(storage, state => {
      const item = state.experiments.find(e => e.id === experimentId)?.measurements.find(m => m.id === id);
      if (!item) throw new Error('测量不存在，请刷新页面。');
      item.retracted_at = item.retracted_at ? null : now;
    });
  }
  function review(storage, experimentId, input, now) {
    const result = {};
    for (const key of reviewKeys) result[key] = text(input[key], '复盘内容', 2000, false);
    return mutate(storage, state => {
      const experiment = state.experiments.find(e => e.id === experimentId);
      if (!experiment) throw new Error('实验不存在，复盘尚未保存。');
      experiment.review = { ...result, updated_at: now, source: 'manual' };
    });
  }
  function escapeMarkdown(value) { return String(value).replace(/[\\`*_{}\[\]()<>#!|~]/g, '\\$&').replace(/\r?\n/g, '  \n'); }
  function markdown(experiment) {
    const esc = escapeMarkdown;
    const lines = [`# ${esc(experiment.name)}`, '', `实验编号：${esc(experiment.id)}`, `创建时间：${esc(experiment.created_at)}`, '', '## 电路背景与目标', '', esc(experiment.background) || '未填写', '', '## 已确认测量', ''];
    experiment.measurements.forEach((m, index) => {
      const parent = experiment.measurements.findIndex(item => item.id === m.retest_of);
      lines.push(`### M${String(index + 1).padStart(2, '0')} · ${esc(m.point)}${m.retracted_at ? '（已撤销）' : ''}`, '', `- ${esc(m.quantity)}：${esc(m.value)} ${esc(m.unit)}`, `- 条件：${esc(m.conditions)}`, `- 记录时间：${esc(m.recorded_at)}（手动输入并确认，非仪表采集时间）`, `- 事件编号：${esc(m.id)}`);
      if (m.retest_of) lines.push(`- 复测关联：M${String(parent + 1).padStart(2, '0')} / ${esc(m.retest_of)}`);
      if (m.retracted_at) lines.push(`- 撤销时间：${esc(m.retracted_at)}；此条不作为有效测量。`);
      lines.push('');
    });
    if (!experiment.measurements.length) lines.push('暂无已确认测量。', '');
    for (const [key, label] of [['issue', '观察到的问题'], ['hypothesis', '候选原因（人工推断）'], ['next_step', '下一项验证'], ['conclusion', '复测后的发现']]) lines.push(`## ${label}`, '', esc(experiment.review[key]) || '未填写', '');
    lines.push('---', '来源：当前浏览器实验记录原型。测量及复盘由用户手动输入；本导出不包含设备语音、视频证据或 AI 分析，未确认草稿不会导出。', '');
    return lines.join('\n');
  }
  return { KEY, read, active, create, select, measurement, add, retract, review, markdown };
});
