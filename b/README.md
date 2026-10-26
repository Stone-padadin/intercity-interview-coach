# B · 设备主程序 语音与整机联调

本次首个交付是可独立测试的设备状态和 C 视觉快照适配器。四种产品状态为准备、面试、复盘、重练；代码输出灯光选择和低亮度 RGB 建议值。**尚未接入厂商主循环、联网回调、实际 WS2812 或面试 Agent，不能当成可烧录整机固件。**

硬件当前在朋友处，计划 10 月 27 日取回。本轮不新增网络 API、物模型属性或引脚，不把 C 的诊断串口当作正式产品接口。

## 文件与接口

- `firmware/b_device_state.h/.c`：产品状态迁移、连接状态、视觉开关、结果过期和灯色选择。由一个任务拥有状态；其他线程通过主程序现有队列交接，不能并发直接写结构体。
- `firmware/b_c_vision.h/.c`：调用实际的 `c_live_pose_get_latest`。必须同时满足 getter 返回成功、`frame_id != 0`、`valid`、`has_person`、`error == ESP_OK`、`calibration_state == C_CAL_READY`、`calibrated_raw` 已知以及 `stable_state` 已知。
- `tests/`：状态规则、无效输入、过期、C 快照适配及合成标定/去抖联调。

只用 `stable_state` 决定视觉反馈，`raw_status/raw_error` 仅为 C 的历史诊断信息。`calibrated_raw` 用于拒绝无效几何，不替换稳定结果；回正迟滞期间 raw 与 stable 不同是允许的。保留 64 位拍摄时间，严格沿用 `C_POSTURE_STALE_MS` 的 6000 ms 规则；重复轮询不会延长同一帧寿命。

## 状态与灯光提案

这是 B 的本地交互实现，状态编号、配色和提醒时机待 D 与团队审阅；不代表已批准的云端协议。

| 条件 | 显示 |
|---|---|
| 设备未连接实际所需的平台 | 低亮红 |
| 准备 | 蓝 |
| 面试 | 绿 |
| 复盘 | 紫 |
| 重练 | 青 |
| 面试/重练中启用视觉，但结果未知、未标定、无效或过期 | 低亮白 |
| 面试/重练中启用视觉，C 已确认持续偏离 | 橙 |

视觉默认关闭，D 与用户确认提醒规则后才启用。只改变视觉提示，不主动播放打断语音，不从姿态生成心理、医学或面试分数。复盘阶段不显示侧倾提醒。断连回准备并清空本地视觉开关和缓存；重连后重新确认项目及视觉选项，不宣称云会话自动恢复。

允许准备→面试→复盘→重练→复盘；任意状态→准备；重复当前状态幂等。离线不能开始面试。姿态变化不能自动切到复盘或重练。

## 接入方法 待整机实现

先由 C 的原脚本准备固定 SDK；本次没有修改或绕过 `scripts/prepare_sdk.py` 的防覆盖规则。不要把之前另一个 SDK 版本的 B 补丁直接叠加到 C 的固定版本。

主程序单一状态任务中引用 `b_device_state.h`、`b_c_vision.h`，初始化一个 `b_device_state_t`。`b_device_connection_changed` 的输入必须来自真实联网状态，`b_device_set_phase` 的调用必须来自确认后的产品流程。每次需要刷新反馈时：

```c
/* state belongs to this task; C live initialization must already have succeeded. */
uint64_t now_ms = (uint64_t)(esp_timer_get_time() / 1000);
(void)b_device_poll_c_vision(&state, now_ms);
b_device_light_t light = b_device_light(&state, now_ms);
b_device_rgb_t rgb = b_device_light_rgb(light);
/* After B verifies wiring/power and initializes the actual LED driver,
 * apply rgb only when light changes, and handle the driver return value. */
```

这段是接入示例，不是已调用灯圈的代码。固件编译时只加入 `b/firmware` 的 `.c`；使用 C 的真实头文件和上游 ESP-IDF/YOLO 类型。**`tests/stubs` 只供主机测试，绝不能放进固件 include 路径。** 正式主程序接入、SDK 构建和语音并发是下一次独立交付。

## 软件复现

按团队环境使用 Python 3.11 与 C11 编译器。先在含编译器的终端执行 C 原有测试，再执行 B 测试：

```sh
python scripts/test_c.py
python b/test_b.py
git diff --check
```

支持 MSVC `cl`、`cc`、`gcc`、`clang`，也可设置 `CC` 为编译器可执行入口。测试输出在被忽略的 `.local/`。B 的 C 快照 getter 在主机测试中是显式桩；C 的标定和去抖算法使用仓库真实实现，输入是合成几何，未运行模型或设备。

## 实机验收与队友配合

- B：取回设备后核对丝印、供电、语音模块与数据线；先做单独语音基线，再接灯光和实时视觉。不提交设备凭据、原始日志或 Flash 备份。
- C：先解决新标定版 PID/空帧问题，确认真实 `C_CAL_READY`、正坐/侧倾/回正和未知恢复；与 B 检查语音/视觉共存。
- D：确认四状态和灯色、用户是否开启提醒、何时进入复盘/重练；提供团队产品/Agent 的正规配置流程，密钥留本机。
- A：与 D 确认项目和会话数据如何进入同一练习。正式网络 API 仍需协商，本次没有创建。

通过标准：真实项目完成两轮语音→复盘→重答；C 有效持续偏离才触发灯；遮挡/重新标定/过期变未知；断网、重启可按说明恢复；视觉和音频同时运行不复位。软件测试不等于这些实机标准已通过。
