# 律镜 Legal Copilot Agent

这是一个可独立运行的求职项目：输入案件材料与问题，通过 LangGraph 完成案件要素提取、混合检索、引用审核和 Markdown 法律分析报告生成。

项目默认使用 SQLite 和离线模式，首次启动自动创建 `data/legal_copilot.db` 并导入 `data/sample_laws.jsonl`，不依赖其他仓库、MySQL、Docker 或大模型密钥。配置 OpenAI 兼容接口后可切换到 Agent 模式和真实 Embedding。

## PyCharm 启动

1. 用 PyCharm 打开本项目根目录。
2. 创建 Python 3.11 或更高版本的虚拟环境。
3. 在 PyCharm Terminal 执行：

```powershell
python -m pip install -r requirements.txt
```

4. 新建 Python 运行配置：
   - Module name：`app.main`
   - Working directory：项目根目录
5. 运行后打开 `http://127.0.0.1:8000/docs`。

也可以直接执行：

```powershell
python -m app.main
```

## 第三周前端启动

后端保持在 `http://127.0.0.1:8000` 运行，再打开一个 PyCharm Terminal：

```powershell
cd frontend
pnpm install --registry=https://registry.npmmirror.com
pnpm run dev
```

项目使用 pnpm 11 的依赖脚本白名单，只允许 Vite 构建所需的 `esbuild` 执行安装脚本。若曾经安装失败，更新项目后重新执行一次 `pnpm install` 即可。

浏览器访问 `http://127.0.0.1:5173`。页面支持拖拽上传、离线/Agent 模式、后台进度轮询、引用详情以及 Markdown/PDF 下载。

如果没有 pnpm，可以先安装 Node.js 20 或更高版本，再执行 `corepack enable`。

## Docker Compose 启动

安装 Docker Desktop 后，在项目根目录执行：

```powershell
docker compose up --build
```

- Web 页面：`http://127.0.0.1:3000`
- Swagger：`http://127.0.0.1:8000/docs`
- SQLite 数据通过 `legal-data` volume 持久化。

## 当前接口

- `GET /health`：服务与法规数量检查；
- `POST /api/v1/articles/search`：法规检索；
- `POST /api/v1/cases`：上传 `.txt/.docx/.pdf` 和问题，返回案件要素与引用。
- `GET /api/v1/articles/{article_id}`：根据 ID 回查法条原文；
- `POST /api/v1/runs`：执行完整 LangGraph 工作流；
- `GET /api/v1/runs/{run_id}`：查看任务状态和节点轨迹；
- `GET /api/v1/runs/{run_id}/citations`：查看引用审核结果；
- `GET /api/v1/runs/{run_id}/report`：获取 Markdown 报告；
- `POST /api/v1/runs/{run_id}/retry`：重试失败任务。
- `GET /api/v1/runs/{run_id}/export?format=markdown|pdf`：下载报告文件。

## 第三周 Agent 调用示例

在 Swagger 中调用 `POST /api/v1/runs`，填写：

```text
question=供应商收款后未按合同交货，我能否解除合同并要求赔偿？
mode=offline
```

创建接口立即返回 `queued` 和 `run_id`。前端每 1.5 秒查询状态，完成后读取引用和报告。离线模式不需要模型密钥。

如需使用真实模型，复制 `.env.example` 为 `.env`，设置 `OFFLINE_MODE=false`、LLM 与 Embedding 配置，然后运行：

```powershell
python scripts\reindex_embeddings.py
```

产品范围见 [PRODUCT_SPEC.md](PRODUCT_SPEC.md)，详细开发计划见 [PROJECT_GOALS.md](PROJECT_GOALS.md)，完整验证步骤见 [SELF_TEST.md](SELF_TEST.md)。

如果主要用于学习和准备求职，请优先阅读 [学习文档与追加式开发日志](docs/LEARNING_JOURNAL.md)。它按开发阶段解释架构、代码流转、测试、技术取舍和面试回答。

接口资料：

- [中文接口说明](docs/API_REFERENCE.md)
- [可直接导入 Apifox 的 OpenAPI 3.0.3 文件](docs/openapi.json)
- [DeepSeek、Embedding、MySQL、Redis 配置迁移说明](docs/CONFIGURATION.md)
- [逐接口含义、请求参数与返回示例](docs/API_GUIDE_DETAILED.md)

> 本项目为软件工程与 AI 技术演示，生成内容不构成法律意见；样例法规正式使用前必须核对权威来源。
