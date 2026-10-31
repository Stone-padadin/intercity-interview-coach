# C · 灵机实验台助教集成原型

贡献者：C / Stone-padadin。此目录承接 DeepSeek Harness「排查飞书智能体创建问题」会话中的软件交付。平台智能体实际建在灵机一动；飞书是赛题文档来源。

这是独立的实验台助教原型，供 A/B/D 审阅后接入；不自动替换仓库 main 的面试陪练方向，不修改共享固件、引脚或设备协议。

| 路径 | 用途 |
|---|---|
| [lab-tool-service](lab-tool-service/README.md) | SQLite 实验、待确认测量、修订、证据元数据；REST / MCP / SSE 接口 |
| [alert-policy](alert-policy/README.md) | 对已有姿态状态裁决提醒意图，语音默认关闭，无设备输出 |
| [platform](platform/README.md) | 工作流复建说明与规划、回答提示词模板 |
| 本目录三份知识资料 | 操作数据规范、嵌入式基础、检测提醒边界 |
| [交接文档](../../docs/ljyd/HANDOFF_20261031.md) | 历史验证、此次复测、未完成事项与接续顺序 |

## 从仓库根目录验证

需要 Python 3.11+，仅用标准库：

```sh
python -m unittest discover -s c/ljyd-integration/lab-tool-service -p 'test_*.py' -v
python -m unittest discover -s c/ljyd-integration/alert-policy -p 'test_*.py' -v
```

服务测试使用回环地址随机端口和独立 `.local/tests` 数据，不访问正式实验数据库或开发板。2026-10-31 本目录迁移后重新运行，分别 15、21 项通过。若运行环境禁止本机 socket，需要在宿主允许本机网络的环境复测。

## 启动和边界

```sh
python c/ljyd-integration/lab-tool-service/server.py --host 127.0.0.1 --port 8765
```

默认数据库、证据目录、自动生成的鉴权 token 都在服务目录的 ignored `.local/`。本次只迁移代码与文档，不迁移既有服务的数据，也不启动第二个长期服务。自定义数据目录见服务说明。

公网接入需要另配 HTTPS 代理和鉴权。历史临时隧道已断开，仓库不提供持续在线保证。单服务仅支持单活动实验，不是多设备隔离方案。文件登记与文字/时间筛选不等于视频分析；提醒意图不等于实际播放。

原会话要求开发板被占用期间禁止连接串口、复位或刷写；此交付没有进行硬件操作。
