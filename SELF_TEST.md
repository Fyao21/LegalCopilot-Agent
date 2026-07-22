# 自测与验收文档

## 一、环境要求

- Windows 10/11、macOS 或 Linux；
- Python 3.11 或更高版本；
- 项目路径可以包含中文，但建议使用纯英文路径；
- 离线模式不需要 Docker、数据库服务或大模型 API Key；
- 前端开发需要 Node.js 20+ 与 pnpm；Docker 验收需要 Docker Desktop。

## 二、全自动自测

在项目根目录创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\run_self_test.py
```

预期结果：26 项测试全部显示 `ok`，最后输出 `OK`，进程退出码为 0。

自动测试覆盖：

- 合同纠纷案件类型与当事人抽取；
- TXT 文档解析；
- 非法文件格式拒绝；
- 中文检索相似度基本排序；
- 服务健康检查与样例数据初始化；
- 法规搜索接口；
- 案件分析接口与引用返回。
- 法条详情回查；
- LangGraph 完整节点顺序；
- 混合检索的关键词、语义和综合分数；
- 篡改引用拒绝；
- LLM 异常回退和非法 JSON 单次修复；
- 空知识库最多重试两次；
- Agent 模式无密钥时安全使用离线回退；
- Markdown 报告与免责声明。
- `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL_NAME` 兼容变量映射。
- 后台任务创建响应为 `queued`，最终状态为 `completed`；
- `started_at` 与 `completed_at` 时间记录；
- Markdown/PDF 报告导出；
- 非法导出格式拒绝；
- 文件名安全清洗和扩展名/MIME 不一致拒绝；
- `X-Request-ID` 请求追踪。

## 三、第二周 Agent 工作流验收

启动服务后打开 `http://127.0.0.1:8000/docs`。

### 用例 A：创建离线 Agent 任务

调用 `POST /api/v1/runs`，使用 `multipart/form-data`：

```text
question=供应商收取货款后没有按合同交货，我能否解除合同并要求赔偿？
mode=offline
file=留空
```

预期：HTTP 202；立即返回 `run_id`；创建响应的 `status` 为 `queued`；同时返回状态和报告 URL。

### 用例 B：检查节点轨迹

调用 `GET /api/v1/runs/{run_id}`。

预期：`progress=100`；节点依次包含 `analyze_case`、`retrieve_laws`、`review_citations`、`write_report`；每个节点包含耗时和公开动作摘要。

### 用例 C：检查审核引用

调用 `GET /api/v1/runs/{run_id}/citations`。

预期：每条结果包含 `article_id`、综合分数、关键词分数、语义分数、`review_status`、`review_reason` 和 `verified`。至少有一条 `verified=true`。

### 用例 D：检查报告

调用 `GET /api/v1/runs/{run_id}/report`。

预期：HTTP 200；Markdown 包含案件摘要、争议焦点、法律分析、行动建议、信息缺口、审核通过的法律依据和免责声明。引用编号能通过法条详情接口回查。

### 用例 E：法条回查

从引用列表选择一个 `article_id`，调用 `GET /api/v1/articles/{article_id}`。

预期：返回的法律名称、条号和正文与引用一致。

### 用例 F：劳动争议与无密钥回退

调用 `POST /api/v1/runs`：

```text
question=公司拖欠工资并且没有签订书面劳动合同
mode=agent
```

当 `.env` 未配置模型密钥或 `OFFLINE_MODE=true` 时，预期任务仍然完成，案件类型为劳动争议，节点摘要显示使用规则或离线能力。

### 用例 G：真实模型模式（可选）

复制 `.env.example` 为 `.env`，填写有效配置：

```env
OFFLINE_MODE=false
LLM_API_KEY=你的密钥
LLM_BASE_URL=OpenAI兼容地址/v1
LLM_MODEL=模型名称
EMBEDDING_PROVIDER=openai-compatible
EMBEDDING_API_KEY=你的Embedding密钥
EMBEDDING_BASE_URL=Embedding兼容地址/v1
EMBEDDING_MODEL=Embedding模型名称
```

执行 `python scripts\reindex_embeddings.py`，再使用 `mode=agent` 创建任务。预期状态中的 `model_name` 被记录；模型失败时流程回退而不是崩溃。此用例需要用户自己的服务和配额，不属于离线自动测试。

## 四、第三周浏览器界面验收

### 1. 启动后端

在第一个 Terminal 执行：

```powershell
python -m app.main
```

### 2. 启动前端

在第二个 Terminal 执行：

```powershell
cd frontend
pnpm install
pnpm run dev
```

打开 `http://127.0.0.1:5173`，预期右上角显示“知识库在线”和法规数量。

### 3. 完整页面流程

