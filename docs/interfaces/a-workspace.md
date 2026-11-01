# A 统一实验工作区接口 v1（本任务分支）

2026-11-01。依赖 PR #11 `51cbdff` 与 PR #13 `03dbaad`；此集成尚待团队审阅，未宣称 main 或整机已通过。

## 唯一归属与存储

- 首次空目录启动使用 `exp_a_20261101_01`；后续新建使用 `exp_` 加 UUID 的 32 位十六进制字符。编号均满足 B 的 1–64 位 ASCII 字母/数字/下划线/连字符要求。
- 已存在 `session.json` 时沿用其 `experiment_id`，不把已有 C 数据改号。默认目录为 `c/voice-camera-notes/.local/`；`--data-dir` 可显式指定另一目录。
- A 和 C 共用该目录的 `notes.sqlite3`，测量只写既有 `demo_measurements`。照片仍在 `photos/`，视频在 `media/`。A 新增 `a_experiments` 元数据与 `a_operations` 幂等回执表。
- 浏览器不再自动写正式记录。`intercity.lab-assistant.v1` 仅用于显式导入；不删除原浏览器数据，不修改旧实验和测量编号。整个导入事务失败时全部回滚；同编号冲突拒绝覆盖。
- `session.json` 是当前服务实验的启动绑定。设备事件到达后禁止网页切换实验；切换需先停止唯一桥接，重启服务，选择实验后再以新 ID 启动桥接。
- A 服务一个进程承载网页、C 接口和数据库。不要另起独立 C 服务、第二个相机采集者或串口桥接。

## A 接口

全部只允许 loopback 与匹配的 Host/Origin；不放开 CORS，不提供公网、多租户部署。所有 POST 为 JSON，写入操作需要稳定 `request_id`（允许字符同实验编号）。同 ID 相同请求返回 `deduplicated:true`，不同内容返回 409。

| 方法与路径 | 请求/结果 |
|---|---|
| `GET /api/workspace/state` | `version:2, active_id, experiments[], status, storage:server-sqlite` |
| `POST /api/workspace/experiments` | `expected_active_id, name, background`；生成新实验并切换 |
| `POST /api/workspace/select` | `expected_active_id, experiment_id`；设备绑定后拒绝切换 |
| `POST /api/workspace/measurements/draft` | `experiment_id, point, quantity, value, unit, conditions, retest_of`；手动待确认草稿 |
| `POST /api/workspace/measurements/confirm` | 上述字段及 `id, revision, user_confirmed:true`；不覆盖已确认记录 |
| `POST /api/workspace/measurements/retract` | `experiment_id, id, revision, retracted:boolean` |
| `POST /api/workspace/review` | `experiment_id, revision, review:{issue,hypothesis,next_step,conclusion}` |
| `POST /api/workspace/import` | `experiment_id, data`；完整的旧浏览器 v1 数据 |
| `GET /api/workspace/export?experiment_id=...` | Markdown，已确认测量、撤销标记、复测、原文、照片/视频引用、人工复盘及 AI 结果 |
| `GET /api/health` | 如实区分服务状态、设备事件接收、相机状态；`voice_verified:false` |

POST 成功为 `{result:...}`，重复带 `deduplicated:true`。输入无效 400，错实验/过期页面/ID 冲突 409，存储失败 500；失败不显示已保存。`revision` 是记录或复盘的版本，防止旧页面覆盖新状态。

## B 与 C 的接入

- B 仍使用 `POST /api/lab/device-events`、`GET /api/lab/device-commands?experiment_id=...`；`b.lab.v1` 和 `b.lab.command.v1` 不改。接收在数据库提交后回执；相同设备事件不重复拍照或建测量草稿。
- C 完整保留 `/api/state`、`/api/demo/*`、`/photos/*`、`/media/*`、相机与视觉端点。`GET /capture` 打开原 C 页面，和 A 同源同进程。
- A 注入同一个 `Lab` 实例给 C 的 `make_server`，使关联的视频位置和最终 ASR 使用同一上下文。该函数仅增加可选 `lab` 参数，原调用保持兼容。
- 在统一服务中，C 的测量确认也走 A 的事务；存在关联照片时同时核验照片并确认图文记录。缺失或变更照片时不确认完整图文记录。
- 非测量操作笔记仍通过 C 的笔记确认流程；不能把确认一段自由文本冒充确认结构化数值。
- 已撤销测量保留原文，A/C 页面和导出均标记，模型分析上下文排除它。
- `GET /capture?media_id=...&seconds=...` 打开对应原片位置。原片时间不冒充现场发生时间。

## 来源与时间

手动输入 `source:manual`；开发板转写 `source:user_reported, input_channel:device_asr_final`，原始 `raw_text` 与设备 `event_id` 保留；AI 为 `ai_generated` 且不自动确认。

测量值存字符串，支持有限小数/科学计数法，本轮绝对值上限 `1e12`。数值确认后不自动换单位、不改称仪器采集。`confirmed_at` 为用户点击后的服务端时间；`speech_received_at` 为转写接收时间；这些均不等于仪表采样或用户开口时刻。

对接包增加自然口述、中文数字和 60 秒内的分段补字段；仅唯一未确认的设备语音草稿可补充，保留 `speech_events[]` 和完整原句，版本变化后需要重新核对。保留 `73.3 mV`，不改成 `73.3 V`。

视频的 `seconds` 是导入片段位置，`source_seconds=source_offset_seconds+seconds` 是来源原片位置。页面跳转、取帧使用片段时间，引用和导出分别标注两种时间。

## 当前边界

这套接口的软件测试使用合成 ASR、临时数据库和随机端口。仍需 B/用户完成真人新口述、模式回执、确认和刷新回读。PR #12 的独立服务没有启动，也未静默合并其数据库或宣称平台上下文已打通。
