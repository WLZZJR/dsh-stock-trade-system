# FINANCIAL_ENGINE：财务指标标准

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 17. 财务指标标准

MVP 应实现并测试以下指标：

### 17.0 财务期间与复算规则（ADR-0015）

- 区分 FY、季度、TTM、YTD 和其他期间类型（`financial_facts.period_type`）；
- TTM 必须由连续 4 个可验证季度构成；对只披露 YTD 的季度（如美股 10-Q 的现金流量表），用相邻 YTD 相减推导单季度，并记录推导来源；第四季度用 FY 减前三季度 YTD 推导；
- 缺季度、财年变更或期间不连续时，TTM 不可用，Pre-flight 返回 `TTM_PERIOD_INCOMPLETE`；
- 财年结束日与自然年不同时，以发行人财年为准，`fiscal_year` 标签不得按自然年重算；
- 重述、修订和后续更正以新版本追加，不覆盖历史已知事实；
- 单位换算、币种换算、股数和价格复权口径必须显式保存；
- 每个指标保存公式版本、输入事实引用（`source_fact_ids`）和计算时间。

### 17.1 增长

- Revenue Growth：同比、复合增长率；
- Gross Profit Growth；
- Operating Income Growth；
- Net Income Growth；
- EPS Growth（区分基本/稀释）；
- Free Cash Flow Growth；
- Segment Growth（数据可用时）。

### 17.2 盈利和资本回报

- Gross Margin；
- Operating Margin；
- Net Margin；
- FCF Margin；
- ROE；
- ROIC；
- ROA；
- Incremental ROIC（可选，后续完善）。

### 17.3 财务质量与偿债

- Net Debt / EBITDA；
- Debt / Equity；
- Interest Coverage；
- Current Ratio；
- Cash Conversion；
- Accrual Ratio（需定义口径）；
- SBC / Revenue；
- Share Dilution Rate；
- Capex / Revenue。

### 17.4 现金流

- CFO（`operating_cash_flow`）；
- Capex（`capex`，入库已按 Absolute Expense Convention 统一标准化为正数）；
- $\text{FCF} = \text{CFO} - \text{Capex}$；
- FCF per Share；
- FCF Yield；
- Cash Conversion Ratio。

每个指标必须拥有：定义、分母/分子、单位、期间规则、币种规则、来源字段、计算版本和边界情况测试。
