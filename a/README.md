# A · 统一实验网页与服务

本任务分支将 PR #11 的 A 网页接入 PR #13 的 C 服务。A 工作区、C 取景/视频页、语音测量、照片和分析证据共用一个实验 ID 与 SQLite 文件。软件联通不代表真人开发板或真实模型案例已验收。

## 启动

Windows 可先双击 `a/01_install.cmd`，完成后双击 `a/02_start.cmd`。后者在绑定端口成功后打开浏览器；保留窗口，关闭服务按 Ctrl+C。

Python 3.11+；手动测量与设备事件接收仅需标准库。从仓库根目录运行：

```powershell
python a/lab_server.py
```

或在 `a/` 中执行 `npm start`。打开 <http://127.0.0.1:8765/>。启动默认不打开相机、不读取串口、不输出音频、不调用模型。

相机和视频功能需要安装 C 的依赖，建议独立环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r c/voice-camera-notes/requirements.txt
.\.venv\Scripts\python.exe a/lab_server.py
```

首次使用空目录时，当前 ID 是 `exp_a_20261101_01`，不预置测量。页面左侧可查看、复制 ID。后续新实验用 `exp_` 加随机 UUID，旧 ID 保持不变。

默认数据目录 `c/voice-camera-notes/.local/`：

- `session.json`：启动绑定的实验 ID；已有文件时沿用。
- `notes.sqlite3`：本分支唯一测量/笔记/视频/分析与实验元数据库。
- `photos/`、`media/`：本机照片与导入视频。

通过 `--port 8771 --data-dir .local/my-lab` 可独立试运行；端口需空闲。重启必须沿用同一数据目录，不要把两个不同目录当作自动同步。

## 使用顺序

1. 打开网页，复制当前实验 ID；可先手动填一条测量。
2. 点击“核对这条测量”，此时只是服务端草稿；再点“确认并保存”。
3. 刷新页面或重启服务，检查正式记录回读。
4. 点“打开取景与视频分析”，在 C 页面核对照片、导入视频及分析证据。两页读取相同记录。
5. 旧浏览器有 `intercity.lab-assistant.v1` 数据时，可点击“导入浏览器旧记录”。保留原 ID、来源和浏览器数据；冲突拒绝覆盖。localStorage 按来源地址隔离，须从旧网页相同的主机/端口访问才能读取；本版本不提供跨来源自动迁移。
6. 关联复测、撤销/恢复、保存人工复盘后，导出 Markdown。

## 与 B 联调

使用已审阅的 PR #10 `697de5683ca84d219180ea4af5e241a653e56a67` 桥接，不凭空假设本分支有 `b/lab/bridge.py`。由 B 从自己的工作区启动，替换真实 COM 号与私有数据库路径：

```text
python <B工作区>/b/lab/bridge.py --port <真实COM号> --experiment-id exp_a_20261101_01 --service http://127.0.0.1:8765 --database <私有目录>/bridge.sqlite3
```

以网页显示的当前 ID 为准。保持一个串口读取者。先收到匹配的 `record/mode_set` 回执，再让用户真实说一条新的测量。网页保留最终原句，先补字段、核对、确认，再检查刷新回读；重复同事件不重复建记录。原生 Agent 回答不能代替保存回执。

设备事件到达后锁定实验切换。要换实验，先停止桥接、重启 A 服务、在网页选实验，然后用新 ID 重启桥接。不能自动沿用旧设备/平台会话。当前 PID 11920 与已通固件由 B 核实，本任务不刷机、不改设备产品。

## 检查

在 `a/` 运行 `npm test`：A 原有 10 项 Node 检查与新增统一服务检查。也可在仓库根目录仅运行 Python 集成检查：

```powershell
python -m unittest discover -s a/tests -p 'test_*.py' -v
```

C 回归在其目录执行（需要 OpenCV）：

```powershell
python -m unittest -v test_app test_vision test_lab test_continuation
```

测试用独立临时目录、随机端口及明确合成的数据，不触碰正式数据库、不输出音频、不调用真实计费模型。真人口述与真实实验素材仍需分项验收。

接口、幂等、来源、时间和导入边界见 [统一接口](../docs/interfaces/a-workspace.md)。旧浏览器格式见 [历史本地记录说明](../docs/interfaces/a-local-records.md)。

用户交接包的校验、功能接入与额外修复见 [包接入记录](HANDOFF_PACKAGE.md)，本轮软件与浏览器验证见 [验收记录](../docs/validation-a-integration-20261101.md)。

## 历史入口

`npm run start:static` 仅用于静态文件回归，不提供统一写记录 API；新页面会如实提示服务未连接。旧面试实现保留在 `legacy/interview/`、`legacy-server.js`，使用 `npm run start:legacy` 单独回归。本次不更新 Pages/CloudBase 公网部署，不把静态站当作本机数据库。
