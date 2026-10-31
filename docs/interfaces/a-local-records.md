# A 浏览器本地记录格式 v1

2026-10-31。本格式仅描述 `a/lab-store.js` 的当前原型实现，不是正式设备消息/ASR桥接协议，不替代待 A/B/D 确认的共享契约。

- 存储键：`intercity.lab-assistant.v1`，与历史面试记录隔离。
- 根字段：`version: 1`、`active_id`、`experiments[]`。
- 实验：`id`、`name`、`background`、`created_at`、`measurements[]`、`review`。
- 已确认测量：`id`、`point`、`quantity`、`value`、`unit`、`conditions`、`retest_of`、`recorded_at`、`source: manual`、`confirmed: true`、`retracted_at`。
- 数值保留输入字符串，允许有限负数、小数及科学计数法，不自动换算单位。复测只能关联本实验已有且当前未撤销的测量。
- `recorded_at` 是点击确认时的浏览器 UTC 时间；不是仪表采样、设备发生或 ASR 采集时间。实验/测量编号由浏览器随机生成。
- 草稿先校验和显示，确认后才持久化。同一测量编号重复确认不重复插入。撤销保留原始内容及撤销时间，恢复时清空撤销标记；不是不可篡改审计日志。
- 人工复盘：`issue`（观察）、`hypothesis`（候选原因）、`next_step`（下一项验证）、`conclusion`（复测发现）；保存时加 `source: manual` 与 `updated_at`。
- M01 等编号按该实验测量顺序生成用于阅读；稳定关联使用测量 `id`。

每次写入重新读取已存数据，失败则保留输入并提示；不能读取、格式不兼容时停止写入。另一个标签页更新后锁住当前操作，提示保留输入并刷新，避免沿用旧实验上下文。未实现服务器同步、导入、多人并发或跨设备恢复。

Markdown 导出只包括已保存内容，包括已撤销记录及标记，明确人工来源和没有视频/AI证据。实验名称、背景和测量文本通过 textContent 展示，导出时转义 Markdown/HTML 标记。

后续接入须另行冻结 experiment_id/event_id、来源、采集/接收时间、确认与撤回事件、设备重启边界；不要直接用本地随机字段冒充已接通的设备事件。
