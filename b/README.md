# B · 设备主程序 语音与整机联调

本次交付包含四态设备逻辑、C视觉快照适配器，以及已接入SDK主程序的单任务运行层、真实云连接事件和可选WS2812驱动。语音基线及B+C整合版已在本机编译通过；平台Agent工作流仍待接入，不能据此宣称整机语音和灯光已经验收。

10月27日已取得硬件并识别COM7上的ESP32-S3、16MB Flash和8MB PSRAM。相机预览已在实物上运行；语音板、麦克风和喇叭已连接，用户确认开机提示音清楚，日志有麦克风数据与离线唤醒事件。10月29日正坐标定及独立样本记录见[当前联调交接](integration-20261029.md)；灯圈仍未焊接。本轮不新增网络API、物模型属性或引脚，不把C诊断串口当作正式产品接口。

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

## SDK接入与本机构建

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

这段是接入示例，不是已调用灯圈的代码。固件编译时只加入 `b/firmware` 的 `.c`；使用 C 的真实头文件和上游 ESP-IDF/YOLO 类型。**`tests/stubs` 只供主机测试，绝不能放进固件 include 路径。** `b_device_runtime.c`已实现上述单任务轮询、真实连接事件排队、可选LED驱动与CLI；语音/视觉/联网共存仍待实物验收。

## 软件复现

按团队环境使用 Python 3.11 与 C11 编译器。先在含编译器的终端执行 C 原有测试，再执行 B 测试：

```sh
python scripts/test_c.py
python b/test_b.py
git diff --check
```

支持 MSVC `cl`、`cc`、`gcc`、`clang`，也可设置 `CC` 为编译器可执行入口。测试输出在被忽略的 `.local/`。B 的 C 快照 getter 在主机测试中是显式桩；C 的标定和去抖算法使用仓库真实实现，输入是合成几何，未运行模型或设备。

## 实机验收与队友配合

- B：已取回设备，接下来核对语音模块与供电；先做单独语音基线，再验证灯光和实时视觉。不提交设备凭据、原始日志或 Flash 备份。
- C：先解决新标定版 PID/空帧问题，确认真实 `C_CAL_READY`、正坐/侧倾/回正和未知恢复；与 B 检查语音/视觉共存。
- D：确认四状态和灯色、用户是否开启提醒、何时进入复盘/重练；提供团队产品/Agent 的正规配置流程，密钥留本机。
- A：与 D 确认项目和会话数据如何进入同一练习。正式网络 API 仍需协商，本次没有创建。

通过标准：真实项目完成两轮语音→复盘→重答；C 有效持续偏离才触发灯；遮挡/重新标定/过期变未知；断网、重启可按说明恢复；视觉和音频同时运行不复位。软件测试不等于这些实机标准已通过。

## 可执行的整机接入

新建干净固定版本SDK时先运行`python scripts/prepare_sdk.py --clone`。C接入完成且没有额外修改后，再运行：

```sh
python b/tools/prepare_device.py --check-only
python b/tools/prepare_device.py
```

B脚本要求整个已跟踪差异与C补丁内容完全一致，并逐字节验证C新增文件；有其他修改、已暂存工作或B目标目录时拒绝覆盖。再次运行不会重置SDK。B构建前还会检查SDK内B源码与仓库是否一致，防止编译旧副本。

本机工具链放在`.local/idf-tools`，使用固定SDK的`tools/idf_tools.py`安装Xtensa、CMake、Ninja、ULP和ROM文件及`install-python-env`。构建工具从该目录的实际环境和SDK工具清单定位，不复用作者电脑路径。当前构建验证使用项目内Python3.12，主机测试使用Python3.11.9。新机完整自动安装仍不是本脚本的功能。

```sh
python b/tools/firmware.py build --profile voice
python b/tools/firmware.py build --profile integrated
# 接线、供电和实际端口确认后单独烧录，不在build中自动烧录：
python b/tools/firmware.py flash --profile integrated --port COM7
python b/tools/firmware.py monitor --profile integrated --port COM7
```

COM7只是本次已识别端口，新机必须重新查。语音版明确关闭摄像头和模型；整合版要求C live。共享构建输出在`.local/build-device`，生成前一版需单独保存镜像和烧录清单；源码、版本与实测记录同时保留。CMake使用响应文件避开Windows命令行过长，所有本机依赖、镜像和日志均不入Git。

灯圈接好并复核后，再加`--led`构建/烧录。默认不开灯圈驱动。设备CLI支持`b status`、`b phase prepare/interview/review/retry`、`b visual on/off`及`b led test`；本地诊断不是云工作流调用证据，离线仍不能强行开始面试。

## 产品身份与尚待工作

尚无团队产品时，构建明确使用PID=0与UNCONFIGURED离线身份，不沿用上游示例产品冒充本团队；此版不能完成正式配网绑定。创建自己的平台产品和Agent后，在本机运行`b/tools/configure_product.ps1`隐藏输入SECRET，配置只写入被忽略的`.local/product.json`，再重编译烧录。不要把SECRET发到聊天或PR里。

D仍需实现/确认面试与复盘流程如何触发B的状态入口；A与D需提供实际作品或会话入口。灵机官网首页不是本项目的分享入口。保留两轮真实对话、一次平台控制和端到端反馈证据后，才能勾选整机验收。

## 10月29日可复现检查

安装pyserial后，退出其他占用串口的监视器，再运行：

```powershell
python b/tools/check_device.py --port COM7 --seconds 40
# 仅在固定机位、头肩完整且用户准备好时重新建立基准：
python b/tools/check_device.py --port COM7 --seconds 50 --calibrate
# 取得本人团队产品的SECRET后在本机隐藏输入，不发到聊天或PR：
powershell -NoProfile -File b/tools/configure_product.ps1 -ProductPid 11814
```

检查工具不主动复位板子，原始日志只保留在ignored `.local/device-checks`，终端仅打印统计。QM精简日志可不带模块名，统计以实际消息内容识别；标定READY、valid及稳定状态分别统计，发生panic不会被后续恢复掩盖。没有输出不能解读为已通过。未联网时B状态中的pose仍可为UNKNOWN，不能与C的离线诊断标定混淆。

Product PID和Agent ID用途不同。当前厂商SDK使用PID与产品SECRET认证；Agent由平台产品绑定，不能把Agent ID当SECRET，也不能拿上游示例身份替代。配置后仍需重编译、烧录、按平台流程配网并实际验证对话。

固定厂商SDK的BLE产品密钥上限为32字节：STR_PROD_SEC_LEN=(32+1)，适配器仅复制strlen<33的输入。B配置入口接受8-32个ASCII字符，超长在任何工具链/烧录动作前拒绝；不要自行截断，从正确产品详情重新复制。产品密码长度限制与Wi-Fi密码限制不同。校验只证明格式符合适配器，不证明与平台一致。
