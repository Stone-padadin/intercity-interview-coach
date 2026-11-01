# A · 实验记录网页原型

AI 实验台助教当前网页入口。面向电子、自动化与嵌入式学习者，让手动测量先形成可追溯记录，再逐步接入语音、录像和证据分析。

## 运行与检查

Node.js 20 或更新版本；新入口和测试只用 Node.js 标准库，不需要安装依赖。

```powershell
cd a
npm start
```

浏览器打开 `http://127.0.0.1:8765/`。需要调整端口时设置 `PORT`。服务默认仅监听本机；不是已发布网站。

```powershell
npm test
```

## 当前可用

- 新建实验、填写电路背景、切换实验。
- 输入测量点、物理量、有限数值、单位和条件；先核对，再明确确认保存。
- 同实验复测关联、测量撤销与恢复；保留原记录。
- 区分观察、候选原因、下一项验证和复测发现的人工复盘。
- 浏览器本地持久化、刷新回读、按实验隔离；导出 Markdown 复盘。
- 存储失败明确提示；损坏/未知版本数据停止写入，避免覆盖；另一个标签页修改后要求刷新。

无自动填充示例。记录来源为 `manual`；记录时间是网页确认时间，不冒充仪表或设备采集时间。未确认测量与未保存复盘不导出，离开/切换时提醒。

数据只在当前浏览器的 `intercity.lab-assistant.v1` localStorage 中。旧面试数据使用原有键，不会自动迁移。清除网站数据、换浏览器或换来源地址不能恢复记录；及时导出。Markdown 是复盘文件，当前没有导入恢复能力，也没有跨设备同步。

## 尚未接入

设备最终语音转写、USB 录像回放、十分钟缓存、圈选、真实多模态模型、设备播报与平台上下文均未接入本页。不得把人工填写候选原因称作 AI 诊断。`GET /api/health` 明确返回 `voice/video/ai: false`，不是设备在线探测。

当前运行 `server.js` 仅提供显式列出的静态页面文件，不提供写记录 API。浏览器格式见 [本地数据说明](../docs/interfaces/a-local-records.md)，它不是已批准的 A/B/D 事件协议。

## 历史实现

旧面试前端完整移至 [legacy/interview/](legacy/interview/README.md)，原后端保存在 `legacy-server.js`。如需回归，在安装锁文件依赖后运行：

```powershell
npm ci
npm run start:legacy
```

旧服务单独运行时仍提供原 `/api/resume/parse`、`/api/projects` 和面试页面，不代表新实验服务。不要与新服务占用同一端口。

既有公网 Pages/CloudBase 是历史部署，本次源码修改不会自动更新这些站点。见 [静态发布边界](PAGES_DEPLOYMENT.md) 和 [历史 CloudBase 部署](CLOUDBASE_DEPLOYMENT.md)。
