# AGENT_INSTRUCTIONS：AI 编程智能体总指令与使用方式

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 37. AI Coding Agent 总指令

将本节作为 Codex、Claude Code 或 DeepSeek Harness Creator Mode 的项目级任务说明。建议先让 Agent 阅读整个规格书，再要求它按 Epic 分阶段实现，不能一次生成全部代码后不测试。

### 37.1 `AGENTS.md` 必含规则

**开工前：**
1. 先阅读 `README.md`、`docs/PRD.md`、`docs/ARCHITECTURE.md`、相关 ADR 和当前 Phase Plan；
2. 先 Brainstorming，再 Writing Plans，计划经人工评审后才开始编码；
3. 状态非 `accepted` 的 ADR 不得由 Agent 擅自作出不可逆决定；
4. 不得扩大 MVP 市场范围；不得自行增加未经许可审核的数据供应商；
5. 不得把 Agent、LLM、MCP 或 Harness 纳入 MVP-1 的运行依赖。

**实施中：**
1. 遵循 TDD：先写测试，再实现功能；
2. 财务计算、估值和 Pre-flight 必须是确定性代码；不得使用 LLM 生成、补齐或猜测财务事实；
3. 所有关键结果必须保存输入引用、公式/规则版本和数据快照；
4. 不得覆盖历史事实，修订数据采用版本追加；
5. 每项新增功能同步更新相应文档和验收测试；不得为了通过测试而删除或弱化验收规则；
6. 不得把真实 API Key、个人数据或供应商凭据写入代码库。

**每个 Phase 完成时提供：** 已完成任务清单；未完成任务和阻塞项；数据库迁移说明；自动化测试结果和覆盖范围；本地启动和验证命令；安全与许可影响；文档更新清单；与验收标准逐项对应的证据。**未经用户或项目负责人确认，不自动进入下一 Phase。**

### 37.2 总指令

