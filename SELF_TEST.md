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

预期结果：82 项测试全部显示 `ok`，最后输出 `OK`，进程退出码为 0。

自动测试覆盖：

- 合同纠纷案件类型与当事人抽取；
- TXT 文档解析；
- 非法文件格式拒绝；
- 中文检索相似度基本排序；
- 服务健康检查与样例数据初始化；
- 法规搜索接口；
- 法规版本生效/失效边界、历史/现行切换和不填日期兼容；
- 已废止版本不会作为当前有效条文返回；
- Agent 引用、数据库关联和报告快照保存同一 `law_version_id`；
- 法规新增、重复提交冲突、空白字段校验和新增后立即检索；
- JSONL 种子数据按法律名称与条号增量补充且可重复安全执行；
- 案件分析接口与引用返回。
- 法条详情回查；
- LangGraph 完整节点顺序；
- 混合检索的关键词、语义和综合分数；
- 篡改引用拒绝；
- LLM 异常回退、非法 JSON 单次修复，以及连续返回空案件类型时回退规则识别；
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

## 三、法规知识库接口验收

启动服务后打开 `http://127.0.0.1:8000/docs`，调用 `POST /api/v1/knowledge/articles`：

```json
{
  "law_name": "测试法规",
  "article_number": "第一条",
  "content": "这是一条仅用于本地接口验收的测试内容。",
  "source": "本地人工验收数据"
}
```

预期：

1. 第一次调用返回 201 和新的 `article_id`；
2. 相同请求再次调用返回 409；
3. 调用 `POST /api/v1/articles/search` 搜索“本地接口验收”，结果包含新 `article_id`；
4. `GET /health` 的 `article_count` 比创建前增加 1；
5. PyCharm Database 中 `legal_articles` 和 `article_embeddings` 都出现对应记录。

教学样例 JSONL 当前包含 36 条。已有数据库启动时只补充缺少的“法律名称 + 条号”组合，不会清空案件、任务或报告。

## 四、第二周 Agent 工作流验收

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
EMBEDDING_BATCH_SIZE=10
```

先执行 `python scripts\check_embedding.py`，预期输出 `mode=online`、真实模型名、维度和非零坐标数，且不显示 Key。再执行 `python scripts\reindex_embeddings.py` 并调用法规搜索接口。预期响应头为 `X-Embedding-Provider: openai-compatible` 和实际模型名；使用 `mode=agent` 创建任务后，`retrieve_laws` 节点摘要也记录在线 provider。将 Key 临时改错后再次搜索，预期请求仍返回结果，但响应头变为 `hash` 且后端记录降级日志。此用例需要用户自己的服务和配额，不属于离线自动测试。

## 五、第三周浏览器界面验收

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

## 六、PyCharm 后端手工验收

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

## 七、Docker Compose 验收

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

## 八、独立性检查

在项目根目录执行：

```powershell
$oldProjectName = "LvJing-" + "Agentproject-main"
Get-ChildItem -Recurse -File | Select-String -Pattern $oldProjectName
```

预期：没有匹配结果。随后临时重命名或断开旧项目目录，本项目仍能启动、自测和检索。

## 九、数据库重置

SQLite 文件位于 `data/legal_copilot.db`。如需重新验证首次初始化，可在服务停止后删除该文件，再次启动项目。数据库只包含本项目生成的样例和测试记录，可以安全重建。

## 十、已知限制

- 哈希向量只是离线基线，不能代表真实语义 Embedding 的质量；
- 教学法条存在节选和概括，正式展示权威引用前需要接入官方来源；
- 当前使用 FastAPI 进程内后台任务，不是跨进程持久任务队列；服务退出时未完成任务不能自动恢复；
- 真实模型与 Embedding 的质量和费用取决于用户配置的服务；
- PDF 仅支持包含文本层的文件，扫描件需要后续接入 OCR；
- 系统输出只用于技术演示，不构成法律意见。

## 十一、第四周评测与质量验收

### 1. 安装开发依赖

```powershell
python -m pip install -r requirements-dev.txt
```

### 2. 运行格式、静态检查和类型检查

```powershell
ruff format --check app eval scripts tests
ruff check app eval scripts tests
mypy app/services app/llm eval
```

预期：Ruff 显示 `All checks passed`，mypy 显示 `Success: no issues found`。

### 3. 运行完全离线的测试

```powershell
python scripts\run_self_test.py
```

预期：82 项测试通过。脚本会在导入应用前强制 `OFFLINE_MODE=true`、`EMBEDDING_PROVIDER=hash`，删除进程中的 LLM/Embedding Key，并使用测试数据库；控制台不应出现发往真实模型地址的 HTTP 请求。

第四周安全用例包括：损坏 PDF、超大文件、MIME 伪装、恶意文件名、重复提交、提示/SQL 注入文本、模型超时、非法 JSON 和 SQLite 锁重试。

### 4. 运行评测和对照实验

```powershell
python eval\run_eval.py
python -m json.tool eval\results\latest.json > $null
```

预期生成：

- `eval/results/latest.json`：机器可读明细、数据集哈希和环境信息；
- `eval/results/latest.md`：适合 README 和面试展示的指标表。

默认只运行关键词、哈希语义和哈希混合三组，不访问网络。只有已经配置独立 Embedding 服务时才显式执行：

```powershell
python eval\run_eval.py --include-online
```

如果仍为 `EMBEDDING_PROVIDER=hash`，在线组应标记 `skipped`，不得填写虚构指标。

### 5. 前端执行来源验收

分别运行一次离线和 Agent 模式：

- 离线完成后页面显示“离线规则引擎 · 未调用模型”；
- Agent 成功后显示“智能 Agent · 模型名”；
- Agent 配置关闭或降级后显示“Agent 已降级 · 离线规则”；
- 状态接口对应返回 `execution_engine=rules|llm|fallback` 和 `model`。

### 6. GitHub Actions

推送后打开仓库的 **Actions** 页面。`CI` 工作流包含两个 Job：

1. `backend`：依赖安装、Ruff format、Ruff lint、mypy、82 项测试、离线评测；
2. `frontend`：pnpm 锁文件安装、TypeScript 检查和 Vite 构建。

CI 不配置真实模型密钥。两个 Job 均为绿色后，第四周 CI 才算通过。

### 7. 人工验收项

- 第二位标注者复核 `eval/dataset.jsonl` 并记录争议；
- 安装 Docker Desktop 后完成第六节容器测试；
- 配置独立 Embedding 服务后补做在线混合检索对照；
- 按 `docs/DEMO_SCRIPT.md` 录制 2–3 分钟视频并检查没有泄露隐私。

## 十二、知识库管理页面验收

### 1. 打开页面

同时启动后端和前端，浏览器访问 `http://127.0.0.1:5173/#knowledge`，或点击顶部“知识库管理”。

