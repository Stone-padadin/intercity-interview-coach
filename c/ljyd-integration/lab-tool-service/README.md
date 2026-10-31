# 实验记录工具服务

Python 3.11+ 标准库，无第三方依赖。实际SQLite持久化；不包含模型、摄像头、串口、录像采集或公网部署。未知电路不预填参考值。测试中的数值仅为合成测试输入，不是用户实测。

## 启动

在本目录运行（先核实端口是否占用；重启时沿用既有数据目录）：

```powershell
python server.py --host 127.0.0.1 --port 8765
```

建议8765端口，可用 `--port` 改。默认数据库 `.local/lab.sqlite3`，证据根目录 `.local/evidence`。可用 `--data-dir` 与 `--evidence-root` 指定。每次启动沿用相同数据库。

鉴权优先读取环境变量 `LAB_TOOL_TOKEN`（至少24字符）。未设置时首次启动在 `.local/token` 生成随机凭据并复用，永不打印。token文件只用于本机集成，不能提交、展示截图或写进公共配置。Windows目录权限由宿主管理，不宣称POSIX mode可替代Windows权限保护。

除本机 `GET /health` 外全部请求需要 `Authorization: Bearer <凭据>`。`GET /health` 仅报告服务状态和 `visual_analysis:false`，不返回实验或密钥。所有业务读取也使用POST。拒绝带Origin的浏览器跨站请求；用于平台后端到后端调用，不直接暴露给任意网页。

本程序只允许本机监听。灵机云端不能直接访问电脑的127.0.0.1；需要主代理另外配置经授权的公网HTTPS反向代理/部署、鉴权与可达性。此前已通过临时HTTPS隧道验证灵机真实调用，但临时隧道已断开；目前不能视为持续公网部署。反向代理应拦截无鉴权health路径；服务看到隧道连接来自本机，不能仅凭client_address认定原始访问者在本机。

## REST接口

所有接口 `Content-Type: application/json`，POST JSON参数。

| 路径 | 工具 | 作用 |
|---|---|---|
| `/v1/experiments/create` | experiment_create | 创建实验；同一服务只允许一个活动实验 |
| `/v1/experiments/current` | experiment_current | 当前活动实验，空时data为null |
| `/v1/experiments/end` | experiment_end | 结束实验，结束后禁止新写入 |
| `/v1/measurements/draft` | measurement_draft | 用户口述草稿 |
| `/v1/measurements/confirm` | measurement_confirm | 用户明确确认后入正式查询 |
| `/v1/measurements/update` | measurement_update | 修改并恢复待确认，保留旧版 |
| `/v1/measurements/list` | measurement_list | 默认只列已确认，可include_drafts |
| `/v1/evidence/register` | evidence_register | 登记真实文件元数据和SHA256 |
| `/v1/evidence/list` | evidence_list | 证据元数据 |
| `/v1/evidence/query` | evidence_query | 按描述/文件名文字及时间区间过滤 |

也可统一使用 `POST /v1/actions`：`{"action":"measurement_list","arguments":{"experiment_id":"当前真实实验ID"}}`。

成功返回 `{ok, experiment_id, action, data, event_id, source, received_at}`。业务无效返回HTTP400，鉴权失败401，文件/存储失败500。字段和时区均校验。

### 最小真实记录流程

1. 创建：`{"name":"用户确认的实验名称"}`，取 `data.id` 作为experiment_id。不要每次请求新建实验。
2. 草稿：

```json
{
  "experiment_id": "从创建返回的真实ID",
  "event_id": "来自语音最终事件的稳定唯一ID",
  "point": "用户口述测量点",
  "quantity": "voltage",
  "value": 3.27,
  "unit": "V",
  "conditions": "用户提供的实际条件",
  "raw_text": "仅为示例：实际调用须填用户原始口述"
}
```

以上3.27为接口示例，不能预置为实际测量或正常参考值。可选 `occurred_at` 必须带时区；未提供时保留null，接收时间不冒充发生时间。

3. 向用户复述并征求确认。确认后POST confirm：

```json
{"experiment_id":"真实ID","event_id":"确认事件稳定ID","measurement_id":"草稿返回data.id","user_confirmed":true}
```

4. 查询：`{"experiment_id":"真实ID"}`。草稿在默认list中不可见。
5. 修正：带新的event_id和measurement_id提交变更字段；修改后再次确认。修订记录保存在SQLite revisions表。

`event_id`保证草稿、确认、修改和证据登记幂等：相同ID及相同完整请求返回缓存并附 `deduplicated:true`；同ID不同请求或不同实验直接拒绝。实验创建可由调用方指定唯一experiment_id防止重复建号，但不接受不同名称复用ID；结束操作不是可重放幂等操作，客户端应先查状态。全部写入使用单事务，避免并发重复事件。

来源测量固定 `user_reported`，不会误称自动仪表采集。`user_confirmed`是调用方对用户实际确认的记录，服务本身无法证明模型是否真实征求了同意；平台提示词必须明确禁止自行确认。

## 灵机实验会话网关（已真实联调）

`POST /v1/context` 请求体 `{}`，返回 `context.current_experiment / records / pending / evidence`。`records`仅已确认，`pending`为待确认。

`POST /v1/assistant` 请求体：

```json
{"action":"read","arguments":{},"user_text":"用户本轮原话","request_id":"可选稳定事件编号"}
```