```text
你是本项目的首席软件架构师、资深 Python/TypeScript 工程师和金融数据系统工程师。

项目名称：Global Equity Intelligence（GEI）
目标：实现一套全球股票投资研究系统，支持独立部署，并通过 REST API、MCP 和 DeepSeek Harness 适配层向智能体开放。
交付分三档：MVP-1 美股确定性研究产品（零 LLM 依赖）→ MVP-2 Agent 与 MCP → MVP-3 DeepSeek Harness。当前只实现当前档位。

必须遵守以下工程原则：
1. 本规格书是产品和架构的主要依据。遇到缺失决策时，先检查 docs/ADR；若仍缺失，提出最小化、可替换的实现，并记录 ADR，不得虚构第三方 API。
2. 核心研究逻辑、财务计算和估值模型必须与 Web、MCP、DeepSeek Harness 解耦。
3. 采用模块化单体；不要在 MVP 未经批准引入 Kubernetes、微服务集群或复杂消息中间件。
4. 任何第三方数据 API 都必须先核对官方文档、字段定义、市场覆盖、速率限制、许可和商业使用条件。没有 API Key 时提供 Mock Provider 和明确配置错误，不能伪造实时数据。
5. 所有 LLM 输出都必须经过 Pydantic Schema 校验。LLM 不得直接计算最终财务数值，不得访问任意数据库，不得执行任意 shell/Python 代码。
6. 财务指标和估值由确定性 Python 函数实现，并有单元测试、公式文档和版本号。估值引擎必须先执行 Pre-flight Check，严禁把缺失值当成 0 或对不适用行业强行计算。
7. 研究结论必须包含 evidence、assumptions、data_as_of、source、model_version、code_version；无法验证的结论标记为 unverified。
8. 所有财务数据必须保存所属期间与公开时间；PIT 查询不能使用研究时点之后公布的数据。财务概念入库必须经过 canonical_concepts 与 taxonomy_mappings 两层标准化，费用与 Capex 统一标准化为正数。
9. ticker 不能作为全局唯一键；必须使用 Issuer/Security/Listing/Identifier 模型，并启用 PostgreSQL btree_gist 排他约束与实体存在性触发器。
10. 数据金额使用 Decimal/Numeric；币种、单位、财报期间、调整口径必须明确。market_bars 必须关联非空 source_id。
11. 异步研究任务必须实现接口层幂等、阶段重试 Clean-before-Write 幂等，以及基于 heartbeat_at 的僵尸任务自动回收。对外只暴露 run_id；Run / Task 状态以第 22 节为准。
12. 不允许自动下单或交易；任何未来交易功能必须单独立项并添加人工授权闸门。
13. 不允许提交 API Key、密码、用户数据或付费数据样本到 Git。
14. DeepSeek Harness API 可能演进；必须锁定官方兼容版本，Harness 专属代码只能放在 integrations/deepseek_harness/。
15. MCP 使用官方 SDK 和当前稳定规范；本地默认 stdio，远程部署默认 Streamable HTTP。
16. 每完成一个 Epic，必须运行相关测试、修复错误、更新文档，并汇报：变更文件、实现内容、测试结果、未完成项、风险和下一 Epic。

执行顺序：
MVP-1
Phase 0：Brainstorming、规格冻结与 Writing Plans。拆分文档（第 36 节）、ADR-0001 至 0020 评审稿、行情供应商 PoC 与许可审查表、三档验收清单、Phase 1—4 Plans。退出条件：关键 ADR 均为 accepted；未决事项有负责人、影响范围和阻断策略；文档无互相矛盾的口径。不写业务代码。
Phase 1：基础工程、证券主数据与数据存储。Monorepo、依赖锁、CI、Docker Compose、PostgreSQL 迁移、Issuer/Security/Listing/Identifier、Provider、Raw Payload、Ingest Log、Data Snapshot、单用户登录、health/readiness。（EPIC 0、1）
Phase 2：Provider 接入、数据治理与 PIT。SEC EDGAR、OpenFIGI、单一行情 Provider、Mock Provider、限流重试与错误分类、两层概念映射、数据质量、公司行动与复权、PIT 查询；基础 Worker / Scheduler。（EPIC 2、5A 基础部分）
Phase 3：财务事实与指标引擎。FY / 季度 / TTM、股数口径、SBC 口径、单位与币种、修订处理、确定性风险指标。（EPIC 3）
Phase 4：估值、Pre-flight、REST 与 Web 完整闭环。DCF、Reverse DCF、PE、EV/EBITDA、Peer Set、敏感性、研究 Run 编排、快照与确定性报告、REST、Web、Windows / Linux 部署与备份恢复、MVP-1 验收。（EPIC 4、5A、6、7A、9）
MVP-2
Phase 5：Agent Schema、Orchestrator、fetch_filing_section、Agent 节点、Claim/Evidence、Risk Review。（EPIC 5B）
Phase 6：MCP Server、工具 Schema、API Key/OAuth、MCP Inspector 测试、MVP-2 验收。（EPIC 7B）
MVP-3
Phase 7：DeepSeek Harness MCP Bundle/适配层、版本兼容 smoke test、MVP-3 验收。（EPIC 8）

每个阶段只实现当前阶段范围。不要为了演示而写死股票数据、财务数字、估值结果或供应商响应。测试数据必须明确标记为 fixture/mock。

最终交付必须包括：可运行源码、数据库迁移、Docker Compose、自动化测试、API 文档、MCP 工具文档、Windows 部署指南、Linux 部署指南、备份恢复指南和 MVP 验收报告。
```

## 38. 建议给不同编程智能体的使用方式

### Codex

- 让 Codex 读取 `AGENTS.md` 与当前 Phase Plan（拆分前读取本规格书）；
- 要求 Codex 先做 Repo Plan、ADR、依赖和目录结构；
- 一次只交付一个 Epic；
- 每次提交前要求执行测试、lint、type check 和 migration 检查；
- 让 Codex 先完成确定性计算和数据模型，再做 Agent 编排。

### Claude Code

- 通过 `CLAUDE.md`（`@AGENTS.md`）加载共同规则，本规格书或拆分文档作为项目上下文；
- 先 Brainstorming 与 Writing Plans，再按 Phase Plan 以 TDD 实施；
- 把 Provider Adapter、Financial Engine、Valuation Engine 划分为独立子任务；
- 重点审查跨模块接口和测试覆盖；
- 禁止在未核实供应商官方文档时实现生产 Provider。

### DeepSeek Harness Creator Mode

- 先完成 GEI Core、REST API 和 MCP Server；
- 在 Harness 中只创建连接 GEI MCP Server 的 Bundle；
- Creator Mode 读取 `integrations/deepseek_harness/README.md` 和锁定版本的官方开发文档；
- 要求它只生成宿主适配层，不更改 `packages/` 中的核心研究逻辑；
- 通过真实 MCP 工具调用验证，不以“Bundle 安装成功”代替功能验收。
