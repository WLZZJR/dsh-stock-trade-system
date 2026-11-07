# REASON_CODES：原因码注册表

> **唯一事实来源（ADR-0017）。** Pre-flight、任务执行与 API 错误使用的全部原因码以本表为准；代码中对应一个版本化枚举。原因码一经发布**不得改名或复用**，只能标记废弃。新增原因码须同时更新本表、对应规则章节与测试。
>
> **注册表版本：** `reason_codes_v1`（2026-11-06）

## 1. Pre-flight：`BLOCK` → `not_applicable`（模型在金融逻辑上不适用）

| 原因码 | 触发条件 | 定义处 |
|---|---|---|
| `SECTOR_INCOMPATIBLE_WITH_FCFF` | 发行人 SIC 命中 `sic_applicability_v1`，且请求 `dcf_fcff` / `ev_ebitda` | VALUATION 18.0.3 #1 |
| `NEGATIVE_EARNINGS` | 当期或 TTM 净利润 ≤ 0 时请求 PE | VALUATION 18.0.3 #6 |
| `NEGATIVE_OR_ZERO_EBITDA` | 当期或 TTM EBITDA ≤ 0 时请求 EV/EBITDA | VALUATION 18.0.3 #9 |
| `ESTIMATES_PROVIDER_NOT_CONFIGURED` | 请求 Forward PE / PEG（不写入 `valuation_runs`） | VALUATION 18.0.3 #7 |

## 2. Pre-flight：`BLOCK` → `insufficient_data`（数据缺失或数学约束违反）

| 原因码 | 触发条件 | 定义处 |
|---|---|---|
| `MISSING_REQUIRED_FIELD` | 核心字段缺失或非法（如 `shares_outstanding <= 0`）；独立估值 API 返回 422 | VALUATION 18.0.3 #2 |
| `WACC_MISSING` | 无 WACC 假设 | VALUATION 18.0.3 #3 |
| `WACC_UNCONFIRMED` | WACC 仅为未确认的建议 | VALUATION 18.0.3 #3 |
| `WACC_LTE_TERMINAL_GROWTH` | WACC ≤ 终值增长率 | VALUATION 18.0.3 #5 |
| `RATE_BASIS_MISMATCH` | WACC、g 与现金流的币种或名义 / 实际口径不一致 | VALUATION 18.0.3 #5 |
| `EFFECTIVE_TAX_RATE_UNAVAILABLE` | `income_before_tax <= 0` 且无已确认税率假设 | VALUATION 18.0.3 #8 |
| `TTM_PERIOD_INCOMPLETE` | 缺季度、财年变更或期间不连续，TTM 不可用 | FINANCIAL_ENGINE 17.0 |
| `REVERSE_DCF_NO_SOLUTION` | 求解区间内无解或不收敛 | VALUATION 18.2 |
| `SCENARIO_ASSUMPTIONS_MISSING` | 缺少 Bear / Base / Bull 情景假设 | VALUATION 18.1.3 |
| `PEER_SET_INSUFFICIENT` | 剔除后有效 Peer 少于 3 个 | VALUATION 18.3.1 |

## 3. Pre-flight：`WARN` → `degraded`（执行，但报告必须披露）

| 原因码 | 触发条件 | 定义处 |
|---|---|---|
| `MINORITY_INTEREST_UNAVAILABLE_ASSUMED_ZERO` | 少数股东权益缺失，经配置显式允许按 0 处理 | VALUATION 18.0.3 #4 |
| `LEASE_LIABILITIES_UNAVAILABLE_ASSUMED_ZERO` | 融资租赁负债缺失，同上 | VALUATION 18.0.3 #4 |
| `PREFERRED_STOCK_UNAVAILABLE_ASSUMED_ZERO` | 优先股缺失，同上 | VALUATION 18.0.3 #4 |
| `LONG_TERM_INVESTMENTS_UNAVAILABLE_ASSUMED_ZERO` | 长期投资缺失，同上 | VALUATION 18.0.3 #4 |
| `DILUTED_SHARES_PROXY` | 使用稀释股数代理口径 | DATA_MODEL 12.6 |
| `EBIT_DERIVED_FROM_PRETAX` | `ebit` 由税前利润 + 利息费用回退推导 | DATA_MODEL 12.6 |
| `EFFECTIVE_TAX_RATE_REPLACED_BY_USER_INPUT` | 以已确认的用户税率替代不可用的有效税率 | VALUATION 18.0.3 #8 |
| `PEER_SET_NOT_CONFIRMED` | 未提供 Peer Set，仅输出标的自身倍数 | VALUATION 18.3.1 |

## 4. 任务与执行（Run / Task 的 `error_json`）

| 原因码 | 含义 | 定义处 |
|---|---|---|
| `STAGE_TIMEOUT` | 子阶段超时 | AGENT_WORKFLOW 22.4 |
| `WORKER_LOST` | Worker 失联，Reaper 判定重试耗尽 | AGENT_WORKFLOW 22.4 |
| `TOKEN_BUDGET_EXCEEDED` | LLM token 预算耗尽（MVP-2） | AGENT_WORKFLOW 21.4 |

## 5. API 与报告

| 原因码 | 含义 | 定义处 |
|---|---|---|
| `SECTION_NOT_ENABLED` | 请求了本档未启用的研究章节，HTTP 422 | API_CONTRACT 25.2 |
| `NARRATIVE_REJECTED` | LLM 段落数字扫描违规，段落被省略（MVP-2） | PRD 4.3.2 |

## 6. 已废弃 / 已合并

| 原因码 | 处理 | 说明 |
|---|---|---|
| `DATA_REQUIRED_FIELD_MISSING` | 合并为 `MISSING_REQUIRED_FIELD` | 原仅出现在 API_CONTRACT 25.4 示例中，与 Pre-flight 原因码含义重复（2026-11-06） |
