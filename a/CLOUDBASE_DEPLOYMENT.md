# 历史面试服务 CloudBase 部署

2026-10-31：以下是旧面试服务的历史配置，本次没有重新检查线上状态，也没有部署。新实验记录原型使用浏览器存储，默认 `server.js` 不再提供简历/项目写入 API。旧实现已保存在 `legacy-server.js` 和 `legacy/interview/`；不要直接按旧命令用整个 `a/` 覆盖在线服务。`scf_bootstrap` 显式指向旧 `legacy-server.js`，保留历史服务入口；新路线部署前需重新审阅入口、绑定地址、存储与发布范围。

当前 A 模块已部署到 CloudBase 国内站的 HTTP 云函数：

- 环境：`ordinary-crane-d7g8n1sc855e9e565`
- 地域：`ap-shanghai`
- 函数：`interview-practice-api`
- 网关路径：`/api`

当前验证地址：

`https://ordinary-crane-d7g8n1sc855e9e565-1519832122.ap-shanghai.app.tcloudbase.com/api/health`

## 重新部署

在 `a/` 目录执行：

```powershell
tcb env use ordinary-crane-d7g8n1sc855e9e565
tcb fn deploy interview-practice-api --dir . --httpFn --runtime Nodejs20.19 --install-dependency true --force
```

网关路由需要保持以下设置：

- upstream 类型：`WEB_SCF`
- upstream 函数：`interview-practice-api`
- 路径传递：开启
- 匿名访问：开启

`scf_bootstrap` 将服务监听在 CloudBase 要求的 `9000` 端口。上传目录和项目 JSON 存储放在 `/tmp`，适合当前演示；云函数实例回收后数据可能丢失。正式使用前应迁移到 CloudBase PostgreSQL/云存储，并把服务端密钥放到环境变量或密钥管理中。

## 前端接入

GitHub Pages 仍然只负责静态页面。将页面的 API 基地址设置为上面的网关域名（不再追加 `/api`），然后请求 `/api/health`、`/api/resume/parse` 和 `/api/projects`。
