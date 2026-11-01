# 四功能演示对接与接续

更新：2026-11-01，北京时间。此文区分已实现、已验证、计划和阻塞；代码所在任务分支以 PR #13 为准。不是四功能完成声明。

## 产品与本轮范围

完整目标：危险操作提醒、实验数据记录、接线指导、用历史视频补充上下文进行排错。本轮四项各做一个限定案例，现场操作软件并保留真实运行录屏。用户目前没有 LED 实验器材，已选择使用**实物电路/操作视频**；不接受电路仿真或纸卡危险区代替真实素材。

记录必须通过开发板真实语音输入；结果以页面文字为主。危险提醒用已存在的实拍素材，不要求任何人重演危险行为。完整产品仍保留十分钟回溯目标，但本轮先验收短片段，不将十分钟缓存作为本轮交付前提。

## 当前事实（2026-11-01）

| 项目 | 状态与边界 |
|---|---|
| 电脑侧预览 | 真实 1280×720，新页面短时状态约 29.3 fps；不是推理帧率或长时稳定性证明 |
| 语音照片原型 | 已实现 BLAB1 最终 ASR 事件接收、“记一下”口述与附近照片关联、人工确认、SQLite 回读；完整实物闭环尚未验收 |
| 单张看图问答 | 已有当前画面和记录照片的主动发送入口，模型结果不自动确认记录；后端配置仅留本机 |
| 真实模型 | 用户提供百炼普通 API Key；最小文字请求 HTTP 200；qwen3.7-flash 从合成图片正确读出仅在图内出现的随机字符及左右红/蓝色块。真实视觉通道已验证一次，不代表电路或危险识别通过 |
| 软件测试 | 原有 13 项与视觉适配 5 项共 18 项通过；JavaScript 语法检查通过。模型边界自动测试使用模拟响应 |
| 开发板 | PID 11920 先前用户确认“你好小灵”唤醒后有完整回答；当前产品、已通固件和 PID 11919 恢复备份保留。本次没有重新验证当前在线/语音状态 |
| 四功能集成 | 已新增视频导入/静音播放/取帧、结构化测量确认、多帧分析、风险检查入口与证据导出；29 项合成/软件测试通过。实拍素材、真实模型案例、开发板口述、四段成片与整体验收仍未通过 |

## 静音、额度与接续约束

- 用户在北京时间约 03:45 再次明确：随后五小时保持静音。保守采用 **2026-11-01 08:47:00 +08:00** 为最早真机测试时间；此时间之前不得重启、烧录、唤醒、播报或播放有声媒体。时点到达只是允许测试，不等于用户已醒或实物已通过。
- 需要用户说话的语音验收必须由用户或 B 配合；没有真人口述不得用合成事件替代。
- 用户要求 Codex 额度及百炼 API 额度任一剩余 10% 时停下开发，先提交代码与交接。分阶段提交，不能等耗尽后才首次保存。
- 最近 Codex 快照五小时约剩 80%、周约剩 97%；快照有时效，续跑前重新核实，不以当前文档数字作为实时余额。
- 百炼真实剩余额度查询尚未接通：普通模型调用成功不证明能查询账单，也不证明账户剩余比例。不得把请求数或 token 数直接称为余额百分比。
- 自动恢复任务**尚未设置成功**。当前没有已验证的自动唤醒工具；不能声称额度恢复后一定自动开工。若额度不可读，暂停批量/连续计费测试，保留本地软件和资料成果。
- 密钥仅在 ignored `.local/vision-config.json`，禁止复制到 PR、群聊、日志或前端。队友使用自己的授权；需要本机联调时由用户管理授权。

## 队友接续顺序

1. 拉取统一演示分支，先读此文及 `README.md`，运行软件测试，核对 PR 最后提交。
2. 核验实拍素材和模型授权。素材不够清楚时先换素材，不编造读数或故障。
3. A/B 先通一条真实语音测量：转写 → 补齐字段 → 用户确认 → SQLite 保存 → 刷新回读。
4. A/C/D 接入一段视频及时间引用，通接线指导与历史排错。
5. C/D 对真实风险片段与对照片段做识别，记录实际响应延迟。
6. 四项各录一次真实功能；再做三分钟演示与备份，更新已通过/未通过表。

## 人员对接（沿用团队 A/B/C/D；不是已派发消息）