预期：

- 页面显示法律名称、条号、来源和正文四个字段；
- 顶部显示后端在线状态和当前法规数量；
- 右侧显示名称核对、条文拆分、来源保留和效力检查提示；
- 页面明确提示知识库写接口尚无管理员认证，不能直接暴露公网。

### 2. 验证前端校验

不填写内容直接点击“保存并建立索引”，再分别尝试空 TXT、非 TXT、超过 1 MB 的 TXT，以及超过 20000 字的正文。

预期：页面分别显示清晰错误，不发送无效保存请求；有效 UTF-8 TXT 会在浏览器本地读取并填入正文框。

### 3. 验证新增与即时检索

填写一条可核验的教学条文，保证“法律名称 + 条号”尚不存在，然后提交。

也可以点击“从 TXT 导入”，选择项目提供的 `examples/labor_contract_law_article_9.txt`。其余字段填写：法律名称“中华人民共和国劳动合同法”、条号“第九条”、来源“国家市场监督管理总局法规页面 https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html”。

预期：

- 页面显示“法规已保存并可立即检索”和新 `ARTICLE #ID`；
- 顶部法规数量增加 1；
- 可选择继续添加同一部法律的其他条文，法律名称和来源会被保留；
- 回到“案件分析”提交包含该条文关键词的问题后，新条文可以进入法规候选。

### 4. 验证重复冲突

使用完全相同的法律名称和条号再次提交。

预期：后端返回 HTTP 409，前端显示该法律名称和条号已存在，不覆盖数据库中的原文。

### 5. 前端构建

```powershell
cd frontend
pnpm run build
```

预期：TypeScript 项目构建和 Vite 生产打包成功，没有类型错误。

## 十三、200 条示例与批量 TXT 导入验收

### 1. 检查示例文件

```powershell
(Get-ChildItem examples\batch_laws -Filter *.txt).Count
python scripts\generate_batch_law_samples.py
```

预期两次都确认生成 200 个文件；`examples/batch_laws_manifest.json` 中 `total_files` 为 200、来源为 10 部法律。生成脚本需要联网读取项目记录的官方页面，并用后端同一个解析器验证每个文件。

### 2. 检查四行格式

打开任意 TXT，例如 `examples/batch_laws/001_labor_contract_001.txt`：

```text
中华人民共和国劳动合同法
第一条
https://www.samr.gov.cn/……
为了完善劳动合同制度……
```

第四行之后都属于正文，因此正文可以有多个自然段。文件必须是 UTF-8。

### 3. 前端批量上传

打开 `http://127.0.0.1:5173/#knowledge`，选择“批量 TXT”，点击“选择多个 TXT 文件”，进入 `examples/batch_laws` 后按 `Ctrl+A` 选择全部 200 个。

预期：

- 页面先显示 200 个文件的名称、法律名称、条号和正文长度预览；
- 点击上传后显示新增成功、重复跳过、格式错误三个计数；
- 首次导入也可能出现少量重复，因为 36 条内置教学数据与这 200 条官方来源样例存在交集；
- 成功数会同步增加到顶部知识库总数；
- 重新上传同一批文件时全部已有组合应显示“重复跳过”，不会覆盖原文。

### 4. 错误隔离

