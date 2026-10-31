# C · 实时视觉与结构

## 布局

- `firmware/apps/main/`：新增纯 C 模块与固件工作线程。
- `firmware/vendor-integration.patch`：对六个厂商文件的必要修改，包含构建 profile、启动入口、摄像头回调、模型返回几何、配置宏保护。
- `firmware/upstream.json`：锁定厂商仓库和提交。
- `tests/`：标定与去抖的纯 C 测试。
- `tools/cvision/`：本机 USB 预览、帧解析和诊断工具。

## SDK 接入（先与 B 确认）

```sh
python scripts/prepare_sdk.py --clone
```

脚本下载固定的官方 SDK 到 `external/vendor-sdk`，核对 SHA 和干净状态，再校验补丁、应用并复制新增模块。下载/磁盘开销较大；SDK、其嵌入的依赖和厂商设备配置不会进入本仓库。脚本不清理旧目录、不自动重置版本；已接入的 SDK 再运行会拒绝，先检查现有差异。

已有完整且干净的同版本 SDK 可使用 `--sdk <路径>`，仅检查可加 `--check-only`。原来已经在开发的 SDK 有修改，不能直接作为接入目标。

## 固件构建

使用厂商提供的 ESP-IDF 5.4.1 和对应工具链；建议 Conda Python 3.11，兼容层 venv 及工具安装目录均放在 `.local/`。不要使用其他项目的系统 Python 或擅自升级 IDF。

创建 Conda 环境可用 `conda env create -p .local/conda -f environment.yml`。固件依赖遵循上游 IDF 的 requirements 与 constraints；完整环境自动安装尚未在本新目录验收。

在官方 IDF 环境已导出的终端，设置 `ADF_PATH` 为 SDK 绝对路径、`IDF_PATH` 为其中 `esp-idf` 绝对路径，然后：

```sh
python "$IDF_PATH/tools/idf.py" -C external/vendor-sdk/apps -B .local/build-live -D C_VISION_PROFILE=live -D C_POSE_ROTATE_CW90=0 build
```

上面是 shell 变量写法；PowerShell 将 `$IDF_PATH` 替换为 `$env:IDF_PATH`。烧录须由 B/C 确认设备、端口、供电与接线后单独执行，不自动烧录。

| Profile | 行为 |
|---|---|
| baseline | 厂商默认完整应用；不保证默认配置适合我们全部接线 |
| camera | 单独摄像头诊断与单帧输出 |
| preview | USB JPEG 预览，921600 波特；不运行姿态模型、语音或云 |
| live | 实时模型与标定、去抖；保留原有应用，语音并发尚未验收 |

## 本机预览和标定

在独立 Python 环境安装 `pip install -r c/requirements-preview.txt`，烧录 preview 固件后运行：

```sh
python c/tools/cvision/preview_server.py --port <串口>
```

打开 http://127.0.0.1:8765/；只绑定本机，最新帧保存在内存，不上传、不录制。退出预览释放串口后才能烧录或打开串口终端。使用 live 固件、115200 波特终端输入 `posecal` 后回车，采集 10 个连续有效的正坐结果。相机移动或断电需要重新标定。此命令和真人标定流程仍待实物验收。

## 模型与边界

上游 ESP-DL YOLO11n-pose S8 V1 输出 17 个关键点。当前只用有效单人的鼻点、双肩及显式正坐基准判断持续肩线侧倾；不推断心理紧张、驼背、眼神或三维朝向。旧 SDK `status/error` 只作调试。详见共享接口和验证记录。

## 3D 结构

尚无可打印 CAD/STL，不能说结构已完成。先测转接板外廓、孔距、USB/排线空间和固定机位，纸板试装后再打印。6.5 mm 是摄像头小模组尺寸，不能当成整块转接板尺寸；小模组微孔不能直接当 M2/M3 安装孔。

## C 的实验台助教集成原型 · 2026-10-31

[代码与软件测试](ljyd-integration/README.md)，[交接文档](../docs/ljyd/HANDOFF_20261031.md)。由 C / Stone-padadin 交付实验记录服务、提醒裁决原型及知识资料。独立原型待团队审阅接入，不改变共享固件和现有产品主线；软件 15+21 项复测通过，硬件语音、实际提醒和知识检索命中未验收。
