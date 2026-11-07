# API_CONTRACT：REST API 契约

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 24. API 通用规范

- Base path：`/api/v1`；
- JSON 请求/响应；
- 时间使用 ISO 8601 UTC；日期使用 `YYYY-MM-DD`；
- 金额返回字符串或 decimal-safe JSON 结构，防止 JavaScript 浮点误差；
- 所有列表接口支持分页；
- 写操作支持 `Idempotency-Key`；
- 错误统一为 `application/problem+json` 风格；
- API 版本变更不得破坏已发布 MCP 工具的旧 Schema。

### 24.1 鉴权

**MVP-1 最低要求：** 单用户（Owner）登录 + 会话；远程 Linux 部署强制 TLS，禁止匿名访问任何业务接口；本地 Windows 部署默认仅绑定 localhost，同样需要登录。API Key 与 OAuth 属于 MVP-2（MCP / 外部 Agent 接入时启用）。

- Web 使用 HttpOnly Secure Cookie / session 或经过安全审查的 JWT；
- Service / MCP 使用 scoped API Key 或 OAuth 2.1（远程多用户部署建议 OAuth）；
- API Key 仅存 hash，不回显完整密钥；
- Scope 示例：`research:read`、`research:write`、`market:read`、`portfolio:read`、`watchlist:write`、`admin:data_sources`；
- 对 workspace 资源必须进行服务端归属校验；
- 所有写操作记录 audit log。

## 25. 核心 REST Endpoints

| Method | Path | 用途 | 响应 |
|---|---|---|---|
| GET | `/health/live` | 存活探针 | 200 |
| GET | `/health/ready` | 依赖就绪探针 | 200/503 |
| GET | `/instruments/resolve` | 证券消歧 | 200 |
| GET | `/instruments/{listing_id}` | 上市证券详情 | 200 |
| POST | `/screenings` | 执行筛选 | 200 或 202 |
| GET | `/screenings/{screening_id}` | 查询筛选结果 | 200 |
| GET | `/issuers/{issuer_id}/snapshot` | 公司概览 | 200 |
| POST | `/research-runs` | 创建研究 Run | 202 |
| GET | `/research-runs/{run_id}` | Run 状态、当前阶段、数据质量状态 | 200 |
| POST | `/research-runs/{run_id}/cancel` | 取消 Run | 202 |
| GET | `/research-runs/{run_id}/tasks` | 内部子任务状态（诊断用，需管理权限） | 200 |
| POST | `/valuation-assumptions` | 创建估值假设（WACC、税率、情景假设；见 18.1.3） | 201 |
| POST | `/valuations` | 执行估值（同步 Pre-flight + 确定性计算） | 200 / 422 |
| GET | `/valuations/{valuation_id}` | 获取估值结果与 Pre-flight 报告 | 200 |
| POST | `/peer-sets` | 创建/新版本 Peer Set | 201 |
| GET | `/issuers/{issuer_id}/risk-metrics` | 确定性风险指标（MVP-1） | 200 |
| POST | `/risk/assessments` | Agent 风险分析（MVP-2） | 202 |
| GET | `/reports/{report_id}` | 获取报告元数据 | 200 |
| GET | `/reports/{report_id}/content` | 获取报告内容 | 200 |
| POST | `/watchlists` | 创建自选列表 | 201 |
| POST | `/watchlists/{id}/items` | 添加股票 | 201 |
| GET | `/watchlists/{id}` | 获取自选列表 | 200 |
| POST | `/alerts` | 创建告警规则（MVP-1 仅站内） | 201 |
| GET | `/data-sources` | 查看数据源状态 | 200 |

### 25.1 Resolve Instrument 示例

`GET /api/v1/instruments/resolve?query=MSFT&market=US`

可能响应：

```json
{
  "matches": [
    {
      "issuer_id": "uuid",
      "security_id": "uuid",
      "listing_id": "uuid",
      "issuer_name": "Microsoft Corporation",
      "ticker": "MSFT",
      "venue_mic": "XNAS",
      "currency": "USD",
      "identifiers": {
        "isin": "...",
        "figi": "..."
      },
      "match_confidence": "high"
    }
  ],
  "requires_user_selection": false
}
```

以上为响应形状示例，不代表系统应硬编码该证券数据。若多个候选均匹配，返回 `requires_user_selection=true`，不得自行选择。

