# A · 网页、简历与会话界面

A 侧网页原型：简历上传与解析、项目方向确认、陪练入口、练习记录和设置页面。确认项目后，记录会保存在当前浏览器的练习记录页；点击“查看项目”可恢复项目内容。

## 本地运行

在本目录执行：

```powershell
npm install
$env:PORT=8765
npm start
```

浏览器打开 `http://127.0.0.1:8765/index.html`。

## 接口

- `GET /api/health`
- `POST /api/resume/parse`
- `POST /api/projects`
- `GET /api/projects/:sessionId`

## 当前边界

页面目前可以本地运行。简历解析和项目保存依赖 `server.js`，摄像头、语音、硬件和 Agent 接口仍预留给后续联调。不要提交数据库、上传文件、真实简历、`node_modules` 或密钥。