允许 `read/create/draft/confirm/update/end`。创建参数为name；草稿为point/quantity/value/unit/conditions；确认可以无参数定位最后一条待确认；修改可带measurement_id与更正字段。后台解析活动实验，不由模型猜ID。草稿保留user_text为raw_text；明确确认短语才允许confirm，否定确认不执行。明确短语“确认保存”“结束实验”也能纠正模型误判为read。若提供request_id，同一操作重复请求返回deduplicated，不生成重复记录；平台暂无稳定语音事件ID时省略后由服务生成，不承诺跨平台网络重试自动去重。

返回 `{ok,action,request_id,result,context,source}`。非法请求HTTP400，不能当成功。action计划只代表意图，result才是执行依据。当前为单设备/单活动实验服务，尚未实现多租户设备隔离。

2026-10-31在灵机工作流381真实验证：创建“平台接入验证”→口述明确标记的合成测试TP_TEST/1.23伏/空载→待确认→确认保存→新一轮查询→结束实验。测试记录保留并已结束，不作为实际电路采样。生产硬件语音闭环尚未验证。平台工作流由上下文HTTP→JSON规划LLM→执行HTTP→回执LLM→回复构成；公网目前使用临时Pinggy隧道，断线需更新两个HTTP节点地址，不可视为稳定部署。

工具审计文件在数据库同目录 `tool-audit.jsonl`，仅记录timestamp、合法tool、status、transport，不记录参数、结果、凭据。应结合平台运行时间窗口核验调用来源。

## 证据边界

登记 `path`必须在配置的evidence-root里且真实存在。返回相对路径、字节数、SHA256、文件修改时间及登记时间，不返回文件内容。不会下载远程文件，也不会上传本地录像。

`start_at/end_at`是调用方提供的发生区间，均标记 `time_source:user_supplied`，不把文件修改时间当录像发生时间。查询按区间重叠；无发生时间的文件不命中带时间条件的查询。描述匹配为简单大小写不敏感子串过滤，**不是视频语义检索或视觉分析**。结果始终有 `analysis_status:not_analyzed`。

示例：先把真实录像放入evidence-root，再登记：

```json
{"experiment_id":"真实ID","event_id":"录像登记稳定ID","path":"真实片段.mp4","description":"由用户标注的接线调整","start_at":"2026-10-31T16:00:00+08:00","end_at":"2026-10-31T16:00:30+08:00"}
```

原始文件只留本地；注册后文件可被外部改动，已登记哈希代表登记时状态，后续分析必须重新校验哈希并验证文件仍存在。当前无模型分析入口，不应宣传AI已看过录像。

## MCP协议

提供两种MCP传输，共用同一SQLite数据及工具实现：

- **Streamable HTTP JSON模式**：`POST /mcp`，无会话状态，不使用Mcp-Session-Id；`GET /mcp`返回405。请求返回application/json JSON-RPC2.0，通知返回202空体。
- **旧版HTTP+SSE**：带Bearer鉴权 `GET /sse`，收到 `event:endpoint` 及 `/messages?session_id=...`。随后向该消息地址POST JSON-RPC，HTTP返回202；相应JSON-RPC结果通过原SSE连接的 `event:message` 返回。通知不产生结果事件。配对端点也需要相同Bearer鉴权。平台自定义MCP Server URL可填经部署后的 `/sse`。

支持 `initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`。初始化支持请求协议版本2024-11-05、2025-03-26和2025-06-18；未知版本时旧SSE回退2024-11-05、Streamable回退2025-03-26。支持的能力仅工具，不声明资源、提示词、订阅或采样能力。

SSE每秒发送keepalive注释，单连接最长30分钟，到期或断开后须重新GET并初始化；最多32个会话，每会话队列64条，不提供断线事件重放。无效/过期会话POST返回404，队列满返回503。session_id只用于路由，不能代替Bearer鉴权。事件endpoint使用根相对 `/messages` 地址，反向代理必须把 `/sse` 与 `/messages` 放在同一站点根路径，关闭缓冲并允许长连接。不要把session_id写入公开日志。

工具schema与REST字段完全一致，由 `tools/list`提供；工具调用结果为MCP text content包裹业务JSON，工具业务错误 `isError:true`。本机已用真实HTTP SSE连接验证初始化、工具发现、草稿写入、确认及查询；也保留Streamable HTTP测试。上述为本机协议测试；原会话曾验证灵机文字工作流通过 REST 网关调用，本次未复测云端 MCP 业务调用。

## 灵机HTTP节点最小配置

1. 先调用 `experiment_current`取得活动实验ID（必须先创建并明确绑定本次演示实验）。
2. HTTP节点POST `/v1/measurements/list`，请求体从上游变量引用该ID，不写死上个实验。
3. 请求头设置Content-Type及Bearer凭据，避免把真实凭据放入公开导出。
4. 将节点text输出作为LLM证据变量；LLM只据已确认记录回答，缺数据明说缺失。
5. 下一轮仍重新查同一实验，不能仅依赖隐式记忆；切实验必须切换映射。
6. 工作流应区分HTTP非200或业务ok:false，不把报错文本当成功证据。

## 测试

```powershell
python -m unittest -v test_server
```

15项测试覆盖（2026-10-31更新）：实验会话网关真实HTTP、明确确认/否定、请求重试、上下文隔离、审计隐私与并发，以及真实SQLite重开持久化、确认/修订、事件去重、实验隔离、结束拒写、真实文件与时间筛选、HTTP鉴权、REST、Streamable MCP，以及旧SSE初始化/工具发现/草稿写入/确认/查询。HTTP仅在测试期间临时监听127.0.0.1随机端口，finally关闭，不影响正式8765服务。

测试数据使用独立的 ignored `.local/tests/run_*`，不触碰正式数据库。迁移后 15 项测试已重新通过；受限环境若禁止回环连接，需要在宿主允许本机 socket 的环境执行。