在一批合法文件中加入一个只有三行的 TXT、一个非 UTF-8 TXT 和一个非 TXT 文件。

预期：错误文件标记为 `invalid`，合法文件仍能创建；响应项目顺序与上传顺序一致。超过 200 个、单文件超过 128 KB 或整批超过 8 MB 时，整个请求返回 413。

## 十四、Agent 智能回退修复验收

### 1. 案件类型补全

在“智能 Agent”模式输入：

```text
食物中毒商家需要负责吗
```

预期：案件类型为“食品安全与消费者权益纠纷”，不能显示“未识别”。正常情况下轨迹来源为 `llm`；如果模型仍返回“未识别”，轨迹来源为 `llm_enriched`，表示模型字段与本地分类结果进行了融合。

### 2. 在线 Embedding 重试

确保 `.env` 中 `OFFLINE_MODE=false`、`EMBEDDING_PROVIDER=openai-compatible` 且 Embedding 配置完整，提交同一问题。

预期：

- 正常轨迹显示 `provider=openai-compatible`；
- 第一次请求发生瞬时网络错误时，同一检索节点自动重试一次；
- 只有连续两次失败才显示 `provider=hash`；
- hash 回退时轨迹必须同时显示“回退原因”，不能静默伪装成在线检索。

### 3. 报告结构化输出

预期：“生成分析报告”节点不再因为模型把 `suggestions` 或 `evidence_gaps` 返回为字符串而离线回退。最终建议和证据缺口仍以列表展示。

### 4. 本次真实配置回归结果

使用当前本地配置进行不写库回归，结果为：

```text
case_type=食品安全与消费者权益纠纷
retrieval_provider=openai-compatible
retrieval_model=text-embedding-v4
verified_citations=3
report_fallback=None
```

真实接口测试会产生模型和 Embedding API 用量，日常自动测试仍使用 Fake Provider 与离线数据库。

## 十五、随机案件问题示例接口验收

### 1. 默认随机示例

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/examples/questions/random"
```

预期：HTTP 200，`count=3`，返回三个不重复问题，并包含 `available_categories`。

### 2. 指定数量和分类

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/examples/questions/random?count=5&category=食品安全"
```

预期：返回 5 条问题，所有 `category` 都是“食品安全”，`example_id` 和 `question` 在本次响应内不重复。

### 3. 参数错误

分别请求 `count=0`、`count=11` 和 `category=不存在的分类`。

预期：全部返回 HTTP 422；未知分类的 `detail` 列出可选值。

### 4. 前端验收

打开 `http://127.0.0.1:5173/#analysis`：

1. 案件问题下方显示三条带分类的示例；
2. 点击任一示例，完整问题进入文本框；
3. 点击“换一批”，按钮短暂显示“生成中…”，随后替换三个示例；
4. 后端不可用时仍显示本地兜底示例，用户可以继续手工输入，但“换一批”会显示连接错误。

随机示例由本地模板和变量池生成，不调用 LLM，不产生模型 API 费用，也不会写入数据库。它只负责准备输入；只有用户点击“开始案件分析”才会创建 Agent 任务。

## 十六、详细案件背景示例验收

### 1. 调用详细模式接口

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/examples/questions/random?count=3&category=食品安全&detail_level=detailed"
```

预期：

- `requested_detail_level` 为 `detailed`；
- 每个示例的 `detail_level` 都是 `detailed`；
- 问题不是一句话，包含时间、主体、购买或事件经过、损害结果、已有证据、对方态度和希望解决的问题；
- 同一次响应的三个问题不重复。

将 `detail_level` 改成 `brief`，预期返回适合快速测试的一句话问题。不传该参数时默认也是 `brief`，兼容旧调用。

### 2. 参数错误

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/examples/questions/random?detail_level=very-detailed"
```

预期：返回 HTTP 422。

### 3. 前端验收

1. 打开案件分析首页；
2. 在“示例生成”处选择“详细案情”；
3. 等待按钮结束“生成中…”状态；
4. 点击任一带分类的示例；
5. 文本框应填入多句案情，字符计数明显增加；
6. 提交 Agent 后，“案件摘要”应能够提取具体关键事实和诉求，而不再只显示“材料不足”。

详细模板中的姓名、金额和日期均为随机组合的教学数据，不代表真实案件。

## 十七、Agent 非标准 TXT 整理验收

### 1. 配置在线 Chat 模型

`.env` 至少需要：

```env
OFFLINE_MODE=false
LLM_API_KEY=你的Chat模型密钥
LLM_BASE_URL=服务商的OpenAI兼容地址
LLM_MODEL=服务商实际支持的模型名
```

修改 `.env` 后必须重启后端。该功能使用 Chat LLM，不使用 Embedding Key；`OFFLINE_MODE=true` 时接口会返回 HTTP 503。

### 2. Apifox 或命令行测试

项目提供故意打乱格式的文件：

```text
examples/unstructured_law_example.txt
```

请求：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/knowledge/articles/normalize" `
  -F "file=@examples\unstructured_law_example.txt;type=text/plain"
