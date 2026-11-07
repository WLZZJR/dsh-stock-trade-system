# VALUATION：估值模型与 Pre-flight

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 18. 估值模型与前置检查机制

### 18.0 估值引擎“起飞前检查器”（Pre-flight Check）契约

Pre-flight 是 MVP-1 的**确定性校验引擎**，不是 LLM 审核功能。估值引擎必须采用**两阶段执行架构（Pre-flight Check $\rightarrow$ Deterministic Execution）**。面对缺失字段、行业不适用或数学边界违规，引擎**严禁静默将缺失值填 0，也严禁直接抛出未捕获的 Python `TypeError` / `ZeroDivisionError` 导致 HTTP 500**，而是必须返回结构化的 `ValuationPreFlightReport`。

#### 18.0.1 两个维度：Pre-flight 结论与估值状态

| Pre-flight 结论 | 含义 | 是否执行估值 | 对应估值状态 `valuation_runs.status` |
|---|---|---|---|
| `PASS` | 所有阻断性条件满足，无警告 | 执行 | `completed` |
| `WARN` | 存在非阻断问题（显式降级、代理口径等） | 执行，报告必须披露全部警告 | `degraded` |
| `BLOCK` | 模型在金融逻辑上不适用 | 不执行 | `not_applicable` |
| `BLOCK` | 核心必需字段缺失或数学约束违反 | 不执行 | `insufficient_data` |

映射关系由 `valuation_runs` 的 `chk_preflight_status_mapping` 约束强制。`BLOCK` 必须附带原因码，调用方（Web、Orchestrator）依据原因码决定提示切换模型还是放弃。

```python
from enum import StrEnum
from pydantic import BaseModel, Field

class PreFlightStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"

class ValuationStatus(StrEnum):
    COMPLETED = "completed"                 # 正常完成全部情景计算
    DEGRADED = "degraded"                   # 完成计算，但使用了显式降级规则（附带 Warning）
    NOT_APPLICABLE = "not_applicable"       # 模型在金融逻辑上不适用（如银行跑 FCFF、亏损企业跑 PE）
    INSUFFICIENT_DATA = "insufficient_data" # 核心必需字段缺失或数学约束违反，拒绝硬算

class PreFlightIssue(BaseModel):
    code: str                               # 原因码，如 'MISSING_REQUIRED_FIELD', 'WACC_LTE_TERMINAL_GROWTH'
    field: str | None = None
    message: str
    is_blocking: bool                       # True 则直接阻断该模型计算

class ValuationPreFlightReport(BaseModel):
    model_type: str
    preflight_status: PreFlightStatus
    valuation_status: ValuationStatus
    rules_version: str                      # 校验规则必须版本化
    data_snapshot_id: str                   # 必须关联数据快照
    checks: list[str] = Field(default_factory=list)          # 已执行的检查项
    blockers: list[PreFlightIssue] = Field(default_factory=list)
    warnings: list[PreFlightIssue] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
```

#### 18.0.2 最低校验项

- 发行主体和证券身份已唯一确认；
- 估值价格日期有效，且为 `research_as_of` 当时可得的价格；
- 财务数据不晚于研究时点可用（PIT）；
- 所需财务项目齐备；FY、季度及 TTM 期间完整性符合规则（17.0）；
- 财务金额、价格和估值币种一致，或存在明确换算记录；
- 股价、股数和公司行动口径一致；
- SBC 处理方式明确，且无重复加回（18.1.2）；
- WACC 存在、已确认且符合输入规则（18.1.1）；
- Terminal Growth Rate 小于 WACC；
- 模型适用性检查通过（ADR-0017）；
- 关键财务数据不存在未解决的重大冲突；
- 缺失数据和低质量数据均被显式列出。

#### 18.0.3 标准判定与原因码

> 全部原因码及其状态映射的唯一事实来源是 [REASON_CODES.md](REASON_CODES.md)（ADR-0017）；本节描述判定规则。

