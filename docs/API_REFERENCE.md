# 律镜 Legal Copilot Agent 接口文档

如果希望逐个学习每个接口的业务含义、Apifox 填写方法、成功返回和错误返回，请阅读 [逐接口含义与返回示例](API_GUIDE_DETAILED.md)。

## 1. Apifox 导入

直接导入同目录的 `openapi.json`：

1. 打开 Apifox 项目。
2. 选择“项目设置”或“导入数据”。
3. 选择“OpenAPI/Swagger”。
4. 选择文件 `docs/openapi.json`。
5. 导入模式建议选择“智能合并”，接口基础地址使用 `http://127.0.0.1:8000`。

规范版本为 OpenAPI 3.1.0。每个接口都包含请求类型、参数约束、返回 Schema、错误响应和示例。

## 2. 状态说明

OpenAPI 中通过 `x-implementation-status` 标记实现状态：

- `implemented`：已经写入 FastAPI，可以立即调用；
- `planned`：来自后续周次规划，目前调用会返回 404，开发完成后再改为 `implemented`。

当前已经实现：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务健康检查 |
| GET | `/api/v1/examples/questions/random` | 随机生成 1～10 个案件问题，可按分类和简短/详细程度筛选 |
| POST | `/api/v1/articles/search` | 支持 `as_of_date` 的法规 Top-K 检索 |
| POST | `/api/v1/cases` | 支持案件日期的同步分析 |
| GET | `/api/v1/articles/{article_id}` | 回查法规完整原文 |
| POST | `/api/v1/runs` | 执行带法规适用日期的完整 Agent 工作流 |
| GET | `/api/v1/runs/{run_id}` | 查询状态、法规日期、实际执行引擎、模型和节点轨迹 |
| GET | `/api/v1/runs/{run_id}/pending-action` | 查询当前追问或报告审批待办及状态版本 |
| POST | `/api/v1/runs/{run_id}/clarifications` | 幂等提交本轮回答并恢复原工作流 |
| POST | `/api/v1/runs/{run_id}/approvals` | 幂等提交批准、要求修改或驳回 |
| GET | `/api/v1/runs/{run_id}/report-versions` | 获取全部报告版本摘要 |
| GET | `/api/v1/runs/{run_id}/report-versions/{version_number}` | 获取指定版本及与上一版本的差异 |
| POST | `/api/v1/runs/{run_id}/retry` | 重试失败任务 |
| GET | `/api/v1/runs/{run_id}/monitoring` | 查看单次脱敏 Trace、节点耗时、模型、Token、费用和降级 |
| GET | `/api/v1/monitoring/overview` | 按 1～90 天聚合运行数、成功/降级率、平均/P95 和节点指标 |
| GET | `/api/v1/runs/{run_id}/citations` | 查看审核引用 |
| GET | `/api/v1/runs/{run_id}/report` | 获取 Markdown 报告 |
| GET | `/api/v1/runs/{run_id}/export` | 下载 Markdown 或 PDF 报告 |
| POST | `/api/v1/knowledge/articles` | 新增单条法规并立即建立检索向量 |
| POST | `/api/v1/knowledge/articles/batch` | 同步批量上传最多 200 个四行格式 TXT，返回逐文件结果 |
| POST | `/api/v1/knowledge/articles/normalize` | 使用在线 LLM 把任意排版的单条法规 TXT 整理成标准四行草稿，不自动入库 |

法规搜索响应通过 `X-Embedding-Provider` 与 `X-Embedding-Model` 返回本次实际使用的向量服务，并通过 `X-Law-As-Of-Date` 返回实际法规适用日期。在线配置失败时接口仍可返回哈希检索结果，响应头和后端日志会明确显示降级，不能只根据相似度分数判断是否调用在线模型。

第七周为搜索 JSON、同步案件 form-data 和 Agent form-data 增加可选 `as_of_date=YYYY-MM-DD`。系统在召回前按 `[effective_from, effective_to)` 过滤法规版本；留空按当前日期。Citation 响应新增 `law_id`、`law_version_id`、`version_label`、`effect_status`、`effective_from` 和 `effective_to`，可直接在 Apifox 中比较 2020-12-31 与 2021-01-01 的结果。

## 3. 规划接口总览

### Agent 任务导出接口（第三周已完成）

| 方法 | 路径 | 计划阶段 | 说明 |
|---|---|---|---|
| GET | `/api/v1/runs/{run_id}/export` | 第三周 | 已实现，导出 Markdown/PDF |

### 法规知识库

当前已经实现的 `POST /api/v1/knowledge/articles/batch` 适合一次最多 200 个小型 TXT 的同步导入。下面两个接口仍是未来针对大型 JSONL/CSV、后台任务和进度轮询的规划，不与同步批量接口冲突。

| 方法 | 路径 | 计划阶段 | 说明 |
|---|---|---|---|
| POST | `/api/v1/knowledge/imports` | 第二周 | 批量导入法规 |
| GET | `/api/v1/knowledge/imports/{job_id}` | 第二周 | 查询导入状态 |