| 人员 | 明早／下一次共同测试要做什么 | 输出 |
|---|---|---|
| A：网页与服务 | 评审本原型与 PR #11 正式实验工作区的接法；统一确认、回放、引用和导出，禁止双份正式数据各自变化 | 同一实验的页面与服务数据一致、刷新可回读、接口说明与 PR |
| B：设备／总联调 | 审阅 PR #10 桥接，08:47 后配合真实口述；核对当前 PID 11920 与固件，不按旧文档刷回旧产品；保持一个串口读取者 | 真实 ASR 进同一实验、确认后回读、重复事件去重；声音允许后再验收播报仲裁 |
| C：画面／视觉 | 审查视频清晰度、帧与时间一致性、危险片段及遮挡；与 B 另查 SPI 姿态与 RGB 等原赛题项 | 真实素材证据、风险/对照测试及延迟记录；不从 2D 画面猜温度或导通 |
| D：Agent／资料／展示 | 核验安全和电路资料、真实多模态回答、当前/历史证据引用；整理讲稿、素材署名与一次真实平台调用证据 | 四张案例卡、实际模型结果、三分钟讲稿与真实备份录屏 |
| 用户 | 管理 API 授权，醒后完成一次真实口述及整体彩排 | 确认产品体验与最终展示内容 |

RGB、SPI 坐姿、两轮平台对话和平台设备调用是原赛题独立验收项。四项演示通过不自动等于这些项目通过。暂不新增舵机、IMU 或重做外壳。

## GitHub 同步：不要只拉 main

仓库：<https://github.com/Stone-padadin/intercity-interview-coach>

- 统一演示交付：[PR #13](https://github.com/Stone-padadin/intercity-interview-coach/pull/13)，分支 `feat/stone-padadin-voice-camera-notes`。持续更新此 PR，不将其当前基础原型误称最终完成版。
- [PR #10](https://github.com/Stone-padadin/intercity-interview-coach/pull/10)：B 桥接，最后核对草稿、未合并；审阅基准 `697de5683ca84d219180ea4af5e241a653e56a67`。本原型 `--bridge-source` 指向已取得并审阅的该版本源码；仓库当前分支不自带 `b/lab/bridge.py`，不能写一个不存在的路径启动。
- [PR #11](https://github.com/Stone-padadin/intercity-interview-coach/pull/11)：正式实验网页原型，未合并；[PR #12](https://github.com/Stone-padadin/intercity-interview-coach/pull/12)：实验记录服务与平台交接，未合并。
- PR #9 已关闭且未合并；不要把关闭当作已进入 main。main 仍可能显示旧面试方向。

已有仓库的队友从干净的独立目录审阅，保留自己的未提交工作：

```powershell
git status --short
git fetch origin
git worktree add --detach ../lab-demo-review origin/feat/stone-padadin-voice-camera-notes
cd ../lab-demo-review/c/voice-camera-notes
python -m unittest -v test_app test_vision test_lab test_continuation
```

无现有仓库时：

```powershell
git clone --branch feat/stone-padadin-voice-camera-notes https://github.com/Stone-padadin/intercity-interview-coach.git lab-demo-review
cd lab-demo-review/c/voice-camera-notes
python -m unittest -v test_app test_vision test_lab test_continuation
```

仅查看静音页面（不打开串口），先确认端口空闲：

```powershell
python app.py --port 8769
```

打开 <http://127.0.0.1:8769/>。相机必须只有一个采集者；有其他预览时先释放相机。未填视觉配置时不能真实识图；启动成功不等于功能验收成功。

检查交接记录的提交 SHA，不只核对分支名称。修改前从最新 main 创建自己的任务分支，再按审阅意见纳入所需依赖；提交 PR，由集成人员汇入统一演示分支。不得强推、覆盖他人工作或自行合并 main。每人回报：提交 SHA、复现步骤、实际结果、证据位置、阻塞和下一项。

## 展示材料候选与验收原则

- 危险素材：[Khan Academy 焊接安全](https://www.khanacademy.org/science/electrical-engineering/robots/spout-bot-with-solder/v/soldering-saftey)；规则依据：[Columbia EHS](https://research.columbia.edu/ehs/safely-handling-solder)。字幕明确讨论电源线搭在烙铁上的风险，视觉动作尚需逐帧核验。
- 读数：[SparkFun 万用表实测](https://www.youtube.com/watch?v=SLkPtmnglOI)。须确认测量对象、档位、单位与数值，不预填视频不存在的数值。
- 接线：[Adafruit 实物面包板教学](https://learn.adafruit.com/collins-lab-breadboards-and-perfboards)及 [LED 连接说明](https://learn.adafruit.com/breadboards-for-beginners/breadboard-usage)。
- 历史排错候选：[电路测试器电源排查](https://open.video/@motbots-com/video/3M6SB3zZsc2)。须核验实际片段、来源与可用方式；未核验前不称为已备妥素材。

视频按原片进度取证，模型只收到当前与此前画面，不收到未来画面、旁白中的答案或验收标签。保留引用与不确定性；源视频不进公开 Git，网络失败时可播放明确标注的实际运行备份，不能冒充现场推理。

三分钟脚本：开场15秒 → 危险提醒25秒 → 开发板语音记录35秒 → 接线指导35秒 → 历史排错55秒 → 总结15秒。四项分别验收；不可用项目如实显示未通过。
