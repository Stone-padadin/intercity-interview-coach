'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const store = require('../lab-store');
const { createServer } = require('../server');
const time = '2026-10-31T08:00:00.000Z';
const sample = { point: 'U1 输出对 GND', quantity: '直流电压', value: '-2.48', unit: 'V', conditions: '±5 V 供电，输入 0.5 V', retest_of: '' };
function memory() {
  const values = new Map();
  return { getItem: key => values.has(key) ? values.get(key) : null, setItem: (key, value) => values.set(key, value) };
}
function setup() {
  const storage = memory();
  store.create(storage, { name: '运放实验', background: '验证增益' }, 'experiment-a', time);
  return storage;
}
test('新实验无预置数据；核对草稿不写入，确认后可重新读取', () => {
  const storage = setup(); store.measurement(sample);
  assert.equal(store.active(store.read(storage)).measurements.length, 0);
  store.add(storage, 'experiment-a', sample, 'm1', time);
  const entry = store.active(store.read(storage)).measurements[0];
  assert.equal(entry.value, '-2.48'); assert.equal(entry.source, 'manual'); assert.equal(entry.confirmed, true);
});
test('空字段、单位混入数值和非有限数字不能保存，零和科学计数法可用', () => {
  const storage = setup();
  for (const input of [{ ...sample, point: ' ' }, { ...sample, quantity: '' }, { ...sample, unit: '' }, { ...sample, conditions: '' }, { ...sample, value: '2.48 V' }, { ...sample, value: 'Infinity' }, { ...sample, value: '1e999' }]) assert.throws(() => store.add(storage, 'experiment-a', input, 'bad', time));
  assert.equal(store.measurement({ ...sample, value: '0' }).value, '0');
  assert.equal(store.measurement({ ...sample, value: '-1.2e-3' }).value, '-1.2e-3');
  assert.equal(store.active(store.read(storage)).measurements.length, 0);
});
test('确认重试使用相同事件编号不会重复插入', () => {
  const storage = setup(); store.add(storage, 'experiment-a', sample, 'm1', time); store.add(storage, 'experiment-a', sample, 'm1', time);
  assert.equal(store.active(store.read(storage)).measurements.length, 1);
});
test('不同实验隔离，不能跨实验关联复测，确认时保留草稿所属实验', () => {
  const storage = setup(); store.add(storage, 'experiment-a', sample, 'm1', time);
  store.create(storage, { name: '第二个实验', background: '' }, 'experiment-b', time);
  assert.throws(() => store.add(storage, 'experiment-b', { ...sample, retest_of: 'm1' }, 'm2', time), /本实验/);
  store.add(storage, 'experiment-a', { ...sample, retest_of: 'm1', value: '0' }, 'm2', time);
  let state = store.read(storage);
  assert.equal(store.active(state).id, 'experiment-b'); assert.equal(store.active(state).measurements.length, 0);
  state = store.select(storage, 'experiment-a');
  assert.equal(store.active(state).measurements[1].retest_of, 'm1'); assert.throws(() => store.select(storage, 'missing'));
});
test('撤销保留原始记录，禁止关联已撤销记录，并支持恢复', () => {
  const storage = setup(); store.add(storage, 'experiment-a', sample, 'm1', time); store.retract(storage, 'experiment-a', 'm1', time);
  assert.throws(() => store.add(storage, 'experiment-a', { ...sample, retest_of: 'm1' }, 'm2', time));
  assert.match(store.markdown(store.active(store.read(storage))), /已撤销/);
  store.retract(storage, 'experiment-a', 'm1', time);
  assert.equal(store.active(store.read(storage)).measurements[0].retracted_at, null);
});
test('人工复盘按实验保存，导出有记录编号、来源和复测关联', () => {
  const storage = setup(); store.add(storage, 'experiment-a', sample, 'm1', time);
  store.add(storage, 'experiment-a', { ...sample, retest_of: 'm1', value: '0' }, 'm2', time);
  store.review(storage, 'experiment-a', { issue: '输出偏差', hypothesis: '可能接线有误', next_step: '检查输入电压', conclusion: 'M02 已复测，仍需确认原因' }, time);
  const result = store.markdown(store.active(store.read(storage)));
  for (const text of ['M01', 'M02', 'm1', '复测关联', '人工推断', '仍需确认原因', '不包含设备语音、视频证据或 AI 分析']) assert.ok(result.includes(text));
  store.create(storage, { name: '新实验', background: '' }, 'experiment-b', time);
  assert.equal(store.active(store.read(storage)).review.hypothesis, '');
});
test('损坏或未知版本数据不被新实验覆盖', () => {
  for (const raw of ['not-json', JSON.stringify({ version: 99, experiments: [] }), JSON.stringify({ version: 1, active_id: '', experiments: [{}] })]) {
    const storage = memory(); storage.setItem(store.KEY, raw);
    assert.throws(() => store.create(storage, { name: '新实验', background: '' }, 'new', time)); assert.equal(storage.getItem(store.KEY), raw);
  }
});
test('存储写入失败不报告成功，保留已存记录', () => {
  const storage = setup(); const before = storage.getItem(store.KEY);
  storage.setItem = () => { throw new Error('QuotaExceededError'); };
  assert.throws(() => store.add(storage, 'experiment-a', sample, 'm1', time), /保存失败/); assert.equal(storage.getItem(store.KEY), before);
});
test('导出转义用户输入中的 HTML 和 Markdown', () => {
  const storage = memory(); store.create(storage, { name: '<img src=x onerror=alert(1)>', background: '[伪装链接](https://example.com)' }, 'a', time);
  const output = store.markdown(store.active(store.read(storage)));
  assert.ok(!/(?<!\\)<img/.test(output)); assert.ok(output.includes('\\<img')); assert.ok(output.includes('\\[伪装链接\\]'));
});
test('默认服务提供新页面，如实声明能力，私有及历史服务文件不可下载', async t => {
  const server = createServer(); server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  assert.match(await (await fetch(base)).text(), /AI 实验台助教/);
  assert.deepEqual(await (await fetch(`${base}/api/health`)).json(), { ok: true, service: 'lab-assistant-prototype', storage: 'browser-local', voice: false, video: false, ai: false });
  for (const route of ['/server.js', '/legacy-server.js', '/package.json', '/uploads/test.docx', '/interview-practice.json', '/api/projects', '/resume.html']) assert.equal((await fetch(base + route)).status, 404, route);
  assert.equal((await fetch(`${base}/lab.js`)).headers.get('content-type'), 'text/javascript; charset=utf-8');
  const head = await fetch(base, { method: 'HEAD' }); assert.equal(head.status, 200); assert.equal(await head.text(), '');
  assert.equal((await fetch(`${base}/api/projects`, { method: 'POST', body: '{}' })).status, 405);
});
