# DATA_MODEL：证券主数据、标准数据域与财务概念标准化

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

> 本文件包含原第 12 节中的 12.6（两层概念映射与股数口径）；12.1–12.5、12.7–12.8 见 [DATA_PIPELINE.md](DATA_PIPELINE.md)。

## 10. 全球证券主数据模型

核心对象必须区分：

1. **Issuer（发行主体/公司）：** 法律或经济意义上的公司实体。
2. **Security（证券）：** 普通股、优先股、ADR、不同股份类别等证券本身。
3. **Listing（上市记录）：** 某一证券在某交易场所、以某 ticker 和交易币种交易的上市记录。
4. **Venue / Exchange（交易场所）：** 使用 MIC 或内部规范标识。
5. **Identifier（标识符）：** ISIN、FIGI、CUSIP、SEDOL、当地代码、供应商代码等。

`symbol` / ticker 不能作为全局主键。一个 ticker 可能在不同交易所重复；同一发行主体可能拥有多个证券和上市记录；ADR 与本地普通股也不能直接合并成一个 listing。

建议内部 ID 使用 UUID。外部标识符作为可变、可带有效期的映射记录保存。

## 11. 标准数据域

| 数据域 | 核心内容 | 点时要求 |
|---|---|---|
| Security Master | Issuer、Security、Listing、Venue、Identifier | 标识符和上市状态保留有效期 |
| Market Data | OHLCV、成交额、复权因子、报价 | 保留交易时间、供应商发布时间/观察时间 |
| Fundamentals | 利润表、资产负债表、现金流、财务指标 | 保留报告期间、公开时间、修订版本 |
| Corporate Actions | 分红、拆股、回购、增发、并购 | 保留公告日、登记日、除权日、生效日 |
| Estimates | 分析师预期、预测区间、目标价 | 供应商授权和时点记录 |
| Macro | GDP、CPI、利率、失业、汇率、流动性 | 使用实时版本/修订历史（可用时） |
| Industry | 行业分类、产业链、竞争者、市场份额 | 保留分类方案与版本 |
| News & Events | 新闻、公告、电话会、事件 | 保留发布时间、来源和原文链接 |
| Ownership | 机构持仓、内部人交易、股权结构 | 依市场披露制度和授权接入 |
| Research | 研究任务、证据、模型假设、报告、结论 | 记录任务数据快照和模型版本 |

### 12.6 跨市场财务概念标准化（Two-Tier Taxonomy Architecture）

美股（US-GAAP / SEC XBRL）、港股（IFRS / HKFRS）与 A 股（CAS）的原始财报科目名称、正负号约定及单位存在显著差异。系统严禁在 `financial_engine` 或 `valuation_engine` 中直接硬编码外部供应商字段名或 XBRL Tag，必须实施**两层映射机制**：

1. **第一层：内部标准财务概念字典（`canonical_concepts`）**
   计算与估值引擎仅识别内部标准枚举。MVP 首批锁定 **40 个核心标准概念**（v1.6 由 38 项扩充，ADR-0003）：
   - **利润表（16项）：** `revenue`, `cost_of_revenue`, `gross_profit`, `rd_expense`, `sga_expense`, `operating_income`, `ebit`, `interest_expense`, `income_before_tax`, `income_tax_expense`, `net_income`, `net_income_common`, `eps_basic`, `eps_diluted`, `sbc_expense`, `da_expense`
   - **资产负债表（17项）：** `cash_and_equivalents`, `short_term_investments`, `accounts_receivable`, `inventory`, `current_assets`, `total_assets`, `accounts_payable`, `current_liabilities`, `short_term_debt`, `long_term_debt`, `lease_liabilities`, `total_debt`, `total_liabilities`, `minority_interest`, `preferred_stock`, `long_term_investments`, `total_equity`
   - **现金流量表与股本（7项）：** `operating_cash_flow`, `capex`, `dividends_paid`, `share_repurchases`, `weighted_basic_shares`, `weighted_diluted_shares`, `shares_outstanding`

   **股数口径（禁止混用）：**
   - `weighted_basic_shares` / `weighted_diluted_shares`：报告期**加权平均**股数（duration），仅用于 EPS 与 EPS 复核；
   - `shares_outstanding`：**期末/最近披露时点**流通股数（instant，通常取自封面 `dei:EntityCommonStockSharesOutstanding`），用于市值、EV 与每股价值；
   - DCF 每股价值使用的“稀释股数”在 MVP-1 定义为：最近一期 `weighted_diluted_shares` 与最新 `shares_outstanding` 中**较大者**，并在 Pre-flight 中给出 `DILUTED_SHARES_PROXY` 警告；精确的库存股法稀释计算延后。
   - `income_before_tax` 用于计算有效税率：`effective_tax_rate = income_tax_expense / income_before_tax`（`income_before_tax <= 0` 时不可用）。
   - **`ebit` 取数规则（v1.4）：** SEC XBRL 通常没有 EBIT 标签。`ebit` 不直接映射任何外部标签，只由版本化派生规则产生：默认等于 `operating_income`（映射自 `us-gaap:OperatingIncomeLoss`）；该标签缺失时回退为 `income_before_tax + interest_expense`（`interest_expense` 已按绝对费用惯例为正数），回退结果记为 `system_derived` 并在 Pre-flight 记录警告 `EBIT_DERIVED_FROM_PRETAX`；两条路径都不可用才算 `ebit` 缺失。回退规则写入 `taxonomy_mappings` 的版本化规则，不得硬编码在引擎中。
   - **债务与租赁口径（v1.6，ADR-0003）：** `total_debt` 一律由 `short_term_debt + long_term_debt` 派生，仅当二者都缺失时才使用报告的总债务标签，且任何情况下不包含租赁负债。`lease_liabilities` 在 MVP-1 中只映射**融资租赁负债**：美国 GAAP 下经营租赁费用已计入 EBIT，若再把经营租赁负债计入净债务会重复扣减。
   - **营运资本（不新增概念）：** NWC =（`current_assets` − `cash_and_equivalents` − `short_term_investments`）−（`current_liabilities` − `short_term_debt`）。
2. **第二层：版本化映射规则表（`taxonomy_mappings`）**
   将外部 Tag（如 SEC 的 `us-gaap:Revenues`、`us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`）按**匹配优先级（`priority`）**、**符号乘数（`sign_multiplier`）**和**单位乘数（`unit_multiplier`）**映射至内部概念。
3. **符号统一铁律（Absolute Expense Convention）：**
   入库 `financial_facts` 时，所有费用与现金支出项（特别是 `capex`、`interest_expense`、`dividends_paid`）统一通过 `sign_multiplier` 标准化为**正数**，从而在计算引擎中严格固定公式（如 $\text{FCF} = \text{operating\_cash\_flow} - \text{capex}$），彻底消除不同数据源正负号相反导致的计算事故。
