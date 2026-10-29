# A 前端公网演示部署

发布日：2026-10-29。团队源仓库为 Stone-padadin/intercity-interview-coach，最新网页变更位于 feat/taooow-pages-frontend 分支的 a/，通过 PR 审阅，不直接修改 main。

## 网站及设置位置

- 网站：https://taooow.github.io/intercity-interview-coach/
- 发布仓库：https://github.com/TaoooW/intercity-interview-coach
- 发布文件：gh-pages 分支根目录
- Pages 设置：https://github.com/TaoooW/intercity-interview-coach/settings/pages
- Source：Deploy from a branch；Branch：gh-pages；Folder：/ (root)

共同仓库账号只有 Write 权限，未开启该仓库 Pages；使用已有个人 Fork 的独立 gh-pages 分支发布，不覆盖任何团队分支。gh-pages 是独立静态快照，不包含团队固件或后端。

## 发布范围

仅发布 HTML、前端 JavaScript、CSS、现有公开插图和 .nojekyll。排除 server.js、数据库、上传文件、测试简历、个人配置、密钥、node_modules 和构建依赖。不要使用根目录 *.js 通配符发布，避免带入后端代码。

## 能力边界

这是前端演示：可以手动确认项目、完成文字回答、查看规则模拟反馈、复盘和浏览器内历史记录。Agent、语音和硬件没有接入；反馈不是实际 AI 评判。数据在当前浏览器本地，不能跨设备同步。

Pages 无法运行 Node.js、简历解析和 SQLite 接口。当前未部署独立 HTTPS 后端，上传入口不代表公网简历解析可用。后端就绪后可在网站设置页配置根地址，再验证解析与保存。

## 更新方法

先在团队任务分支修改 a/ 并提交 PR。随后将上述静态文件的审阅版本拷贝到发布目录 gh-pages 分支并推送，保留 .nojekyll；GitHub Pages 自动重建。不可把本地数据库和真实简历一并同步。