```

预期：

- HTTP 200；
- `law_name` 为“中华人民共和国食品安全法”；
- `article_number` 为“第四条”；
- `source` 为“国家法律法规数据库”；
- `standardized_text` 前三行依次为名称、条号和来源，第四行起为正文；
- `requires_human_review=true`；
- 字段齐全且没有多条内容时 `ready_for_import=true`；
- 调用前后 `/health` 的 `article_count` 不变，证明整理接口没有自动入库。

模型输出存在随机性。如果字段值和原文不一致，结果应在 `warnings` 中提示人工核对，不能直接保存。

### 3. 前端测试

1. 打开 `http://127.0.0.1:5173/#knowledge`；
2. 选择“Agent 整理”；
3. 选择 `examples/unstructured_law_example.txt`；
4. 点击“开始智能整理”；
5. 检查模型名、置信度、字段、警告和标准四行预览；
6. 点击“下载标准 TXT”，确认文件可以用 UTF-8 正常打开；
7. 点击“填入单条录入并核对”，页面切换到“单条录入”；
8. 核对四个字段后再点击“保存并建立索引”。

整理完成但尚未点击最后的保存按钮时，数据库不应新增数据。

### 4. 错误与边界测试

- 上传 PDF：预期 HTTP 415；
- 上传空 TXT、非 UTF-8 TXT：预期 HTTP 422；
- 上传超过 128 KB：预期 HTTP 413；
- 关闭在线模型：预期 HTTP 503；
- TXT 缺少来源：`missing_fields` 包含 `source`，`ready_for_import=false`；
- TXT 同时包含两个条号：`multiple_articles_detected=true`，`ready_for_import=false`。

### 5. 自动测试与构建

```powershell
python scripts\run_self_test.py
cd frontend
pnpm run build
```

该功能完成时为 56 项离线测试；第五周加入追问测试后为 62 项；第六周加入审批测试后为 69 项；第七周加入法规时效测试后为 75 项；第八周加入 Trace、指标和隐私测试后，统一自测入口现为 82 项。前端 TypeScript 检查和 Vite 生产构建通过。自动测试使用 Fake LLM，不读取本机 API Key，也不会产生模型费用。

### 6. 本次真实模型回归结果

使用 `examples/unstructured_law_example.txt` 和本机已有的在线 Chat 配置进行一次不写数据库的真实回归：

```text
model=deepseek-v4-flash
law_name=中华人民共和国食品安全法
article_number=第四条
source=国家法律法规数据库
ready_for_import=True
missing_fields=[]
warnings=[]
```

真实回归会产生一次 Chat 模型调用费用。输出中不记录 API Key，调用过程不创建法规或向量记录。

## 十八、批量 TXT 前端规则展示验收

1. 同时启动前后端，打开 `http://127.0.0.1:5173/#knowledge`。
2. 点击“批量 TXT”页签。
3. 页面应默认展开“批量 TXT 格式与导入规则”。
4. 检查四个字段卡片依次显示：第 1 行法律名称、第 2 行条号、第 3 行来源、第 4 行起条文正文。
5. 检查页面明确显示字段长度、UTF-8、200 个文件、单文件 128 KB、整批 8 MB。
6. 检查页面明确说明一份文件只能对应一个条号，以及按“法律名称 + 条号”判重。
7. 标准文件示例应显示名称、条号、来源和可以跨多行的正文。
8. 页面应解释新增成功会入库、重复会跳过、格式错误不会写库。
9. 点击标题可以收起规则，再次点击可以重新展开。
10. 缩小浏览器到手机宽度，文件要求、判重规则和三种状态应变为单列，不应横向溢出。

前端生产构建命令：

```powershell
cd frontend
pnpm run build
```

规则展示不修改后端解析器和接口契约；最终是否可导入仍以后端校验结果为准。

## 十九、第五周多轮追问与恢复验收

### 1. 准备

启动后端和前端：

```powershell
# 终端 1，项目根目录
python -m app.main

# 终端 2
cd frontend
pnpm run dev
```

离线模式即可验收，不要求 LLM 或 Embedding Key。

### 2. 前端完整闭环

1. 打开 `http://127.0.0.1:5173/#analysis`；
2. 选择“离线可靠”；
3. 输入：`供应商收款后一直没有交货，我能解除合同并要求赔偿吗？`；
4. 点击“开始案件分析”；
5. 右侧状态应变为“等待补充信息”，进度为 35%；
6. 页面出现“第 1 / 3 轮追问”，问题为合同约定的交货日期或履行期限；
7. 回答：`合同约定交货日期为2026年6月30日。`；
8. 点击“提交并继续分析”；
9. 状态依次经过“正在恢复分析、提取案件要素、检索、审核、写报告”；
10. 同一个 RUN 编号最终变为“分析完成”；
11. 轨迹中出现“补充关键信息”；
12. 报告、引用、Markdown 下载和 PDF 下载均可用。

第五周完成标准是第 12 步，不需要等待第六周审批功能。

### 3. 页面刷新恢复

