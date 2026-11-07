# TEST_STRATEGY：测试分层与金融计算必测案例

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 31. 测试分层

| 测试层 | 必测内容 |
|---|---|
| Unit | 财务指标、估值模型、Pre-flight Check 拦截与降级、币种/单位换算、风险计算 |
| Contract | Provider Adapter、REST Schema、MCP Tool Schema |
| Integration | PostgreSQL（含排他约束与触发器）、Redis、对象存储、任务 Worker（含幂等与僵尸任务回收） |
| PIT | 研究时点不得读入未来公开的数据；日期精度事实按下一交易日可用 |
| Snapshot | 快照哈希可复算；快照与 `financial_facts` 的 UPDATE/DELETE 被触发器拒绝；用快照复跑估值得到相同结果 |
| LLM Independence | 关闭所有 LLM 配置后，MVP-1 的全部 E2E 测试通过 |
| Regression | 固定输入与模型版本产生稳定数值结果 |
| Security | 越权访问、Prompt Injection、密钥泄露、工具权限 |
| E2E | 登录、Web 筛选、创建研究 Run、估值、报告查看 |
| Deployment | Windows Docker、Linux Docker Compose、备份恢复 |

## 32. 金融计算必测案例

- DCF：$\text{WACC} \le \text{terminal growth}$ 时 Pre-flight Check 拒绝计算并返回 `WACC_LTE_TERMINAL_GROWTH`；
- DCF：负 FCF、负净债务、少数股东权益缺失降级（`WARN` → `degraded`）、异常股数拦截（`BLOCK` → `insufficient_data`）；
- WACC：缺失或未确认时 `BLOCK`（`WACC_MISSING` / `WACC_UNCONFIRMED`）；不存在隐藏默认值；
- 有效税率：`income_before_tax <= 0` 且无用户确认税率时返回 `BLOCK` → `insufficient_data`（`EFFECTIVE_TAX_RATE_UNAVAILABLE`）；提供已确认 `tax_rate` 假设后降级为 `WARN` → `degraded`（`EFFECTIVE_TAX_RATE_REPLACED_BY_USER_INPUT`），不得静默回退为 0 或任意默认税率；
- SBC：以 EBIT 为起点不加回 SBC；以 CFO 为起点时扣回已加回的 SBC；两条路径对同一 fixture 结果一致；
- 行业适用性：银行/保险/REIT 请求 `dcf_fcff` 时返回 `BLOCK` → `not_applicable`（`SECTOR_INCOMPATIBLE_WITH_FCFF`）；
- PE：亏损企业返回 `BLOCK` → `not_applicable`（`NEGATIVE_EARNINGS`），不得输出有意义的正向 PE 排名；Forward PE 返回 `ESTIMATES_PROVIDER_NOT_CONFIGURED`；
- EV/EBITDA：`EBITDA <= 0` 时返回 `BLOCK` → `not_applicable`（`NEGATIVE_OR_ZERO_EBITDA`），不得输出负数或除零结果参与同业分位排名；
- Reverse DCF：已知解的 fixture 收敛到期望增长率；无解时返回 `REVERSE_DCF_NO_SOLUTION`；
- 股数：EPS 使用加权平均股数，每股价值使用 12.6 定义的稀释股数，二者不得互换；
- 财报：年度、季度、TTM 不得混淆；YTD 推导单季度正确；缺季度时 TTM 不可用；Capex 等支出项入库符号统一为正数；
- 复权：拆股前后价格与股数口径一致；
- 汇率：本币与报告币种转换使用正确日期的 FX；
- ADR：每份 ADR 对应普通股数量正确；
- PIT：财报发布日期之后的数据不能进入发布日期前的研究；
- 重述：财报修订需保存新旧版本；
- 退市：历史筛选池不能自动剔除当时已存在但后来退市的公司。
