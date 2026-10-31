# C 被动诊断文件 · schema_version 1

这是开发机本地文件格式，不是已批准的A/B/D桥接或云API。生产集成遵循 [C姿态语义](c-vision.md) 与B的有效性/过期适配。

```sh
python c/tools/cvision/observe_device.py --port COM7 --seconds 45 --experiment-id lab-check
```

需要pyserial，先关闭占用串口的预览、终端或桥接。115200波特被动读取，打开前设置DTR/RTS为false，不写命令、不标定或烧录。不同驱动的电气行为仍由实物决定，不能宣称所有硬件绝不复位。

每轮新建 `.local/c-observations/<UTC唯一目录>/`，包含数值events.jsonl与summary.json。不保存原始串口、ASR/TTS文本、照片或音频。目录被Git忽略，对外只整理必要汇总。

## 事件

公共字段：schema_version、source、experiment_id、host_utc、host_elapsed_ms、observation_epoch、kind、fields。

| kind | 来源与用途 |
|---|---|
| pose | CPOSE：帧号、设备时间、推理耗时、有效性、错误、内存 |
| calibration | CCAL：标定、有人标志、原始/稳定状态、肩线角 |
| device_status | B status：在线、阶段、视觉、姿态、灯光使能、内存 |
| malformed_diagnostic | 识别到但数值缺失/不合法；不回显原行 |
| crash_diagnostic | 命中崩溃标记；不保存诊断原文 |

source为device_numeric_diagnostic。host_utc是接收时间；capture_ms是设备低32位时间，不是UTC。帧号倒退增加observation_epoch，避免跨重启/乱序配对；它不等于已验证的设备启动ID。

同epoch和frame配对去重。语义可用需frame>0、有效、err=0、people=1、标定state=2、raw已知、双方stable一致且已知。固件的people字段实际是has_person布尔值，不能据此得出人数；数值一致也不证明真人分类正确。

## 判定边界

diagnostic_capture_passed要求至少3个姿态样本，无已识别崩溃、畸形诊断、推理/内存错误、有效性矛盾或帧倒退。允许未知样本，因此它**不代表标定或分类通过**；另看semantically_usable_samples和真人记录。无姿态不能用B状态充数。

退出0为诊断通过，2为未通过（含串口异常）。未解析文本可能包含工具未识别的问题，“未检出崩溃标记”不等于整机无故障。没有生产级时钟映射、过期判断或语音事件交付。
