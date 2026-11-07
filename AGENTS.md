# AGENTS.md

本文件是所有 AI 编程智能体（Codex、Claude Code、DeepSeek Harness Creator Mode 等）在本仓库的共同规则。Claude Code 通过 `CLAUDE.md` 引用本文件。

## 项目

Global Equity Intelligence（GEI）：全球股票投资研究系统。分三档交付：MVP-1 美股确定性研究产品（**零 LLM 依赖**）→ MVP-2 Agent 与 MCP → MVP-3 DeepSeek Harness。**当前只实现当前档位，未经用户或项目负责人确认，不自动进入下一档或下一 Phase。**

**当前阶段：Phase 1 进行中（计划已批准 2026-11-06；项目负责人于 2026-11-07 指示开始编码）。阶段 A（工程骨架，P1-01 ~ P1-07）已完成；项目负责人于 2026-11-07 指示开始阶段 B，阶段 B（数据库与主数据，P1-10 ~ P1-19）已在本地分支实现；阶段 C（服务与接口，P1-20 起）须在阶段 B 评审后由项目负责人确认再开始。**

## 必读文档（开工前）

[README.md](README.md) → [docs/README.md](docs/README.md)（章节映射）→ [docs/PRD.md](docs/PRD.md) → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) → [docs/adr/](docs/adr/README.md) → 当前 Phase Plan（[docs/plans/PHASE-1-PLAN.md](docs/plans/PHASE-1-PLAN.md)）。完整总指令见 [docs/AGENT_INSTRUCTIONS.md](docs/AGENT_INSTRUCTIONS.md)。

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

## 补充规则（v1.5，Agent 阶段适用）

- Agent 节点只获得 `read` 与 `propose` 工具；`write` 类工具须 `confirmation_token`（见 [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md) 21.1）；
- 每次 LLM 调用必须登记 `agent_invocations`，不得存在未登记的二次 LLM 调用（21.3）；
- 报告中的数值由确定性渲染器注入，LLM 文本不得自写数字（[docs/PRD.md](docs/PRD.md) 4.3.2）。

## 其他

- 权威来源是 `docs/` 下各拆分文件；`docs/archive/` 中的原单文件仅作历史参考，不得据其实现。
- 分支与合并：智能体只在本地功能分支上开发并提交，**不得推送、发起 PR 或合并**；推送远程与合并到 `main` 均由项目负责人手动操作（见 [README.md](README.md)“分支与合并约定”）。

## 工程命令

均在仓库根目录执行；依赖 `uv`、`make`、Docker。CI 只调用这些 `make` 目标。

| 命令 | 作用 |
|---|---|
| `uv sync` | 安装依赖（Python 3.12，按 `uv.lock`） |
| `make ci` | lint + 类型检查 + 单元/契约/安全测试（不含集成测试），提交前必跑 |
| `make lint` | ruff 检查与格式检查 + import-linter 分层契约 |
| `make format` | 自动格式化并修复可自动修复的 lint 问题 |
| `make typecheck` | mypy（`packages` 严格，`apps` 标准） |
| `make test` | pytest（排除 `integration` 标记）并输出覆盖率 |
| `make test-integration` | 集成测试，需要真实 PostgreSQL 16（先 `make up`，并配置 `GEI_DATABASE_URL`） |
| `make audit` | 依赖漏洞扫描（pip-audit，基于锁文件） |
| `make secret-scan` | 密钥扫描（gitleaks，Docker 镜像，扫描 git 历史） |
| `make check-config` | 校验配置，缺少必需环境变量时报错并退出 |
| `make up` / `make down` | 启动 / 停止开发环境（postgres、redis、api），需要 `.env` |
| `make migrate` | 把 `GEI_DATABASE_URL` 指向的数据库迁移到最新版本（Alembic，手写 SQL） |
| `make seed` | 应用参考数据种子（币种、国家、美国交易场所、内部来源），可重复执行 |
| `make check-migrations` | 迁移检查：逐版本 downgrade 还原、版本链、模式快照无漂移（需要 PostgreSQL） |
| `make install-hooks` | 安装 pre-commit / pre-push 钩子（可选，需本人执行） |

约定：测试数据一律为 fixture / mock；`.env` 不入库；新依赖的主版本变更须先跑全部测试。