1. **行业适用性拦截（`BLOCK` → `not_applicable`）：** 发行人 SIC 属于银行、保险、REIT 等，且请求模型为 `dcf_fcff` 或 `ev_ebitda` 时，返回 `SECTOR_INCOMPATIBLE_WITH_FCFF`。MVP-1 不提供 PB/ROE、FFO 等替代模型，Web 与报告必须明确提示“该行业在 MVP-1 中仅支持 PE”；后续版本由 Orchestrator 自动切换为行业专用模型。适用性规则表按 SIC 维护并版本化，**行业分类不等于模型适用性**。初始版本 `sic_applicability_v1`（ADR-0017）拦截：6000–6199（存款与非存款信贷机构）、6200–6299（证券与商品经纪）、6300–6399（保险承保）、6722 / 6726（基金、单位信托与封闭式投资公司）、6770（空白支票公司 / SPAC）、6798（REIT）。
2. **核心字段缺失拦截（`BLOCK` → `insufficient_data`）：** 缺少 `revenue`、`ebit`、`shares_outstanding`（或 `<= 0`）等核心字段时，返回 `MISSING_REQUIRED_FIELD` 并列出 `missing_fields`。独立估值 API 调用返回 HTTP `422`（见 25.3 同步语义）；在 Research Run 内部调用时，仅该模型对应的 `valuation_runs` 记为 BLOCK，`valuation` Task 在**全部**请求模型均 BLOCK 时才标记 `skipped`（部分模型 BLOCK 时 Task 仍 `succeeded`，BLOCK 项在报告“不适用与未支持项”列出），均不阻断其他章节生成。
3. **用户输入缺失拦截（`BLOCK` → `insufficient_data`）：** 缺少已确认的 WACC 返回 `WACC_MISSING`；WACC 仅为 `unconfirmed` 的 Agent 建议返回 `WACC_UNCONFIRMED`。**不允许通过隐藏默认值绕过。**
4. **次要字段缺失显式降级（`WARN` → `degraded`）：** 存在 `total_debt` 和 `cash_and_equivalents`，但缺失 `minority_interest`、`lease_liabilities`、`preferred_stock` 或 `long_term_investments` 时，仅在配置显式允许降级时将其按 0 纳入股权桥接计算，记录 `MINORITY_INTEREST_UNAVAILABLE_ASSUMED_ZERO` 等警告，并在报告中强制高亮。使用稀释股数代理口径时记录 `DILUTED_SHARES_PROXY`（见 12.6）；`ebit` 由税前利润回退推导时记录 `EBIT_DERIVED_FROM_PRETAX`（见 12.6）。
5. **数学与金融边界拦截（`BLOCK` → `insufficient_data`）：**
   - $\text{WACC} \le g$ 时返回 `WACC_LTE_TERMINAL_GROWTH`。MVP-2 中若该假设由 Valuation Agent 生成，Orchestrator 将错误反馈给 Agent 要求修正（最多重试 1 次）。
   - WACC、g 与现金流预测的币种或名义/实际口径不一致时返回 `RATE_BASIS_MISMATCH`。
6. **亏损企业 PE（`BLOCK` → `not_applicable`）：** 当期或 TTM 净利润 $\le 0$ 时返回 `NEGATIVE_EARNINGS`，不得输出负数 PE 参与同业分位排名。
7. **未支持模型（`BLOCK` → `not_applicable`）：** Forward PE / PEG 返回 `ESTIMATES_PROVIDER_NOT_CONFIGURED`，界面显示 `N/A — Estimates provider not configured`。该类未支持模型不写入 `valuation_runs`，仅在 API 响应与报告“不适用与未支持项”中列出。
8. **有效税率不可用（`BLOCK` → `insufficient_data`，可由用户输入豁免）：** 按 12.6 节定义，`income_before_tax <= 0` 时 `effective_tax_rate` 不可用，返回 `EFFECTIVE_TAX_RATE_UNAVAILABLE`。DCF 的 NOPAT 计算依赖 Tax Rate；若用户已在 `valuation_assumptions` 中提供 `name = 'tax_rate'` 的已确认（`status = confirmed`）假设（如使用法定税率或历史正常化税率），Pre-flight 改为 `WARN` → `degraded` 并记录 `EFFECTIVE_TAX_RATE_REPLACED_BY_USER_INPUT`；否则维持 `BLOCK`，不得静默回退到 0 或任意默认税率。
9. **EV/EBITDA 的 EBITDA 边界（`BLOCK` → `not_applicable`）：** 定义 $\text{EBITDA} = \text{ebit} + \text{da\_expense}$（均取自 12.6 标准概念，`da_expense` 已标准化为正数）。当期或 TTM `EBITDA <= 0` 时返回 `NEGATIVE_OR_ZERO_EBITDA`，不得输出负数或除零产生的 EV/EBITDA 参与同业分位排名，与第 6 条的 `NEGATIVE_EARNINGS`（针对 PE/净利润）处理方式对称，但原因码与触发字段不同，两者不得混用。

### 18.1 DCF

MVP 以 FCFF DCF 为主：

$$\text{FCFF} = \text{NOPAT} + \text{D\&A} - \text{Capex} - \Delta \text{NWC}, \quad \text{NOPAT} = \text{EBIT} \times (1 - \text{Tax Rate})$$

其中 EBIT 为**包含 SBC 费用**的经营利润口径（见 18.1.2）。

显式预测期企业价值：