1. 点击任意示例问题，或输入合同/劳动问题；
2. 可选拖入不超过 10 MB 的 TXT、DOCX、PDF；
3. 选择“离线可靠”，点击“开始案件分析”；
4. 页面显示 run ID、进度条和四个节点；
5. 完成后出现报告正文和已审核引用；
6. 点击引用卡片，检查条文原文、来源、关键词/语义分数和审核理由；
7. 分别下载 Markdown 和 PDF，确认文件可以打开；
8. 点击“分析新案件”，确认页面恢复到输入状态。

### 4. 前端异常验收

- 停止后端并刷新页面：显示“后端未连接”，提交按钮不可用；
- 上传 `.exe`：前端直接提示格式错误；
- 上传超过 10 MB 文件：前端直接提示文件过大；
- 将 `.txt` 文件改名为 `.pdf` 并上传：后端应返回 MIME 不匹配；
- 请求执行失败：页面展示可理解的错误，不无限轮询。

### 5. 前端生产构建

```powershell
cd frontend
pnpm run build
```

预期：TypeScript 检查通过，Vite 在 `frontend/dist` 生成生产文件。

## 五、PyCharm 后端手工验收

1. 使用 PyCharm 打开项目根目录。
2. 选择 `.venv` 作为项目解释器。
3. 创建运行配置，Module name 填 `app.main`，Working directory 填项目根目录。
4. 启动后控制台应显示服务运行在 `http://127.0.0.1:8000`。
5. 浏览器打开 `http://127.0.0.1:8000/docs`。

### 用例 1：健康检查

调用 `GET /health`。

预期：HTTP 200；`status` 为 `ok`；`article_count` 不小于 10。

### 用例 2：法规检索

调用 `POST /api/v1/articles/search`：

```json
{
  "query": "合同没有履行，能否要求赔偿损失",
  "limit": 5
}
```

预期：HTTP 200；返回 5 条以内结果；每条包含 `article_id`、法律名称、条号、原文、来源和分数；靠前结果应包含合同违约责任或损失赔偿内容。

### 用例 3：纯文本案件分析

调用 `POST /api/v1/cases`，问题填写：

```text
甲方与乙方签订采购合同，乙方收款后未交货。甲方能否解除合同并要求赔偿？
```

预期：HTTP 201；案件类型为合同纠纷；返回争议焦点、诉求和至少一条法规引用；响应含免责声明。

### 用例 4：上传文件

创建 UTF-8 TXT 文件，写入：

```text
申请人在公司工作两年，公司拖欠三个月工资且未签订书面劳动合同。
```

上传该文件并提问“可以主张哪些权利”。

预期：识别为劳动争议；检索结果应出现劳动报酬或未签劳动合同相关条文。

### 用例 5：异常文件

上传 `.exe`、`.zip` 或其他不支持格式。

预期：HTTP 415；返回“仅支持 .txt、.docx、.pdf 文件”，服务继续正常运行。

## 六、Docker Compose 验收

前提：安装并启动 Docker Desktop。

```powershell
docker compose up --build
```

预期：

1. `backend` 健康检查通过；
2. `http://127.0.0.1:3000` 打开前端；
3. 前端能通过 Nginx 反向代理调用 `/health` 和 `/api`；
4. 完成一条案件分析并下载报告；
5. 执行 `docker compose down` 再重新启动后，法规和历史任务仍在 volume 中。

停止服务：

```powershell
docker compose down
```

当前开发机没有 Docker 命令，因此本次只完成配置文件，尚未执行镜像构建；安装 Docker Desktop 后必须补做本节。

## 七、独立性检查

在项目根目录执行：

```powershell
$oldProjectName = "LvJing-" + "Agentproject-main"
Get-ChildItem -Recurse -File | Select-String -Pattern $oldProjectName
```

预期：没有匹配结果。随后临时重命名或断开旧项目目录，本项目仍能启动、自测和检索。

## 八、数据库重置

SQLite 文件位于 `data/legal_copilot.db`。如需重新验证首次初始化，可在服务停止后删除该文件，再次启动项目。数据库只包含本项目生成的样例和测试记录，可以安全重建。

## 九、已知限制

- 哈希向量只是离线基线，不能代表真实语义 Embedding 的质量；
- 教学法条存在节选和概括，正式展示权威引用前需要接入官方来源；
- 当前使用 FastAPI 进程内后台任务，不是跨进程持久任务队列；服务退出时未完成任务不能自动恢复；
- 真实模型与 Embedding 的质量和费用取决于用户配置的服务；
- PDF 仅支持包含文本层的文件，扫描件需要后续接入 OCR；
- 系统输出只用于技术演示，不构成法律意见。