1. 再创建一个会触发追问的任务；
2. 看到追问卡片后按 `F5` 刷新页面；
3. 页面应从 `sessionStorage` 读取当前 run ID；
4. 状态接口重新返回 `waiting_for_user`；
5. 追问卡片和之前相同；
6. 回答后仍能完成报告。

点击“分析新案件”会清除当前 run ID。浏览器会话结束或手工清除站点数据后，前端不会自动找回 run ID，但可以通过 API 使用已知 run ID 查询。

### 4. 后端应用上下文重启恢复

1. 创建任务并等待状态变为 `waiting_for_user`；
2. 记下 `run_id`；
3. 关闭后端并重新启动；
4. 请求：

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/runs/{run_id}/pending-action"
```

预期仍返回 `action.type=clarification`、问题列表和 `state_version`。这是因为业务追问记录和 LangGraph checkpoint 都保存在 `data/legal_copilot.db`，不是进程内内存。

### 5. Apifox 回答示例

先请求：

```http
GET /api/v1/runs/{run_id}/pending-action
```

假设返回 `state_version=1`、`question_id=r1-q1`，再请求：

```http
POST /api/v1/runs/{run_id}/clarifications
Content-Type: application/json
Idempotency-Key: manual-run-12-round-1

{
  "expected_state_version": 1,
  "answers": [
    {
      "question_id": "r1-q1",
      "answer": "合同约定交货日期为2026年6月30日。"
    }
  ]
}
```

预期 HTTP 202，`status=resuming`。再次轮询状态直到 `completed`。

### 6. 错误和边界

- 不提供 `Idempotency-Key`：HTTP 422；
- 幂等键短于 8 个字符：HTTP 422；
- `expected_state_version` 过期：HTTP 409，刷新待办后再提交；
- 漏答某个问题或提交未知 `question_id`：HTTP 422；
- 任务不是 `waiting_for_user`：HTTP 409；
- 相同幂等键重复提交：HTTP 202，`replayed=true`，不会重复恢复；
- 回答“暂不清楚”：允许继续，不要求用户猜测；
- 连续存在信息缺口：最多三轮，之后继续生成标明证据缺口的报告。

### 7. 自动验证

```powershell
python scripts\run_self_test.py
python -m ruff check app tests
python -m mypy app
cd frontend
pnpm run build
```

第五周完成时的实际结果：62 项离线测试全部通过，Ruff 和 mypy 通过，TypeScript 与 Vite 生产构建通过。升级到第六周后为 69 项，第七周后为 75 项，第八周后统一测试总数为 82 项。

### 8. 本次浏览器实测记录

2026-07-26 已在 `http://127.0.0.1:5173/#analysis` 完成真实页面验收：

- 测试运行：`RUN #73`；
- 暂停状态：`waiting_for_user`，进度 35%，第 1 / 3 轮；
- 追问内容：合同约定的交货日期或履行期限；
- 恢复前操作：停止并重新启动后端，确认待办仍可提交；
- 提交答案：收到全部货款后 7 日内交货，当前已经过去 30 日；
- 恢复结果：同一运行继续执行，轨迹出现“已合并第 1 轮用户回答”；
- 最终结果：`completed`、100%，报告、引用、Markdown 和 PDF 下载入口均显示。

## 二十、第六周报告审批与版本管理验收

### 1. 准备一个不触发追问的案件

启动前后端，在离线模式输入：

```text
合同约定供应商应在收到全部货款后7日内交货，现已过去30日仍未交货，我要求解除合同、退还货款并赔偿损失。
```

提交后预期：

1. 案件抽取、检索、引用审核和报告生成均完成；
2. 任务不是 `completed`，而是 `waiting_for_approval`；
3. 进度为 97%，当前节点为 `approve_report`；
4. 页面显示“待审批草稿 V1”和人工审批卡片；
5. 草稿正文、引用和证据缺口可以查看；
6. 页面不显示 Markdown/PDF 最终下载按钮。

### 2. 验证后端无法绕过审批