### 评测

第四周已实现本地/CI 评测命令 `python eval/run_eval.py`。评测不是在线业务接口，不会让任意访问者触发高成本批处理。以下接口仍属于未来管理端规划：

| 方法 | 路径 | 计划阶段 | 说明 |
|---|---|---|---|
| POST | `/api/v1/evaluations` | 第四周 | 启动离线评测 |
| GET | `/api/v1/evaluations/{evaluation_id}` | 第四周 | 查询指标和进度 |

## 4. 调用顺序

当前第一周同步流程：

```text
GET /health
  ↓
POST /api/v1/articles/search
  ↓
POST /api/v1/cases
```

第三周后台任务流程：

```text
POST /api/v1/runs
  ↓ 可选 as_of_date，留空按当前日期
  ↓ 返回 run_id
GET /api/v1/runs/{run_id}
  ├─ waiting_for_user
  │    ↓
  │  GET /api/v1/runs/{run_id}/pending-action
  │    ↓
  │  POST /api/v1/runs/{run_id}/clarifications
  │    ↓ resuming，继续查询同一个 run_id
  ↓ waiting_for_approval
GET /api/v1/runs/{run_id}/pending-action
  ↓
POST /api/v1/runs/{run_id}/approvals
  ├─ approve → completed
  ├─ request_changes → revising → waiting_for_approval
  └─ reject → rejected
GET /api/v1/runs/{run_id}/report
  ↓ 只有 approved 版本
GET /api/v1/runs/{run_id}/export?format=markdown
```

## 5. 文件上传约定

- 批量法规接口字段名为 `files`，允许重复添加最多 200 个 TXT；
- Agent 整理接口字段名为 `file`，只接收一个 UTF-8 TXT，单个不超过 128 KB；
- Agent 整理只返回草稿；`ready_for_import=true` 仍必须人工核对，接口本身不会写数据库；
- 每个法规 TXT 第一行为名称、第二行为条号、第三行为来源、第四行起为正文；
- 批量法规单文件不超过 128 KB，整批不超过 8 MB，编码必须是 UTF-8；
- Content-Type 使用 `multipart/form-data`；
- 追问回答和审批接口使用 `application/json`，并携带 `Idempotency-Key`；
- 问题字段名为 `question`；
- 文件字段名为 `file`；
- 支持 `.txt`、`.docx`、`.pdf`；
- 当前文件可选，但必须提供非空问题；
- 第三周需要增加文件大小和 MIME 类型校验。

## 6. 错误码规划

| HTTP 状态 | code 示例 | 含义 |
|---|---|---|
| 404 | `RUN_NOT_FOUND` | 任务或资源不存在 |
| 409 | `RUN_NOT_READY` | 报告尚未完成或状态不允许操作 |
| 415 | `UNSUPPORTED_FILE_TYPE` | 文件格式不支持 |
| 422 | `VALIDATION_ERROR` | 参数校验失败 |
| 429 | `RATE_LIMITED` | 请求频率或并发超限 |
| 500 | `INTERNAL_ERROR` | 未预期服务器错误 |
| 502 | `MODEL_PROVIDER_ERROR` | 外部模型服务失败 |
| 504 | `MODEL_TIMEOUT` | 模型请求超时 |

第一周 FastAPI 的默认 422 格式与统一 `ErrorResponse` 不完全相同。第二周实现全局异常处理后，再统一所有业务错误响应。

## 7. 维护规则

1. 新增或修改 FastAPI 接口时，同步更新 `docs/openapi.json`。
2. 接口开发完成后，将 `x-implementation-status` 从 `planned` 改成 `implemented`。
3. 删除接口前先标记 `deprecated: true`，至少保留一个版本周期。
4. 字段变更优先新增可选字段；不要直接修改已有字段类型。
5. 每次更新规范后运行：

```powershell
python -m json.tool docs\openapi.json > $null
```

6. 将规范重新导入 Apifox 时使用智能合并，避免覆盖已经编写的测试用例和环境变量。

## 8. 第八周运行监控

```text
POST /api/v1/runs
  ↓ 响应 trace_id + monitoring_url
GET /api/v1/runs/{run_id}
  ↓ 状态包含 total_duration_ms、Token、estimated_cost_usd、fallback_count
GET /api/v1/runs/{run_id}/monitoring
  ↓ 单次 Trace、节点 Span、模型、费用、重试和降级原因
GET /api/v1/monitoring/overview?days=7
  ↓ 运行数、成功/降级率、平均/P95、节点指标和最近运行
```

- `days` 允许 1～90，越界返回 422；
- 费用是环境变量单价乘 Token 的估算值，不是服务商账单；
- 离线模式 Token 和费用为 0 是正确结果；
- Trace 属性只允许低敏元数据，不返回案件全文、Prompt 或密钥；
- 无 Trace 的历史任务单次监控返回 404，不影响原状态与报告接口。
