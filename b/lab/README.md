# B · AI 实验台助教软件首版

本目录是从 `origin/main d816296` 新建的实验助教增量。复用现有音频和 C 集成，产品身份由 ignored 本机配置提供，不覆盖旧工作区。当前交付是设备事件桥接和短文本播报候选；实物已验证绑定、六个阶段与时钟，真实转写/播报见 [本轮结果](VALIDATION.md)。本目录不替 A 或 D 实现实验服务、模型分析、报告或平台工作流。

用户本轮确认优先用电脑摄像头监视台面，暂不增加舵机；板子保留原接线。本候选编译为 **voice、SPI 推理关闭、LED 关闭**。C 的新分支 `feat/stone-padadin-lab-assistant-c` 已读取，主要新增诊断与摄像头实测文档，未提供产品录像服务，因此本 PR 不合入其整套文档，仅增加 B 的可复现摄像头通路检查。D 接手见 [交接说明](D-HANDOFF.md)。

## 产品切换更新 · 2026-10-31

当前调试目标是 D 新提供的 **PID 11919**，不是旧面试产品 PID 11814；不能沿用旧产品的 SECRET 或假定旧 Agent ID 2736 仍适用。新固件已编译、写入应用并收到 online=1；六个实验阶段和时钟/桥接回执通过，真实新角色应答与 final ASR 仍按 [实物记录](VALIDATION.md) 分别验收。产品密钥、备份、构建输出与采集原文留在 `.local/`。

## 这次实现

- 监听固定 SDK 的公开 `QM_AGENT_EVENT_BASE`，只复制 final ASR/TTS/Agent 文本到非阻塞队列；事件回调不跑 HTTP。串口增加 `BLAB1 ` 开头的 JSON 行。
- 每次启动随机 `boot_id`、单调序号、设备启动毫秒数、实验 ID、阶段、内容来源和截断标记。ASR 始终为 `user_reported`、`confirmed:false`，不能直接当传感器读数。TTS/Agent 文本为 `agent_generated`。
- 一个电脑进程独占串口；SQLite outbox 先落盘再发送，按事件 ID 幂等重试。时间通过往返同步估计，并标注不确定度；未同步或映射过期时保留未知。设备重启或换实验时停止，不自动沿用旧命令。
- 应用播报独立任务、最多两条等待队列，64 UTF-8 字节上限；只允许分析阶段提交。过期、取消、阶段改变和重复 ID 不再次播报。命令先持久化，写入结果不确定时不自动重试，需用户决定新命令。
- 实验阶段为 `prepare/record/analysis/review/paused/ended`。`analysis` 请求 SDK 资源让位，拒绝已知原生思考/播报中的外部请求。结束分析时由 A 显式发阶段命令。
- 独立 SDK 增量安装器：核对固定提交、全部插入位置与已有 B 集成；先备份两个目标文件，再加入 `b_lab`。已有目标或不匹配时拒绝。默认 `B_LAB_ENABLE=OFF`；不运行原来的清理/覆盖流程。

## 已知 SDK 限制，必须保留

1. 公开文本快照只有 **191 字节**正文。超长或末尾 UTF-8 不完整会标 `truncated:true`、`usable_for_confirmation:false`。A 应要求重说短句或人工补全，不能把半句生成正式测量记录。本版不修改厂商文本上限。
2. `source_agent_instance_id` 是 SDK 本地不透明会话编号，**不是平台 Agent ID 2736**。没有厂商唯一 utterance ID，无法可靠合并重复 ASR 回调；只去重传输重发的同一事件，不合并用户重复说的同一句话。
3. `agent_app_user_corpus()` 是应用 **sendSpeakRequest 播报**，不是给原生 Agent 注入上下文。`qm_agent_send_text` 在此 Agora 实现中不支持；不能据此声称上下文已打通。
4. SDK 的 `agent_app_wait_tts_complete()` 可能在播放失败后返回成功，而且公开播放事件不能可靠关联到这条自定义播报。因此只有 `submitted`、`playback_failed`、`playback_unconfirmed`、`uncorrelated_playback_observed` 等证据等级；**没有自动宣称 `played` 的状态**。最后一种也必须人工核对唯一短句。服务器原生输出无法由本模块保证完全隔离。
5. `cancel_requested` 仅表示调用了取消入口；Agora 中止能力有限，不能当作喇叭立即静音的证明。固件排队期限在执行前检查，已经发往厂商的请求不能保证过期后远端立即撤销。
6. `lab bind` 清理本地归属和排队状态，不能清除厂商的旧对话上下文。换实验前应暂停、等原生回复结束，并由 D 确认新会话流程。晚到的云端文本没有可靠服务端实验 ID，仍需 A 显示来源与用户确认。
7. 两个 SDK 任务分别使用内部 RAM 栈；新增内存开销、与 SPI 视觉并发、长时运行仍须实物测试。厂商 `qm_cli_printf` 只有 256 字节，因此本模块使用完整标准输出并加行边界，桥接启动时关闭 CLI 字符回显。SDK 日志仍可能与 JSON 串口行交错；解析失败会丢弃且不打印私密正文，应核对 `queue_drops` 与序号缺口。