### 25.2 创建研究任务

`POST /api/v1/research-runs`

请求：

```json
{
  "listing_id": "uuid",
  "profile": "balanced",
  "horizon_years": 3,
  "research_as_of": "2026-11-04T00:00:00Z",
  "sections": [
    "business_model",
    "industry",
    "financial_quality",
    "growth",
    "valuation",
    "risk_metrics"
  ],
  "valuation_models": ["dcf_fcff", "reverse_dcf", "pe_ttm", "pe_latest_fy", "ev_ebitda"],
  "valuation_assumption_ids": ["uuid", "uuid"],
  "peer_set_id": null,
  "include_counter_thesis": true,
  "save_to_watchlist": false
}
```

以上为 MVP-2/3 完整 Schema 形状示例（字段名在 REST 与 MCP 两种入口统一使用 `horizon_years`，不得各自改名）。MVP-1 中 `sections` 仅接受 `financial_quality`、`valuation`、`risk_metrics`；`business_model`、`industry`、`growth`（定性部分）与 `include_counter_thesis` 属于 MVP-2，MVP-1 收到示例中其余取值时返回 `422`（`code = SECTION_NOT_ENABLED`），不得静默忽略。`valuation_assumption_ids` 引用须事先通过 `POST /valuation-assumptions` 创建（见 18.1.3）；缺失或未确认时不阻止 Run 创建，估值按 18.0.3 BLOCK 并在报告中说明。`research_as_of` 省略时取服务端当前时间并在响应中回显。

响应（HTTP 202）：

```json
{
  "run_id": "uuid",
  "status": "queued",
  "status_url": "/api/v1/research-runs/uuid",
  "created_at": "2026-11-04T00:00:00Z"
}
```

### 25.3 执行估值

`POST /api/v1/valuations`

请求至少需要：

```json
{
  "listing_id": "uuid",
  "model_type": "dcf_fcff",
  "valuation_date": "2026-11-04",
  "currency": "USD",
  "data_snapshot_id": "uuid",
  "scenarios": {
    "bear": {"revenue_growth": "0.08", "terminal_growth": "0.02"},
    "base": {"revenue_growth": "0.14", "terminal_growth": "0.025"},
    "bull": {"revenue_growth": "0.20", "terminal_growth": "0.03"}
  },
  "assumptions": {
    "wacc": {
      "value": "0.095",
      "currency": "USD",
      "rate_type": "nominal",
      "source_type": "user_input",
      "rationale": "...",
      "status": "confirmed"
    },
    "tax_rate": {
      "value": "0.18",
      "rate_type": "nominal",
      "source_type": "user_input",
      "rationale": "...",
      "status": "confirmed"
    },
    "forecast_years": 5
  },
  "peer_set_id": null
}
```

响应必须包含 `preflight_status`（PASS / WARN / BLOCK）、`status`（completed / degraded / not_applicable / insufficient_data）、`preflight_report`（含原因码）和 `data_snapshot_id`。`BLOCK` 时不返回任何估值数字。

**同步语义（v1.4）：** Pre-flight 与确定性计算在请求内同步完成（DCF、相对估值为纯计算，不经 Worker）。`PASS` / `WARN` 返回 HTTP 200 与完整结果；`BLOCK` 返回 HTTP 422（`application/problem+json`，`code` 取首个阻断原因码，并附 `preflight_report`），不含估值数字，但仍写入一条 `valuation_runs`（`status = not_applicable / insufficient_data`）以便审计。Research Run 内部由 Worker 调用同一应用服务，不经 HTTP。请求中的 `assumptions` 按 18.1.3 先落库为 `valuation_assumptions`，再生成或校验快照。

注意：请求中的数字仅用于说明 Schema。生产实现必须检查假设合理性、数据来源、缺失项、币种与股数口径。估值服务可以拒绝不满足基本约束的输入。

### 25.4 统一错误格式

```json
{
  "type": "https://example.invalid/problems/data-unavailable",
  "title": "Required data unavailable",
  "status": 422,
  "code": "MISSING_REQUIRED_FIELD",
  "detail": "Required financial facts are unavailable for the selected period.",
  "trace_id": "trace-uuid",
  "missing_fields": ["shares_outstanding", "net_debt"]
}
```

错误必须区分：参数错误、证券歧义、数据缺失、授权失败、供应商限流、任务冲突、模型不适用、内部错误。
