# 律镜 Legal Copilot Agent 接口文档

如果希望逐个学习每个接口的业务含义、Apifox 填写方法、成功返回和错误返回，请阅读 [逐接口含义与返回示例](API_GUIDE_DETAILED.md)。

## 1. Apifox 导入

直接导入同目录的 `openapi.json`：

1. 打开 Apifox 项目。
2. 选择“项目设置”或“导入数据”。
3. 选择“OpenAPI/Swagger”。
4. 选择文件 `docs/openapi.json`。
5. 导入模式建议选择“智能合并”，接口基础地址使用 `http://127.0.0.1:8000`。

规范版本为 OpenAPI 3.0.3。每个接口都包含请求类型、参数约束、返回 Schema、错误响应和示例。

## 2. 状态说明

OpenAPI 中通过 `x-implementation-status` 标记实现状态：

- `implemented`：已经写入 FastAPI，可以立即调用；
- `planned`：来自后续周次规划，目前调用会返回 404，开发完成后再改为 `implemented`。

当前已经实现：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务健康检查 |
| POST | `/api/v1/articles/search` | 法规 Top-K 检索 |
| POST | `/api/v1/cases` | 同步案件分析 |
| GET | `/api/v1/articles/{article_id}` | 回查法规完整原文 |
| POST | `/api/v1/runs` | 执行完整 Agent 工作流 |
| GET | `/api/v1/runs/{run_id}` | 查询状态和节点轨迹 |
| POST | `/api/v1/runs/{run_id}/retry` | 重试失败任务 |
| GET | `/api/v1/runs/{run_id}/citations` | 查看审核引用 |
| GET | `/api/v1/runs/{run_id}/report` | 获取 Markdown 报告 |
| GET | `/api/v1/runs/{run_id}/export` | 下载 Markdown 或 PDF 报告 |

## 3. 规划接口总览

### Agent 任务导出接口（第三周已完成）

| 方法 | 路径 | 计划阶段 | 说明 |
|---|---|---|---|
| GET | `/api/v1/runs/{run_id}/export` | 第三周 | 已实现，导出 Markdown/PDF |

### 法规知识库

| 方法 | 路径 | 计划阶段 | 说明 |
|---|---|---|---|
| POST | `/api/v1/knowledge/articles` | 第二周 | 新增单条法规 |
| POST | `/api/v1/knowledge/imports` | 第二周 | 批量导入法规 |
| GET | `/api/v1/knowledge/imports/{job_id}` | 第二周 | 查询导入状态 |

### 评测

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
  ↓ 返回 run_id
GET /api/v1/runs/{run_id}
  ↓ completed
GET /api/v1/runs/{run_id}/report
  ↓
GET /api/v1/runs/{run_id}/export?format=markdown
```

## 5. 文件上传约定

- Content-Type 使用 `multipart/form-data`；
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