## 给 A 的本地接口提案（待双方确认）

下面是 **B 这份程序的本地接口约定**，不是灵机官方 API，也不代表 A 已实现。只允许电脑 loopback HTTP，默认 `http://127.0.0.1:8000`。网页不能直接放产品密钥或打开第二个串口读取器。

### 设备事件入库

`POST /api/lab/device-events`，JSON 示例（纯合成数据）：

```json
{"schema":"b.lab.v1","event_id":"bootA-1","boot_id":"bootA","seq":1,"device_ms":1000,"experiment_id":"exp_demo","phase":"record","kind":"asr.final","data":{"text":"测试点A电压2.5伏","final":true,"truncated":false,"usable_for_confirmation":true,"confirmed":false,"source":"user_reported","source_agent_instance_id":1,"source_request_id":0,"source_generation":0,"finish_reason":0},"received_at":"2026-10-31T04:00:00+00:00","occurred_at_estimated":null,"clock_uncertainty_ms":null}
```

A 必须先持久化，再返回 `2xx {"event_id":"bootA-1","status":"accepted"}`。重复同 ID 同正文返回 `2xx` 或 `409` 加 `status:"duplicate"`，同 ID 异文不得覆写。B 没有收到匹配 ID 的确认会重试。前端以纯文本显示转写，生成**待确认项**，保留原句；正式记录的单位、位置、来源和用户确认由 A 管理。

事件类型：`asr.final/tts.final/agent.final/device.status/speech.status/clock.sync`。命令反馈的 `data.command_id` 对应下面 ID；`queue_drops` 是本次启动累计事件队列丢弃数。未知/断连/未校准不能变成“实验异常”。

### 电脑向设备发命令

`GET /api/lab/device-commands?experiment_id=exp_demo` 返回 `{"commands":[...]}`，无命令返回空列表。A 保留命令并可重复返回，B 以 ID 持久化去重。先绑定成功才拉命令。每条命令为：

```json
{"schema":"b.lab.command.v1","command_id":"cmd_unique_001","experiment_id":"exp_demo","operation":"mode","argument":"record","expires_at_ms":1793420000000}
```

`expires_at_ms` 是实际 Unix 毫秒，须大于当前电脑时间且不超过 60 秒。上例时间只是示意，运行时必须重新生成。

| operation | argument | A 的处理 |
|---|---|---|
| mode | 六个实验阶段之一 | 等 `device.status` 的匹配 ID 和 `mode_set`；检查返回 phase，失败不显示已切换 |
| speak | 1–64 UTF-8 字节的短句 | 先等分析阶段确认，再投递；一条命令一个短句，不自动拆长报告 |
| cancel | null | 使设备待执行播报失效；正在播放的真实停止结果另验 |

`speech.status` 可能为 `queued/submitted/native_output_busy/queue_full/cancelled_or_stale/cancelled/playback_failed/request_or_wait_failed/uncorrelated_playback_observed/playback_unconfirmed/duplicate_not_replayed/id_conflict`。拒绝或不确定都不要自动给新 ID 重播；让用户决定重试。音频初始化未完成时阶段命令返回 `resource_mode_unavailable`，A 不得显示切换成功。固件只缓存最近 16 条播报 ID，电脑持久化去重是主防线。电脑写串口后记录 `written_unconfirmed`，并不代替设备反馈。

## 本地运行与编译

用 Python 3.11+，安装 `requirements.txt`；测试本身只需要标准库。

