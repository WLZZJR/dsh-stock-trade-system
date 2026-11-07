# MCP_CONTRACT：MCP 工具契约（MVP-2）

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 26. MCP Server 设计

MCP Server 是跨 Agent 的通用工具层；它只调用 Application Services，不实现财务算法。MCP 工具名保持稳定，输出必须机器可解析。

### 26.1 MVP 工具清单

> MCP Server 整体属于 **MVP-2**。工具只包装 MVP-1 已验证的 Application Services；对外只使用 `run_id`。

| 工具名 | 用途 | 只读/写入 | 运行方式 |
|---|---|---|---|
| `resolve_instrument` | 识别公司和上市证券 | 只读 | 同步 |
| `screen_equities` | 股票筛选 | 只读 | 同步/较大任务异步 |
| `get_company_snapshot` | 公司与证券概览 | 只读 | 同步 |
| `research_company` | 创建研究 Run | 创建任务 | 异步，返回 run_id |
| `get_research_run` | 查询 Run 状态和当前阶段 | 只读 | 同步 |
| `get_research_report` | 获取完成报告 | 只读 | 同步 |
| `compare_companies` | 多家公司比较 | 只读/计算 | 同步或异步 |
| `run_valuation` | 启动估值计算 | 创建任务 | 异步或同步轻任务 |
| `analyze_risk` | 公司/组合风险分析 | 计算 | 异步或同步轻任务 |
| `search_research_evidence` | 检索证据和披露 | 只读 | 同步 |
| `fetch_filing_section` | 受控读取 10-K Item 1 / 1A（见 23.1） | 只读 | 同步，分页 |
| `manage_watchlist` | 自选股管理 | 写入 | 同步，需权限 |

**写类工具说明（v1.5）：** `manage_watchlist` 的写操作、假设确认等改变持久状态的调用属于 21.1 的 `write` 级，经 MCP 调用时必须携带 `confirmation_token`；只读与 `propose` 类工具无此要求。

### 26.2 工具输入 Schema 约定

工具参数统一使用 JSON Schema / Pydantic 定义，至少包含：
- `workspace_id`（仅内部/授权上下文注入，不信任模型自行指定）；
- `listing_id` 或能够消歧的 identifier；
- `as_of` / `research_as_of`；
- `profile`；
- `include_evidence`；
- `max_results`；
- `filters` / `fields`。

安全原则：workspace 与用户身份必须从已认证连接上下文取得，不能只依赖 LLM 传入参数。

### 26.3 `research_company` 输入/输出示例

字段名与取值与 REST 25.2 完全一致（`sections`、`models` 使用同一枚举），MCP 不得自行改名或另设别名。

输入：

```json
{
  "instrument": {
    "listing_id": "uuid"
  },
  "profile": "balanced",
  "horizon_years": 3,
  "sections": ["business_model", "industry", "financial_quality", "growth", "valuation", "risk_metrics"],
  "models": ["dcf_fcff", "reverse_dcf", "pe_ttm", "pe_latest_fy", "ev_ebitda"],
  "valuation_assumption_ids": ["uuid"],
  "include_counter_thesis": true
}
```

输出：

```json
{
  "status": "accepted",
  "run_id": "uuid",
  "poll_tool": "get_research_run",
  "message": "Research run accepted. Retrieve status with run_id."
}
```

### 26.4 `get_research_run` 输出示例

```json
{
  "run_id": "uuid",
  "status": "running",
  "stage": "valuation",
  "data_quality_status": "warn",
  "progress": {
    "completed": 5,
    "total": 7
  },
  "warnings": ["Analyst estimates are not available for this listing."],
  "updated_at": "2026-11-04T00:00:00Z"
}
```

进度只能在真实阶段完成后更新，不能让模型编造百分比。

### 26.5 MCP Resources / Prompts

可选暴露：

- `gei://instruments/{listing_id}`：证券标准化档案；
- `gei://research-runs/{run_id}`：研究任务摘要；
- `gei://reports/{report_id}`：报告内容或报告元数据；
- `gei://data-sources`：当前连接的数据源和覆盖范围；
- Prompt `company_research`：公司研究指引；
- Prompt `valuation_review`：估值假设复核指引；
- Prompt `risk_challenge`：反方风险审查指引。

Resources 不得暴露密钥、原始付费数据全文或未授权内容。

### 26.6 MCP Transport

- 本地单机开发：`stdio`；
- 远程服务器：Streamable HTTP + TLS + 认证；
- 新项目不以旧 SSE 传输作为默认方案；
- 对 MCP Server 设置请求超时、每用户限流、并发限制和审计日志。