$$\text{EV} = \sum_{t=1}^{n} \frac{\text{FCFF}_t}{(1 + \text{WACC})^t} + \frac{\text{TV}}{(1 + \text{WACC})^n}$$

Gordon Growth Terminal Value：

$$\text{TV} = \frac{\text{FCFF}_{n+1}}{\text{WACC} - g}$$

股权价值：

$$\text{Equity Value} = \text{Enterprise Value} - \text{Net Debt} - \text{Other Claims} + \text{Non-operating Assets}$$

桥接项口径（v1.6，ADR-0003，概念定义见 DATA_MODEL 12.6）：

- Net Debt = `total_debt` + `lease_liabilities`（仅融资租赁）− `cash_and_equivalents` − `short_term_investments`；
- Other Claims = `minority_interest` + `preferred_stock`；
- Non-operating Assets = `long_term_investments`；
- 上述桥接项缺失时，只能按 18.0.3 第 4 条显式降级为 0，不得静默补 0。

每股价值（需考虑 ADR 换算比例 $\text{ADR Ratio}$；MVP-1 不纳入 ADR，固定为 1）：

$$\text{Value per Share} = \frac{\text{Equity Value}}{\text{Diluted Shares Outstanding}} \times \text{ADR Ratio}$$

实现要求：
- 严格执行 18.0 节的 Pre-flight Check；
- 检查税率、负营运资本、负 Capex 或异常值；
- 允许分阶段收入增长率和利润率；
- 清楚区分现金、债务、租赁负债、少数股东权益和非经营资产；
- 股数、ADR ratio、币种和股份类别必须正确映射；
- 对金融机构等不适用 FCFF 的业务给出模型不适用提示（见 18.0），后续可实现 Excess Return / Dividend Discount 等模型。

#### 18.1.1 WACC 输入规则（ADR-0006）

MVP-1 不自动推导 WACC（不做 CAPM、Beta、ERP 推导）。用户必须显式输入，作为估值假设保存在 `valuation_assumptions`：`value_numeric`、`currency`、`rate_type`（nominal / real）、`period_basis`（annual）、`source_type`（user_input）、`rationale`、`status`（unconfirmed / confirmed）、`confirmed_by`、`confirmed_at`。

1. 缺少已确认 WACC 时 Pre-flight 必须 BLOCK；
2. 不允许通过隐藏默认值绕过缺失输入；
3. WACC 的币种和名义/实际口径必须与现金流预测和终值增长率一致；
4. Terminal Growth Rate 必须小于 WACC；
5. MVP-2 Valuation Agent 可提出建议（`source_type = agent_suggestion`），未经用户确认不得作为已确认假设；
6. 允许按情景分别设定 WACC（`valuation_assumptions.scenario`）；只有一条 `scenario` 为空的 WACC 时适用全部情景。MVP-1 界面不提供 WACC 参考区间或预填值（ADR-0006）。

#### 18.1.2 SBC 处理政策（ADR-0007）

默认政策：**SBC 作为真实经济成本，不从 FCFF 中加回。**

- NOPAT 基于包含 SBC 费用的 EBIT；
- 若以 CFO 为起点推导现金流，必须识别现金流量表中已加回的 `sbc_expense` 并扣回，禁止重复加回；
- 禁止重复扣减：已将 SBC 作为经营成本计入现金流时，不得在没有明确模型依据的情况下，再对同一未来 SBC 造成的稀释施加等额折价；
- MVP-1 使用 12.6 定义的稀释股数作为每股估值基础；未来股权稀释预测暂不纳入。

#### 18.1.3 估值假设的创建顺序与 Run 入口（v1.4）

为消除"快照 → 假设 → 估值运行"的循环依赖，规定顺序如下：

1. **假设先于快照：** 假设通过 `POST /valuation-assumptions` 创建，或在 `POST /valuations` 请求中以内联 `assumptions` 提交（服务端先落库为 `valuation_assumptions` 再继续）。假设独立于任何 `valuation_run`，只绑定 `workspace_id + listing_id`。
2. **快照纳入假设：** 快照 manifest 以 `record_type = 'valuation_assumption'` 逐行引用假设 `id`；`valuation_runs.assumption_ids` 记录同一批引用。请求省略 `data_snapshot_id` 时，服务端按 `valuation_date` 生成含本次假设的新快照；显式传入快照时，其中必须已包含所用假设。
3. **不可原地修改：** 已被任何快照引用的假设不可修改；修改一律追加新版本行（`version + 1`，`supersedes_id` 指向旧版本）。仅 `unconfirmed → confirmed` 的确认动作允许在被引用前原地完成，并写 `audit_logs`。
4. **Research Run 入口：** `POST /research-runs` 通过 `valuation_assumption_ids` 引用已创建的假设（含 WACC、税率及 Bear/Base/Bull 情景假设）。Run 不得自行生成或默认这些假设：缺失已确认 WACC 返回 `WACC_MISSING` / `WACC_UNCONFIRMED`，缺失情景假设返回 `SCENARIO_ASSUMPTIONS_MISSING`（`BLOCK` → `insufficient_data`）。此时 Run 仍可 `succeeded`，估值章节按 18.0.3 第 2 条进入“不适用与未支持项”。