```powershell
python -m unittest discover -s b/lab/tests -v
python b/lab/prepare.py --sdk C:/path/to/reviewed/vendor-sdk --check
python b/lab/prepare.py --sdk C:/path/to/reviewed/vendor-sdk
python b/lab/build.py --tools-root C:/path/to/existing-b-checkout
```

安装器只在已整合 C+B 的固定 SDK 上加入独立模块，不能对原始 SDK 直接运行，也不能对已存在的 `b_lab` 重复运行。它保留原 B/C 文件；备份位于本 checkout 的 `.local/lab-sdk-backups/`。构建为单独 `.local/build-lab`，默认语音版、LED 关闭，保留原 `.local/build-device`；不会烧录或清配网。`--profile integrated` 仅改变构建组合，不代表并发实物已通过。工具链和产品配置必须预先存在，不能把作者机器绝对路径当队友依赖。

板子可连接后，关闭原串口监视器；**先确认真实 COM 号**。由 A 创建实验并给 B 实验 ID，再运行：

```powershell
python b/lab/bridge.py --port COM7 --experiment-id exp_demo --service http://127.0.0.1:8000
```

COM7 只是历史编号。桥接不拉起 UI、不重置板子或改热点。A 未实现接口时，事件仍在私密 SQLite 队列积累，不能据此宣称网页收到了。数据库和 WAL 含用户转写，留在 `.local/lab/`，不要提交；不采集原始音频或摄像头图像。退出桥接不会自动断开平台会话；需要先由 A 发送 cancel，等待反馈并切回 paused。

## 电脑摄像头通路检查

`camera_smoke.py` 是 B 的限时诊断，不是 A 的录像服务。安装 `requirements-camera.txt` 后，关闭 Windows“相机”和其他预览，确认取景再运行：

```powershell
python b/lab/camera_smoke.py --index 0 --seconds 30
```

只打开一个相机源，输出私密 MJPG 视频、首末帧与主机接收时间，关闭相机后完整解码。时长限 1–60 秒；索引只对当前机器成立。实际参数、完整取景、仪表是否可读需看真实画面；录制通过不能替代 OCR 真值、600 秒滚动缓存、网页回放或 AI 分析。原始媒体留在 `.local/lab/camera/`。相机不能与 A/C 另一个采集进程同时打开，诊断结束后由 A 接管单一采集源。

只在桥接**未运行**时可手工诊断：`lab status`、`lab bind exp_demo`、`lab mode testmode record`、`lab sync nonce1`。正式使用保持一个串口进程。`lab speak <id> <ttl_ms> <utf8_hex>` 是串口诊断传输，既不是云端物模型也不是网页 HTTP 接口。

## 软件和实物验收

软件：运行测试与真实 ESP-IDF 编译，`git diff --check`；模拟数据不能升级为实物证据。测试涵盖文本最终性、截断、来源、错实验/过期命令、SQLite 重启和重发、时间未知/重启、HTTP 持久确认、安装器拒绝覆盖。

拿到板子后按顺序验收，每项记录通过/失败，不能仅看编译或烧录成功：

1. 保存当前已通固件/平台版本标记，保留配网；新候选失败可回原版本，不擦 NVS。
2. 启动唯一桥接，A 创建实验并切 `record`；随机说一条**之前没用过**的位置、数值和单位。网页收到完整 final 原文并保持待确认，用户确认后入记录。
3. A 切 `analysis` 并等待设备确认，发唯一短句，例如“播报校验，编号甲七”。人工确认喇叭说出了完整原句；单凭 `submitted` 不算通过。
4. 再问原生 Agent 刚才随机事实，单独验证上下文。失败时走混合路线：电脑服务管理证据和复测上下文；不要声称原生 Agent 已记住。
5. 播报时取消、重复同 ID、同 ID 异文、过期、断开电脑、设备重启、换实验；检查不会自动播放旧结果。留意原生输出争用，若无法可靠仲裁，保持人工触发短播报，不能宣称安全告警可靠。
6. 与 C 做 SPI 视觉＋语音＋电脑 USB 视频并发；先短测再长测。当前首版不新增“自动危险检测成功”的承诺。

灯圈仍由原 B runtime 控制，**本次未把旧灯色映射接到实验阶段**，也没确认当前焊接和供电。灯光作为第二反馈待 B+C 实物低亮核对后再实现。D 必须提供当前物模型导出及真实 siid/piid，才能增加一次平台设备能力调用；本串口命令不算该验收。摄像头录像和 ROI/报告由 A+C+D 完成。
