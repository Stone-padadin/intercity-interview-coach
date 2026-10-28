# 硬件依据与接线

记录日期：2026-10-26。以下来自已核对的原理图、官方 SDK 和先前实机记录；不代表新仓库已重新检测实物。

- 开发板：XJWB03-DevKit-V1，ESP32-S3，实机 16 MB Flash / 8 MB PSRAM。比赛材料有 LJWB03 命名，采购型号以实物与官方图纸为准。
- 摄像头：BF3901，1-bit SPI，转接板有 24 MHz 时钟。已确认 3.3 V 接 VCC，公共 GND，转接板内部 LDO 2.8 V。

| 摄像头信号 | ESP32-S3 GPIO | 状态 |
|---|---|---|
| SDA | 21 | 已核对 |
| SCL | 47 | 已核对 |
| VSYNC / CS | 4 | 已核对；与默认舵机功能冲突 |
| PCLK / SCLK | 13 | 已核对 |
| D0 / DATA | 8 | 已核对；与默认 MPU6050 SDA 冲突 |
| PWDN | 41 | 已核对 |
| HREF、D1、外部 XCLK | 不接 | 当前 SPI 转接板方案 |

不得在未重审引脚和配置前同时启用冲突外设。音频候选为 LJX40 Audio-KIT / VB701N UART 方案，实际接线、模块可用性、并发、功耗由 B 核实；本仓库不假定音频链路已通过。

首版机位固定、画面尽量摆正，并建立个人正坐基准；暂不增加 IMU。移动机位后重新标定。IMU 只能感知设备自身运动，不能替代人体质量检查和真人对照。

## 上游资料位置

在固定版本 SDK 中读取：

- `doc/5-摄像头/AS-BD108A93D17-19-V2.0.pdf`
- `doc/6-摄像头转接板/PCB_摄像头转接板_2026-10-16.pdf`
- `doc/6-摄像头转接板/SCH_摄像头转接板_2026-10-16.pdf`

官方资源：[SDK](https://gitee.com/xj-open/ljyd_xjwb03_agent_public_developer)、[赛道资料](https://xjiangiot.yuque.com/afahpl/qrhct7/cgqb9souvr4xkg8v)、[赛事手册](https://hcn5szavbjrh.feishu.cn/wiki/D0ZuwMQNTiLeG4ks8CSccCWAnoh)。这些链接由用户提供，本次仓库初始化未重新验证最新赛事规定。

## 待确认

转接板外廓和安装孔距、外壳开口/排线弯曲空间、音频供电与接线、语音和视觉共存、打印装配、最新版赛规对赛前开发的要求。外壳尺寸不使用猜测值。