假设 `run_id=100`：

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/runs/100/export?format=markdown"
curl.exe "http://127.0.0.1:8000/api/v1/runs/100/export?format=pdf"
```

两个请求均应返回 HTTP 409：

```json
{
  "detail": "报告尚未通过人工审批，不能导出最终版本"
}
```

这一步证明发布限制在后端执行，不是只隐藏前端按钮。

### 3. 批准路径

1. 审核人填写“本地审核人”；
2. 审批意见可填写“案件事实、引用和风险提示已核对”；
3. 点击“批准并发布”；
4. 同一 `run_id` 进入 `completed`；
5. `approved_report_version=1`；
6. 页面标记“已批准最终报告 · V1”；
7. Markdown 和 PDF 下载按钮出现；
8. 下载文件名包含 `-v1`。

Apifox 请求示例：

```http
POST /api/v1/runs/100/approvals
Content-Type: application/json
Idempotency-Key: manual-run-100-version-1-approve
```

```json
{
  "expected_state_version": 1,
  "action": "approve",
  "comment": "案件事实、引用和风险提示已核对。",
  "reviewer": "本地审核人"
}
```

### 4. 要求修改路径与版本差异

新建另一个案件并等待 V1 审批：

1. 填写审批意见“请把合同解除条件与损失赔偿责任分开说明”；
2. 点击“要求修改”；
3. 状态短暂进入 `revising`；
4. 系统生成 V2 并再次进入 `waiting_for_approval`；
5. 版本列表同时显示 V2 `draft` 和 V1 `superseded`；
6. 点击 V2，可以查看完整 Markdown 和相对 V1 的 unified diff；
7. V1 内容仍能读取，没有被覆盖；
8. 批准 V2 后 `approved_report_version=2`，下载文件名包含 `-v2`。

离线模式不会自行发明新的法律事实，只会把审批修改要求明确加入 V2 并提示人工继续核对；Agent 模式在模型可用时可以进行语义修订。

### 5. 驳回路径

新建第三个案件：

1. 填写“事实材料不足，当前报告不应发布”；
2. 点击“驳回报告”；
3. 任务进入终态 `rejected`；
4. 报告版本状态为 `rejected`；
5. 草稿和审批意见仍保存在数据库中；
6. 最终导出继续返回 HTTP 409。

### 6. 并发、幂等和重启

- 使用过期 `expected_state_version`：HTTP 409；
- 两个页面使用不同幂等键同时审批：只有先完成条件更新的请求返回 202，另一个返回 409；
- 相同 `Idempotency-Key` 重试：HTTP 202，`replayed=true`，不增加审批或报告版本；
- 在 `waiting_for_approval` 时重启后端：重新请求 `pending-action` 仍返回相同 `action_id`，可以继续审批。

### 7. 数据库检查

PyCharm Database 中应新增：

- `report_versions`：每个版本一行，包含正文、事实/引用快照和状态；
- `agent_approvals`：每次审批一行，包含动作、意见、审核人和幂等键；
- `agent_runs.current_report_version`：当前展示版本；
- `agent_runs.approved_report_version`：最终批准版本，未批准时为空。

审批历史是追加数据，不要直接在数据库中手工改成 `approved`。

### 8. 自动验证

```powershell
python scripts\run_self_test.py
python -m ruff format --check app eval scripts tests
python -m ruff check app eval scripts tests
python -m mypy app
cd frontend
pnpm run build
```

本次实际结果：

- 69 项离线自动测试全部通过，其中第六周新增 7 项；
- Ruff format、Ruff lint 和 mypy 全部通过；
- TypeScript 检查和 Vite 生产构建通过；
- 自动测试不读取真实 Chat/Embedding Key，不产生第三方模型费用。

### 9. 2026-07-31 浏览器端到端实测

使用独立临时数据库 `data/week6_browser_qa.db`、离线模式后端 `127.0.0.1:8010` 和前端 `127.0.0.1:5175` 完成真实页面操作：

1. 提交一条包含买卖合同、付款、交货期限、催告和诉求的合同案件；
2. `RUN #1` 先进入第五周追问，补充交货期限后从同一任务恢复；
3. 报告 V1 进入 `waiting_for_approval`，页面显示“待审批草稿 · V1”，且没有最终报告下载入口；
4. 填写“请在行动建议中明确写出先发送解除通知，并补充保存付款凭证、合同原件和催告记录”，点击“要求修改”；
5. 系统生成 V2，版本列表显示 V2“待审批”和 V1“已被新版本替代”；
6. 分别点击 V1、V2 均可查看对应正文，V2 页面出现“与上一版本的差异”和 unified diff；
7. 点击“批准并发布”，同一任务变为“审批通过”和“已批准最终报告 · V2”；
8. 页面同时出现 Markdown、PDF 下载链接，URL 都指向同一 `run_id` 的后端导出接口；
9. 浏览器控制台未发现本项目自身的 JavaScript 运行错误。

这次验收说明追问 interrupt、审批 interrupt、版本循环和批准后导出是一条完整链路，而不是四个彼此独立的页面演示。

## 二十一、第七周法规版本与案件日期检索验收

### 1. 启动后检查数据库结构

启动后端一次：

```powershell
python -m app.main
```

在 PyCharm Database 打开 `data/legal_copilot.db`，应看到：

- `laws`：一部法规一行；
- `law_versions`：具体版本、生效日、失效日、状态和替代版本；
- `legal_articles.law_version_id`；
- `case_runs.as_of_date`、`agent_runs.as_of_date`；
- `retrieval_logs.law_version_id`、`agent_run_citations.law_version_id`。

不要手工把历史版本的 `status` 改成 `effective`。历史有效性由日期区间判断，`repealed` 表示它现在已经废止。

### 2. Apifox 验证日期边界

请求 2020-12-31：

```http
POST /api/v1/articles/search
Content-Type: application/json

{
  "query": "中华人民共和国合同法第九十四条 中华人民共和国民法典第五百六十三条 迟延履行 催告 解除合同",
  "limit": 10,
  "as_of_date": "2020-12-31"
}
```

预期：

