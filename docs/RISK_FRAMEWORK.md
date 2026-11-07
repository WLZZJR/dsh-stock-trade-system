# RISK_FRAMEWORK：价值与成长研究框架及风险框架

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 19. 价值与成长综合研究框架

### 19.1 模块评分而不是黑箱总分

每个 Profile 输出 0—100 分的模块分数、评分依据、缺失字段和置信度。分数只作为研究辅助，不代表收益概率。

建议模块：

- Business Quality；
- Financial Quality；
- Growth Durability；
- Valuation Attractiveness；
- Balance Sheet Strength；
- Governance & Capital Allocation；
- Risk Level；
- Portfolio Fit（必须基于实际/模拟组合数据）。

### 19.2 默认 Balanced 研究维度

Balanced 默认将企业质量、成长可持续性、估值吸引力、财务稳健性和风险并列展示。首版不设跨行业统一“买入线”。权重可配置，但每次研究必须保存 Profile 版本。

### 19.3 必须识别的常见陷阱

- 低 PE 可能是周期高点盈利或结构性衰退；
- 高增长可能依赖股权稀释、并购或补贴；
- EPS 增长不一定意味着 FCF 增长；
- 现金流短期改善可能来自应付账款延长；
- ROE 可能由高杠杆推高；
- DCF 价值可能高度依赖终值；
- ADR 与本地股的股数、兑换比例和权利可能不同；
- 价格复权口径不一致会扭曲回报比较。

## 20. 风险框架

### 20.1 MVP-1 确定性风险指标

MVP-1 不包含 Risk Agent，只输出可由代码计算、可复算的单只证券风险指标，每项注明数据窗口、口径与数据日期：

- 价格风险：年化历史波动率（如 1 年 / 3 年日收益）、最大回撤，基于 `total_return` 或 `split_only` 口径并明确标注；
- 财务风险：Net Debt / EBITDA、Debt / Equity、Interest Coverage、Current Ratio（复用第 17 节定义）；
- 流动性风险：近 N 日平均成交额、零成交天数；
- 估值风险：DCF 终值占 EV 比例、敏感性矩阵的价值区间宽度；
- 数据风险：缺失字段数、未解决数据质量问题、`pit_precision` 降级记录。

Beta、相关性和组合层面风险需要基准与组合数据，延后至 EPIC 10。

### 20.2 完整风险框架（MVP-2 起）

至少分为：

1. Business Model Risk；
2. Competitive / Technology Risk；
3. Financial / Liquidity Risk；
4. Governance / Fraud Risk；
5. Regulatory / Geopolitical Risk；
6. Valuation / Expectations Risk；
7. Currency / Country Risk；
8. Market / Liquidity Risk；
9. Portfolio Concentration / Correlation Risk；
10. Data / Model Risk。

Risk Agent 必须对每条核心投资论点提出潜在反例，输出：风险描述、概率/严重度分级、证据、可监控信号、缓释办法、是否影响估值假设。
