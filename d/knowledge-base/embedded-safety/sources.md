# GitHub 来源与纳入规则

检索日期：2026-10-31。

## 核心来源

- Raspberry Pi 官方文档：https://github.com/raspberrypi/documentation
  - GPIO 方向警告、3.3 V 逻辑、引脚能力、马达不得直接接 GPIO、供电要求。
- Raspberry Pi HAT 指南：https://github.com/raspberrypi/hats
  - 反向供电、启动期间引脚状态、扩展板电源与保护。
- Arduino 官方文档：https://github.com/arduino/docs-content
- Arduino 语言参考：https://github.com/arduino/reference-en
  - 不同板卡电压差异、电源/GND/GPIO 基础、LED 限流与引脚模式。
- Zephyr Project：https://github.com/zephyrproject-rtos/zephyr
  - 调试探头、板载/外部探头冲突、刷写与硬件保护配置。
- Learn Embedded Systems：https://github.com/erinjense/Learn-Embedded-Systems
  - ESD/EMI/EFT、鲁棒性、安全、无线和马达主题索引；外链许可需单独核查。

## 许可与质量规则

- 优先官方厂商、基金会和维护活跃的上游仓库。
- Arduino 文档通常采用 CC BY-SA 4.0，Zephyr 主体采用 Apache-2.0；发布前仍核查具体文件和仓库当前 `LICENSE`。
- 无明确许可的仓库仅用于发现主题，不复制正文。
- 论坛回答、个人测量和单一板卡经验不作为通用额定值。
- 电池火灾、触电、焊接烟雾和急救还必须结合当地消防/职业安全机构、实验室制度和制造商手册；不能只依赖 GitHub 社区资料。