- 响应头 `X-Law-As-Of-Date: 2020-12-31`；
- 结果包含《中华人民共和国合同法》第九十四条；
- `version_label=1999年施行版本`；
- `effect_status=repealed`；
- `effective_from=1999-10-01`、`effective_to=2021-01-01`；
- 不包含《民法典》第五百六十三条。

把日期改为 `2021-01-01`，预期切换为《中华人民共和国民法典》第五百六十三条，`effect_status=effective`，并且不再返回《合同法》第九十四条。这个边界证明失效日期是不包含的。

删除 `as_of_date` 再请求，预期响应头显示服务器当前日期，废止合同法不会作为当前有效结果返回。

非法日期如 `2020-13-40` 应返回 HTTP 422。

### 3. 前端完整闭环

1. 打开 `http://127.0.0.1:5173/#analysis`；
2. 输入事实完整的问题：

```text
合同约定供应商应在收到全部货款后7日内交货，现已过去30日仍未交货，我要求解除合同、退还货款并赔偿损失。请结合中华人民共和国合同法第九十四条和中华人民共和国民法典第五百六十三条分析。
```

3. 案件发生日期选择 `2020-12-31`；
4. 选择“离线可靠”，点击“开始案件分析”；
5. 运行区域显示“法规适用时点 · 2020-12-31”；
6. 报告进入待审批后，引用列表应出现历史《合同法》第九十四条；
7. 卡片显示“已废止 · 历史时点适用”和“1999年施行版本”；
8. 打开引用抽屉，检查版本 ID、1999-10-01 至 2021-01-01 的适用区间和来源；
9. 报告正文顶部显示“法规检索时点：2020-12-31”；
10. 批准报告，最终导出内容仍保留相同版本信息；
11. 点击“分析新案件”，将日期改为 `2021-01-01` 并提交相同问题；
12. 结果应切换为现行《民法典》第五百六十三条。

### 4. 新增法规的版本绑定

通过单条或批量知识库接口新增一条以前不存在的法规。成功响应与法规详情应包含：

- 非空 `law_id`；
- 非空 `law_version_id`；
- `version_label=知识库现行版本`；
- `effect_status=effective`。

这说明新数据不会变成无版本的孤儿条文。当前接口把普通导入绑定到当前版本；导入历史版本仍需要未来的管理员版本接口。

### 5. 自动验证

```powershell
python scripts\run_self_test.py
python -m ruff format --check app eval scripts tests
python -m ruff check app eval scripts tests
python -m mypy app
cd frontend
pnpm run build
```

第七周新增 6 项自动测试：

1. 历史与现行版本替代关系；
2. 2020-12-31 返回历史版本；
3. 2021-01-01 边界切换到现行版本；
4. 不填日期按当前日期并排除废止版本；
5. 搜索接口日期、响应头、版本字段和非法日期；
6. Agent、引用表、报告快照和 Markdown 的版本持久化。

当前完整结果：82 项自动测试通过，前端 TypeScript 与 Vite 生产构建通过，Ruff、mypy 和 OpenAPI 校验通过。

### 6. 2026-07-31 浏览器端到端实测

为避免污染日常开发数据，本次使用独立临时数据库、离线检索后端和单独前端端口完成真实页面操作，验收后已经停止进程并删除临时数据。

第一次提交相同合同问题，案件发生日期填写 `2020-12-31`：

1. 运行轨迹显示“法规适用时点 · 2020-12-31”；
2. 检索节点显示 `provider=hash`、`适用日期=2020-12-31`；
3. 报告顶部显示“法规检索时点：2020-12-31”；
4. 引用结果包含《中华人民共和国合同法》第九十四条；
5. 引用卡片显示“已废止 · 历史时点适用”和“1999年施行版本”；
6. 引用详情显示法规版本 ID，以及 `1999-10-01` 至 `2021-01-01` 的适用区间；
7. 报告正文保留相同的版本标签、效力状态和适用区间。

点击“分析新案件”，把日期改为边界日 `2021-01-01`，再次提交相同问题：

1. 运行轨迹切换为“法规适用时点 · 2021-01-01”；
2. 结果不再包含 1999 年《合同法》版本；
3. 第一条相关依据切换为《中华人民共和国民法典》第五百六十三条；
4. 版本显示“2020年通过（2021年施行）”；
5. 效力状态显示“现行有效”，适用区间从 `2021-01-01` 开始；
6. 浏览器控制台没有本项目 JavaScript 错误。

这组对照验收证明版本过滤是在法规检索之前生效，而不是先召回现行法规再在页面上修改展示文字。

---

## 八、第八周 Agent 运行监控与费用面板验收

### 1. 自动测试

```powershell
python -m pytest -q tests\test_eighth_week.py
python scripts\run_self_test.py
python -m ruff format --check app eval scripts tests
python -m ruff check app eval scripts tests
python -m mypy app
cd frontend
pnpm run build
```

第八周新增 7 项测试：

