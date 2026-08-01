## 三个数据文件和法规版本表分别是什么

| 文件                    | 作用                       | 是否建议提交 GitHub |
| ----------------------- | -------------------------- | ------------------- |
| `legal_copilot.db`      | 本地开发和实际运行数据     | 不提交              |
| `test_legal_copilot.db` | 自动化测试产生的数据       | 不提交              |
| `sample_laws.jsonl`     | 初始化法律知识库的原始数据 | 可以提交            |

### 1. `legal_copilot.db`

这是项目实际运行使用的 SQLite 数据库。

你在网页上提交问题、运行 Agent、检索法条和生成报告后，相关数据会保存在这里。

记录数会随着法规导入、测试和案件运行变化，不应把某一次截图中的数量当成固定值。第七周主要业务表如下：

| 数据表                | 保存内容 |
| --------------------- | -------- |
| `laws`                | 法规实体，例如“中华人民共和国民法典” |
| `law_versions`        | 版本标签、生效/失效日期、状态、来源和替代关系 |
| `legal_articles`      | 法律条文，并用 `law_version_id` 绑定精确版本 |
| `article_embeddings`  | 不同 provider/model 对应的条文向量 |
| `case_runs`           | 同步案件分析记录和可选 `as_of_date` |
| `retrieval_logs`      | 同步案件召回的条文、法规版本和分数 |
| `agent_runs`          | Agent 任务、法规日期、状态、轨迹和报告 |
| `agent_run_citations` | Agent 引用、精确法规版本、分数和审核结果 |
| `agent_clarifications` | 多轮追问问题和回答 |
| `report_versions`     | 不可覆盖的报告、事实与引用快照 |
| `agent_approvals`     | 审批动作、意见、幂等键和状态版本 |

其中比较重要的表是：

- `agent_runs`：记录你输入的问题、选择的运行模式、任务状态、识别出的案件事实、Agent 执行轨迹和最终报告。
- `agent_run_citations`：记录报告引用了哪些法条和哪个 `law_version_id`，以及分数和审核状态。
- `laws` / `law_versions`：把“哪一部法律”和“这部法律的哪一个版本”分开。
- `legal_articles`：保存具体条文并关联法规版本。
- `article_embeddings`：用于检索法条的向量数据。

这个数据库可能包含你手工输入的案件问题，所以不应该上传到 GitHub。目前项目的 `.gitignore` 已经将它排除。

### 2. `test_legal_copilot.db`

这是自动化测试专用数据库。

运行：

```
python scripts\run_self_test.py
```

时，测试程序会使用这个数据库，而不会向正式的 `legal_copilot.db` 写入测试数据。

它与正式库使用相同表结构，但记录数取决于本次运行了哪些测试。第七周测试还会创建法规版本演示数据、历史/现行日期查询和 Agent 引用快照。

两个数据库分开的主要原因是：防止自动化测试污染你平时演示和开发的数据。

如果后端和测试程序都已经停止，`test_legal_copilot.db` 可以删除。下次运行自测时会重新生成。

### 3. `sample_laws.jsonl`

它不是数据库，而是法律知识库的初始化数据文件。

JSONL 是 JSON Lines 的缩写，特点是每一行都是一个独立的 JSON 对象。例如：

```
{"law_name":"中华人民共和国劳动合同法","article_number":"第十条","content":"建立劳动关系，应当订立书面劳动合同。","source":"sample"}
```

当前文件有 36 行，也就是 36 条内置教学法条。每条数据包含：

- `law_name`：法律名称
- `article_number`：条款编号
- `content`：条文正文
- `source`：数据来源

项目首次启动或数据库中没有这些法条时，会将该文件中的数据导入 `legal_articles` 表。

它们之间的关系是：

```
sample_laws.jsonl
        ↓ 项目初始化
legal_copilot.db 中的 legal_articles
        ↓ 启动时创建 laws / law_versions 并绑定 law_version_id
        ↓ 按案件日期过滤有效版本
        ↓ 建立并读取检索数据
article_embeddings
        ↓ 用户提交案件
agent_runs(as_of_date) + agent_run_citations(law_version_id)
```

第七周还会增量准备一组版本切换演示数据：

- 《中华人民共和国合同法》第九十四条：1999-10-01 生效，2021-01-01 起不再适用；
- 《中华人民共和国民法典》现行版本：2021-01-01 生效；
- 民法典版本通过 `supersedes_version_id` 指向被替代的合同法历史版本。

日期区间采用 `[effective_from, effective_to)`。因此 2020-12-31 可以检索历史合同法，2021-01-01 会切换到民法典。`status=repealed` 表示旧版本现在已经废止，不代表它在历史有效期内从未有效。

修改 `sample_laws.jsonl` 后，不一定会覆盖数据库中已有的法条，因为初始化程序按“法律名称 + 条号”增量导入。新增条文会自动绑定到该法规的当前版本。不要为了更新版本随意删除正式库；更安全的做法是先备份，并通过受审计的迁移或导入流程新增版本。

另外，项目里还有一个 `eval/dataset.jsonl`，它保存了 24 条评测案例及标准答案，只用于运行 Agent 效果评测，不是用户业务数据，也不会在普通启动时写入业务数据库。

## 4. 第八周新增的监控数据

`agent_runs` 新增以下聚合字段：

| 字段 | 含义 |
|---|---|
| `trace_id` | 32 位 Trace ID，用于关联创建请求、日志和 Agent Span |
| `total_duration_ms` | 根 `agent.invoke` Span 累计耗时 |
| `input_tokens` | Chat 与 Embedding 输入 Token 合计 |
| `output_tokens` | Chat 输出 Token 合计 |
| `estimated_cost_usd` | 按运行时配置单价估算的美元费用 |
| `fallback_count` | 有明确回退原因的计量 Span 数 |

新增 `agent_run_spans`：

| 字段组 | 保存内容 |
|---|---|
| 关联 | `run_id`、`trace_id`、`span_id`、`parent_span_id` |
| 位置 | Span 名称、工作流节点、状态 |
| 性能 | 开始/结束时间、`duration_ms` |
| 模型 | provider、model、输入/输出 Token、估算费用 |
| 可靠性 | 重试次数、降级原因、错误码 |
| 属性 | 经过 allowlist 的低敏 JSON 元数据 |

同一个任务可能因追问、修改或审批恢复而产生多次 `agent.invoke` 根 Span，所以聚合耗时是这些根 Span 之和。Span 使用 `(run_id, span_id)` 唯一约束，checkpoint 恢复时重复持久化不会产生重复行。

不要把 `agent_run_spans` 当成案件业务正文表。它故意不保存问题、材料和 Prompt。真正的案件问题仍在 `agent_runs.question`，因此整个数据库文件依旧属于敏感本地数据，禁止提交 GitHub。