### 18.2 Reverse DCF

给定当前企业价值，反求在其他假设固定时需要达到的收入增长、利润率或现金流增长路径。输出“当前价格隐含的经营预期”，不能声称该预期必然实现。

MVP-1 纳入 Reverse DCF，范围限定为：在 WACC、终值增长率、利润率、再投资率固定的前提下，**单变量求解**显式预测期的年化收入增长率（确定性数值求根，需定义求解区间、收敛容差与无解时的 `BLOCK` 原因码 `REVERSE_DCF_NO_SOLUTION`）。必须共享 DCF 的 Pre-flight，并在结果中列出所有固定假设与限制。

### 18.3 相对估值

- PE（MVP-1）：支持 PE TTM（价格时点 + TTM `eps_diluted`）与 Latest FY PE（最新已公开完整财年的实际 `eps_diluted`），必须标注价格时点和 EPS 口径。Forward PE 与 PEG 不支持（ADR-0009），**不得使用 AI 估算的 Forward EPS 填补缺失的分析师预期数据**。
- EV/EBITDA（MVP-1）：说明 EBITDA 定义和调整项；EBITDA $\le 0$ 的 Pre-flight 拦截规则见 18.0.3 第 9 条（`NEGATIVE_OR_ZERO_EBITDA`）。
- PB / ROE（**EPIC 10**）：适用于银行、保险及部分金融企业时需行业专用口径；属于 0.3 节"MVP-1 明确不纳入"的行业专用模型，MVP-1 不实现。
- PS（**EPIC 10**）：适用于利润尚未成熟企业，但必须补充毛利率和现金消耗情况；MVP-1 不实现。

同业比较必须确保币种、会计期间、行业、盈利口径可比；无法标准化时必须标记不可比。

#### 18.3.1 相对估值的输出定义（v1.4）

- **前提：** 已确认的 Peer Set（`peer_set_id`）。Peer Set 及其成员的财务事实、价格按同一 PIT 规则取自同一 `data_snapshot`，Peer Set 本身以 `peer_set` 记录纳入快照。
- **成员剔除：** PE 剔除净利润 $\le 0$ 的成员，EV/EBITDA 剔除 EBITDA $\le 0$ 的成员（不得以 0 或负数入列），被剔除成员及原因在报告中列出。
- **样本不足：** 有效成员少于 3 个时 `BLOCK` → `insufficient_data`，原因码 `PEER_SET_INSUFFICIENT`。
- **倍数分布：** 取有效成员倍数的 P25 / P50 / P75，分别对应 Bear / Base / Bull。
- **隐含每股价值：** PE = 倍数 × 标的 `eps_diluted`（TTM 或 Latest FY，口径与所用倍数一致）；EV/EBITDA = 以“倍数 × 标的 EBITDA”得到企业价值，再按 18.1 的股权价值公式扣除净债务与其他债权，除以 12.6 的稀释股数。
- **结果落库：** 复用 `valuation_scenarios`（`scenario = bear/base/bull` 存 P25/P50/P75 结果），`assumptions_json` 记录倍数、入选成员数与 Peer Set 版本。
- **未提供 Peer Set：** `WARN` → `degraded`，原因码 `PEER_SET_NOT_CONFIRMED`，仅输出标的自身当前倍数，不输出隐含价值与同业分位。

**行业分类与 Peer Set（ADR-0008）：** MVP-1 使用 SEC SIC 作为初始行业分类，不依赖 GICS 授权数据。SIC 仅用于生成候选可比公司，**不等于**估值使用的最终 Peer Set。Peer Set 由用户确认，支持手动增删、保存、版本化并记录纳入理由（`peer_sets` 表），相对估值结果必须引用 Peer Set 版本。

### 18.4 情景和敏感性

所有完整估值至少保存 Bear/Base/Bull：
- 关键假设；
- 预测期；
- WACC；
- Terminal Growth；
- 税率；
- 收入增长；
- 利润率；
- Capex 和营运资本假设；
- 现金、债务和稀释股数；
- 估值结果和每股价值。

敏感性分析至少支持 WACC × Terminal Growth，以及增长率 × 利润率。
