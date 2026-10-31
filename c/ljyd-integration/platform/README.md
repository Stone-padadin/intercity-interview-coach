# 灵机工作流复建说明

以下是 2026-10-31 会话中实际使用过的配置结构，不是可直接导入的平台导出文件。账号配置、节点 ID 和可用域名需要在目标账号重新核实；凭据不进入仓库。

## 业务链路

```text
用户 inputText → 意图分支 → context HTTP → planner LLM
                                      → assistant HTTP → final LLM → 回答
```

设备控制保留平台原有独立分支；本原型的实验记录接口不发送设备命令。历史工作流另有 start、意图、设备插件、设备回答，共 9 节点 8 连线。

| 逻辑节点 | 配置 |
|---|---|
| context | POST `https://<服务域名>/v1/context`；JSON `{}` |
| planner | 使用 [planner.txt](planner.txt)，引用用户原话和 context 的真实 JSON 输出 |
| assistant | POST `https://<服务域名>/v1/assistant`；请求体为 planner 的完整 JSON 对象 |
| final | 使用 [final-answer.txt](final-answer.txt)，引用用户原话、context、planner、执行回执与执行 HTTP 状态 |

两个 HTTP 节点都使用 `Content-Type: application/json` 与 `Authorization: Bearer <本机私有 token>`。在平台受保护的请求头字段填入凭据；不得写进模板或公开导出。云端不能直接请求电脑的 `127.0.0.1`。

模板的 `{{INPUT_TEXT}}`、`{{CONTEXT_JSON}}`、`{{PLAN_JSON}}`、`{{EXECUTION_JSON}}`、`{{EXECUTION_HTTP_STATUS}}` 是逻辑占位符。需要通过平台变量选择器替换为实际上游输出引用；不能按字面复制占位符后宣称已接通。

历史节点对应：context=`http-request_mvw63eeh_2`，planner=`llm_mvw9nbt0_1`，assistant=`http-request_mvw6ivsk_4`，final=`llm_chat`。历史 Agent 2837 / 工作流 381 仅作定位线索。

## 恢复与验收

1. 核实实际服务和端口占用，沿用已有服务的数据目录，不覆盖正式数据库。
2. 在授权部署环境提供 HTTPS 地址，验证两个业务接口的鉴权；不复用笔记中的过期隧道域名。
3. 更新两个 HTTP 节点地址、请求头和变量引用。先只读查询，再在明确标注的测试实验中验收。
4. 依次测试创建、草稿、否定确认、明确确认、查询、更正后再确认、结束和实验隔离。检查实际 HTTP 回执、审计及持久化结果，不以模型自述为依据。
5. 清空 start 的调试默认值。保存 Agent 草稿在历史测试中曾重建默认工作流，保存或发布后重新核查节点、连线和变量。
6. 操作规范曾有训练与绑定记录；嵌入式资料和提醒说明曾有上传记录。逐文件检查上传、训练、绑定和本轮检索片段，四者分别验收；历史检索曾返回 `documents=[]`。

本次仓库整理未修改平台、重开公网隧道或发布 Agent。硬件语音、LED/TTS、接线识别和视频分析不属于已通过项。
