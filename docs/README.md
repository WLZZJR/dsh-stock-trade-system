# docs 索引

本目录由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来（Phase 0）。**拆分后各文件是对应内容的唯一权威来源**，原单文件已归档到 [archive/](archive/)，仅作历史参考。同一条财务口径只在一个文件中定义，其他文件只引用。

> 章节编号沿用原规格书，因此正文中的“见 18.1.2”“第 22 节”等引用仍然有效，请按下表找到所在文件。

## 阅读顺序（新成员 / AI 编程智能体）

1. [PRD.md](PRD.md)（含 0.3 三档交付）→ 2. [ARCHITECTURE.md](ARCHITECTURE.md) → 3. [adr/](adr/README.md) → 4. 当前 Phase 相关文档 → 5. [ROADMAP.md](ROADMAP.md)

## 章节映射

| 原章节 | 文件 | 说明 |
|---|---|---|
| 0、1、2、3、4、附录 B | [PRD.md](PRD.md) | 执行摘要、三档交付、产品需求、报告结构 |
| 5、6、7、35 | [ARCHITECTURE.md](ARCHITECTURE.md) | 架构原则、逻辑架构、技术栈、Monorepo 结构 |
| 8、9 | [DEPLOYMENT.md](DEPLOYMENT.md) | 运行服务、部署模式、配置文件 |
| 10、11、12.6 | [DATA_MODEL.md](DATA_MODEL.md) | 证券主数据、标准数据域、两层概念映射与股数口径 |
| 12.1–12.5、12.7、12.8 | [DATA_PIPELINE.md](DATA_PIPELINE.md) | 数据源、接入流程、数据质量、PIT、灌库、行情修订与留存 |
| 13、14、15、16 | [DATABASE.md](DATABASE.md) | 数据库约定、ER、表清单、DDL 基线 |
| 17 | [FINANCIAL_ENGINE.md](FINANCIAL_ENGINE.md) | 财务指标标准 |
| 18 | [VALUATION.md](VALUATION.md) | Pre-flight、DCF、Reverse DCF、相对估值、假设顺序 |
| 19、20 | [RISK_FRAMEWORK.md](RISK_FRAMEWORK.md) | 价值与成长框架、风险框架 |
| 21、22、23 | [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) | Agent 设计、Run/Task 状态机、证据链 |
| 24、25 | [API_CONTRACT.md](API_CONTRACT.md) | REST 契约（以 OpenAPI 自动生成为准） |
| 26 | [MCP_CONTRACT.md](MCP_CONTRACT.md) | MCP 工具契约 |
| 27 | [HARNESS_ADAPTER.md](HARNESS_ADAPTER.md) | DeepSeek Harness 适配 |
| 28、29、30 | [SECURITY_LICENSES.md](SECURITY_LICENSES.md) | 安全、数据授权、可靠性 |
| 31、32 | [TEST_STRATEGY.md](TEST_STRATEGY.md) | 测试分层、金融计算必测案例 |
| 33 | [acceptance/](acceptance/) | MVP-1 / MVP-2 / MVP-3 验收清单 |
| 34、41、附录 A | [ROADMAP.md](ROADMAP.md) | Epic、实施规划、发布定义 |
| 37、38 | [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md) | AI 编程智能体总指令（项目根 [AGENTS.md](../AGENTS.md) 为其精简规则） |
| 39.1 | [adr/](adr/README.md) | ADR-0001 至 ADR-0020 评审稿 |
| 39.2 | [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | 开放问题 |
| 40 | [RISKS.md](RISKS.md) | 工程风险 |
| 修订记录 | [CHANGELOG.md](CHANGELOG.md) | 规格修订记录 |
| 官方参考资料 | [REFERENCES.md](REFERENCES.md) | 外部参考 |
| （新增） | [REASON_CODES.md](REASON_CODES.md) | 原因码注册表，唯一事实来源（ADR-0017） |

## Phase 0 交付状态

| 项 | 状态 |
|---|---|
| 文档拆分、章节映射 | 已完成 |
| `AGENTS.md`、`CLAUDE.md`、`README.md` | 已完成 |
| ADR-0001 至 ADR-0020 | 12 个已 `accepted`（0001、0003、0004、0006、0007、0010、0011、0012、0014、0015、0016、0017）；其余 8 个为 `proposed` 骨架 |
| `MVP_1_ACCEPTANCE.md`（及 MVP-2 / MVP-3） | 已由原 33 节拆出 |
| [Phase 1 Plan](plans/PHASE-1-PLAN.md) | **已批准**（2026-11-06）；编码尚未开始 |
| Phase 2–4 Plans（`docs/plans/`） | **待编写**（依赖 Phase 1 评审结果与 Spike S1–S5） |
| 行情供应商 PoC 计划与许可审查表 | **待编写**（见 ROADMAP 41.2 的 S2） |
| Phase 0 Spike S1–S5 | **待执行**（见 ROADMAP 41.2） |
