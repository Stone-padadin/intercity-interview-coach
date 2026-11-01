# PID11919 纯语音恢复诊断 · 2026-11-01

用户暂停摄像头调试，要求优先恢复语音并完成两轮对话。SPI 预览和左转90度候选固件已在本机保留；这次没有继续运行摄像头。

## 实物观察与边界

- SPI 并发时曾出现 final ASR 和播放开始，但没有观察到播放完成，用户反馈没有声音。切回此前通过两轮的纯语音应用后，仍无新会话/转写/下行事件；因此没有把摄像头负载断言为根因。
- 整板 USB 断电五秒再上电后，用户确认开机提示音清楚。设备 online=1、record 模式确认，音频 UART 和麦克风初始化有记录，但口头唤醒测试仍未产生云会话启动事件。开机音通过不代表云端对话通过。
- 加入手动启动入口后，实物收到 `voice_start_requested`、`qm_agent_start ret=0`，语音房间连接、远端用户加入、上行首帧、final ASR、下行首帧及播放开始事件。**本记录写入时尚待用户确认实际听到的回答，两轮对话未验收。**没有以这些事件代替喇叭听感。
- 本机保留配网、账号绑定及 PID11919；仅写应用与 OTA 选择区，没有写 NVS、分区表、bootloader 或姿态模型。旧纯语音版本及 SPI 候选已保留。

## 最小改动

`b/lab/prepare_voice_start.py` 只为固定厂商 SDK 的 `apps/main/agent/agent_app.c` 加入 `agent_app_request_wakeup()`：云和 worker 就绪后，向既有 worker 信号量投递一次请求。worker 继续执行原硬件唤醒路径，CLI 任务不阻塞建立连接。不修改产品、Agent、提示词、网络或唤醒词。

安装器要求固定 SDK HEAD，检查既有 worker 和唯一锚点，发现已有扩展则拒绝覆盖。写入前保存原文件与前后 SHA256，保持行尾和其他团队修改。现有 SDK 必须先检查差异，不执行 reset/clean 或重装全套 SDK。

B lab 增加仅限本机串口的诊断命令：

```
lab bind <experiment_id>
lab mode <command_id> record
lab voice-start <unique_command_id>
```

须确认 bind 和 record 回执，且没有应用播报占用。`voice_start_requested` 只表示请求已入队；还须核对实际 start 返回值、房间/下行与听感。未绑定、非 record 或应用播报忙时拒绝；旧 SDK 没有此可选扩展时报告 `voice_start_unavailable`。它不是灵机公开 HTTP API，未加入 A 网页命令列表。

新机在已审阅的 B lab 接入基础上：

```
python b/lab/prepare_voice_start.py --sdk <SDK目录> --check
python b/lab/prepare_voice_start.py --sdk <SDK目录>
python b/lab/build.py --tools-root <本机B工具目录> --profile voice
```

已安装旧 B lab 的机器先比对并备份自己的 `b_lab.c`，仅在确认内容后同步本次文件；不要重新运行安装器覆盖 SDK。一次只允许一个串口读取程序。需两轮人工测试，不能根据模式回执自动判成功。

## 软件验证与待办

40 项 B Python 测试通过，包括安装锚点失败、已有扩展拒绝、缺少 worker 拒绝、CRLF 与既有修改保留；实际 ESP-IDF 5.4.1 纯语音构建、链接和局部烧录校验通过。测试不模拟真实声音。

下一步：保持当前房间，人工说出限定电路问题，确认第一轮听感后再提承接问题；记录第二轮下行/播放及用户听感。若手动启动可用而口头唤醒持续失效，再单独检查语音模块唤醒事件，不能把此临时入口宣称为唤醒词已修复。D 仍负责核对产品11919实际绑定的 Agent 与平台会话。
