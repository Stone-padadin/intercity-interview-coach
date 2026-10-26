# 难开口陪练 · INTERCITY HACK

四人 AI + 硬件黑客松项目：面向嵌入式开发实习/校招的面试陪练。目标流程为上传简历、确认项目、语音追问、反馈与重练；这些完整产品流程目前仍待 A/B/D 实现和整机验收。

当前仓库收录 C 模块的实时视觉、固定机位标定、去抖、USB 本地预览及测试。厂商 SDK 采用锁定版本加补丁，不复制整个 SDK，也不上传设备配置、Flash 备份、个人简历、照片和密钥。

## 团队入口

| 成员 | 工作区域 | 主要交付 | 首次接入 |
|---|---|---|---|
| A · CS | `a/` | 简历上传、网页、会话与复盘界面 | 确认前后端接口及数据删除方式 |
| B · EEE | `b/` | 固件主工程、语音、供电及整机联调 | 审阅 C 的 SDK 补丁及资源占用 |
| C · EEE | `c/` | 摄像头、视觉、标定、结构与 3D 打印 | [C 开发说明](c/README.md) |
| D · EEE | `d/` | 面试 Agent、题目与评分、验收及展示 | 明确嵌入式岗位场景与演示脚本 |

这里的 A/B/D 分工用于接入提案，具体成员能力与交付需团队确认；不按性别分配任务。

## 先读这些

- [共享协作规则](AGENTS.md)
- [已确认硬件与待确认项](docs/hardware.md)
- [C 视觉接口和语义](docs/interfaces/c-vision.md)
- [实际验证及限制](docs/validation.md)
- [比赛前迭代与联调清单](docs/team-plan.md)
- [任务记录](docs/tasks.md)

## 快速软件检查

需要 Python 3.11 与 C11 编译器。Linux/macOS 或已启用编译器的终端：

```sh
python scripts/test_c.py
```

Windows 普通终端（已安装 Visual Studio Build Tools）：

```bat
scripts\Test-C.cmd
```

19 项 Python 测试仅依赖标准库；脚本还编译并运行两套纯 C 测试。真实预览另外需要 `c/requirements-preview.txt`。完整固件构建步骤见 C 说明。软件测试不等于人体姿态识别通过。
