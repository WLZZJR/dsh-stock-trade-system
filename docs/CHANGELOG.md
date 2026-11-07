# CHANGELOG：规格修订记录

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

> 拆分后的修订记录从 v1.5 之后继续追加在本文件顶部表格末尾。

## 修订记录

| 版本 | 日期 | 主要变更 |
|---|---|---|
| v1.0 | 2026-11-04 | 初始工程规格 |
| v1.0.1 | 2026-11-04 | 合入 5 项加固：两层财务概念映射、DDL 生产级约束、估值 Pre-flight、双层幂等、僵尸任务回收 |
| v1.1 | 2026-11-04 | 合入《修订建议书》：MVP 三档交付（MVP-1 美股确定性产品 / MVP-2 Agent+MCP / MVP-3 Harness）；MVP-1 零 LLM 依赖；Pre-flight PASS/WARN/BLOCK + 原因码；统一 Run/Task 状态机；对外只暴露 `run_id`；数据快照与 `ingest_log`；WACC、SBC、SIC/Peer Set、Forward PE 口径决策；受控 `fetch_filing_section`；标准概念扩至 38 项并区分加权/期末股数；ADR 统一编号 |
| v1.2 | 2026-11-04 | 一致性与完整性修订：修正 §0 小节编号顺序（0.1→0.2→0.3）；统一 REST/MCP 入口字段名为 `horizon_years`，`sections` 示例值与 MVP-1 允许清单对齐（`risk_metrics`）；18.3 节 PB/ROE、PS 标注为 EPIC 10（MVP-1 不实现）；`listings` 增补 GIST 排他约束防 ticker 有效期重叠；删除未落地的冗余 `financial_periods` 表定义（期间信息并入 `financial_facts`）；`research_tasks.task_type`、`valuation_runs.model_type` 补充 `CHECK` 约束；Pre-flight 新增 `EFFECTIVE_TAX_RATE_UNAVAILABLE` / `EFFECTIVE_TAX_RATE_REPLACED_BY_USER_INPUT` 原因码并补充必测案例；明确 `retry_wait` 期间心跳顺延规则，避免 Reaper 误判合法退避中的 Run |
| v1.3 | 2026-11-04 | 可行性评估后的矛盾修复：§8 Docker Compose 服务表修正 `mcp` 必需性为"仅 MVP-2 起"，消除与 0.3 节"MVP-1 禁止依赖 MCP"的直接冲突；18.0.3 新增第 9 条 `NEGATIVE_OR_ZERO_EBITDA` 原因码，补齐 EV/EBITDA 的 EBITDA$\le 0$ 边界判定（此前只有 PE 有对应的 `NEGATIVE_EARNINGS`）并补充必测案例；16 节基线 DDL 补齐 `workspaces`/`users`/`workspace_members` 三表定义，`data_snapshots.workspace_id`、`research_runs.workspace_id` 补上缺失的 `REFERENCES workspaces(id)` 外键，不再是裸 `UUID` |
| v1.4 | 2026-11-06 | 文档分析后的缺口与矛盾修复：①估值假设（`valuation_assumptions`）改为独立于 `valuation_run`、先于快照创建，消除"快照↔假设↔估值运行"循环依赖，新增 18.1.3 规定创建顺序；②`POST /research-runs` 新增 `valuation_assumption_ids`，明确 Run 的 WACC/情景假设入口；③`POST /valuations` 明确为同步 Pre-flight + 确定性计算（200 / 422），新增 `POST /valuation-assumptions`；④`market_bars` 改为只追加修订（`revision_no` + 只追加触发器 + 快照 `observed_at_cutoff`），保证快照可复现；⑤`raw_payloads` 新增 `retention`（`stored` / `hash_only`），化解许可未决与"可回放"验收的冲突；⑥12.6 定义 `ebit` 取数与回退规则；⑦新增 18.3.1 相对估值输出定义与 `PEER_SET_*` 原因码；⑧REST / MCP 的 `sections`、`models` 取值彻底统一；⑨`research_tasks` 补 `heartbeat_at`；⑩幂等拆分为显式 `idempotency_key` 与自动 `request_fingerprint`（仅非终态唯一）；⑪Pre-flight BLOCK 的 Task 粒度改为按模型；⑫Forward PE/PEG 不落库；⑬`tax_rate` 假设结构与 WACC 一致；⑭新增 16.2 补充 DDL（corporate_actions、financial_metrics、peer_sets、fx_rates、auth_sessions、audit_logs 等）；⑮新增 12.7 股票池灌库与 12.8 行情修订/原始数据留存；⑯`data_collection` 阶段超时例外；⑰新增 MVP-1 内部里程碑 M1-a / M1-b；⑱主导航标注档位 |
| v1.5 | 2026-11-06 | Agent 架构审计与实施规划补充：①新增 21.1 Agent 工具权限与写保护（read / propose / write 三级，污染上下文代码级降权，写工具需 `confirmation_token`）；②新增 21.2 记忆与跨 Run 复用规则（默认无长期记忆，历史 Claim 不得作为事实输入）；③新增 21.3 LLM 调用审计（`agent_invocations`，重试不删除）；④新增 21.4 Run 级 token 预算与适配器层强制中止；⑤新增 23.2 Claim / Evidence 语义校验（防虚构引用与非原文引文）；⑥新增 4.3.2 报告数值由确定性渲染器注入、LLM 文本数字扫描；⑦`confidence` 改为 low / medium / high 枚举；⑧新增 ADR-0018 至 ADR-0020；⑨新增第 41 节实施规划（Phase 0 去风险验证、依赖与并行、退出准则、非功能指标建议值、测试数据策略）；⑩开放问题补充 #10–#12；⑪MVP-2 验收与 EPIC 5B 补充对应条目 |
| v1.6 | 2026-11-06 | ADR 评审：ADR-0001、0003、0004、0006、0007、0010、0011、0012、0014、0015、0016、0017 按评审稿建议 `accepted`。同步修订：标准概念由 38 项扩为 40 项（新增 `preferred_stock`、`long_term_investments`），明确 `ebit` 为派生概念、`total_debt` 派生规则、`lease_liabilities` 仅含融资租赁、NWC 派生公式；VALUATION 新增股权桥接项口径、按情景 WACC、SIC 初始拦截清单 `sic_applicability_v1`；DATABASE 删除 `listings` 冗余 UNIQUE，新增主数据删除保护触发器；DATA_PIPELINE 新增盘前 / 盘中 / 盘后可用规则与交易日历来源；Reaper 阈值可配置；新增原因码注册表 REASON_CODES.md，并将 `DATA_REQUIRED_FIELD_MISSING` 合并为 `MISSING_REQUIRED_FIELD` |
| v1.7 | 2026-11-07 | Phase 1 阶段 B 实施反馈：①新增 `countries` 参考表（迁移 0008，承载计划要求的 ISO 3166 种子）；②`trg_verify_identifier_entity` 的 `CASE` 增加 `ELSE` 分支（BEFORE 触发器先于 CHECK 执行，未知类型原先会抛出 plpgsql 内部错误）；③新增 16.4 规范化哈希规则（D10）与 16.5 迁移、种子、迁移检查说明 |