1. 创建、状态响应与 `X-Trace-ID` 使用同一个 32 位 Trace ID；
2. 单次监控包含根 Span、案件抽取、检索与 Embedding Span；
3. 1～90 天概览能聚合运行、节点平均/P95，非法范围返回 422；
4. Span allowlist 丢弃案件问题、材料和 API Key；
5. Chat 与 Embedding 按每百万 Token 单价估算费用；
6. Chat 优先使用服务商响应中的真实 usage；
7. 无 Trace ID 的历史任务访问监控接口返回明确 404。

完整自测预期为 82 项通过。自动测试固定使用离线模式或 Fake Provider，不调用真实 Chat/Embedding，也不会产生费用。

### 2. Apifox / Swagger 接口验收

先创建一个事实完整的离线任务并记住 `run_id`：

```http
POST /api/v1/runs
Content-Type: multipart/form-data

question=合同约定七日内交货，我方已付款但对方逾期三十日未交货，已经书面催告，要求解除合同、退还货款并赔偿差价。
mode=offline
```

预期：

- HTTP 202；
- 响应头 `X-Trace-ID` 与响应体 `trace_id` 相同；
- `monitoring_url=/api/v1/runs/{run_id}/monitoring`；
- 状态接口返回 `total_duration_ms`、`input_tokens`、`output_tokens`、`estimated_cost_usd` 和 `fallback_count`。

查询单次链路：

```http
GET /api/v1/runs/{run_id}/monitoring
```

预期至少包含 `agent.invoke`、`agent.analyze_case`、`agent.retrieval`、`gen_ai.embeddings`、`agent.review_citations` 和 `agent.write_report`。离线模式的 Chat Token 与费用为 0 是正确结果，不应伪造模型调用。

查询概览：

```http
GET /api/v1/monitoring/overview?days=7
```

检查运行数、成功率、降级率、平均/P95 总耗时、节点平均/P95、累计 Token、累计费用与最近运行。`days=0` 或 `days=91` 应返回 422。

### 3. 费用配置验收

`.env` 中单价单位均为“美元 / 一百万 Token”：

```env
LLM_INPUT_COST_PER_1M_USD=0
LLM_OUTPUT_COST_PER_1M_USD=0
EMBEDDING_COST_PER_1M_USD=0
```

默认 0 只统计 Token，不估算费用。填写服务商实际单价并重启后端后，新运行会按调用时用量计算；历史运行不会被自动改价。不同模型价格不同，不要把示例数字当成真实报价。

### 4. 前端手工验收

1. 启动后端与前端，打开 `http://127.0.0.1:5173/#analysis`；
2. 提交一个事实完整的离线案件；
3. 在执行区确认出现 `Trace xxxxxxxxxxxx… · 查看耗时与费用`；
4. 点击链接或主导航“运行监控”；
5. 概览应显示至少 1 次运行以及节点延迟；
6. 最近运行中选择当前 RUN；
7. 核对 Trace ID、最慢节点、模型、Token、费用、重试和降级次数；
8. Span 列表能区分 ROOT、NODE、CHAT、EMBED；
9. 离线运行显示 `未调用 LLM`、Token 0、费用 0，而不是伪装在线模型；
10. 缩小浏览器宽度，确认指标卡、Trace 摘要和瀑布列表没有横向遮挡。

### 5. 隐私与安全检查

运行案件后，在数据库 `agent_run_spans.attributes` 与后端请求日志中搜索案件全文和测试密钥。预期均不存在。允许出现的只有任务 ID、thread ID、模式、节点、状态、provider/model、Token 数、候选数、重试数和降级错误码等低敏元数据。

本地 SQLite 仍可能在 `agent_runs.question` 保存案件问题，这是业务数据，不是遥测数据，因此数据库文件必须继续被 `.gitignore` 排除并禁止上传 GitHub。

### 6. 2026-08-01 浏览器端到端实测

本次使用独立临时 SQLite、离线 hash 后端和本地 Vite 前端完成真实页面操作，验收后停止了两个进程并删除临时数据库：

1. 首页成功连接 37 条教学法规；
2. 提交事实完整的合同问题后，任务进入 `waiting_for_approval`；
3. 执行区显示 RUN #1、离线规则引擎、法规适用时点和 Trace 快捷链接；
4. 监控概览显示 1 次运行、成功率 100%、降级率 0%、平均/P95 111 ms、Token 0、费用 `$0.000000`；
5. 节点指标展示案件抽取、法规检索、引用审核和报告生成的平均/P95；
6. 单次 Trace 显示 32 位 Trace ID、最慢节点“法规混合检索”、`offline-template` 模型标识和 0 次降级/重试；
7. Span 瀑布包含 ROOT、NODE 与 EMBED，Embedding 明确显示 `hash / chinese-bigram-sha256-v1`；
8. 浏览器控制台只有 Vite 连接与 React 开发提示，没有项目 JavaScript 错误；
9. 390×844 响应式验收下，文档宽度没有超过视口，指标卡为两列，监控容器无横向溢出；
10. 页面明确展示隐私边界，没有把案件全文、Prompt 或 Key 显示在监控数据中。

耗时会因机器、法规条数和首次索引而变化，111 ms 是本次临时环境结果，不是固定性能承诺。
