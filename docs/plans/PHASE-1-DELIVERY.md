# PHASE-1-DELIVERY：Phase 1 交付说明（P1-30）

> **状态：草稿 — 自动化证据已全部填齐（2026-11-09 / 11-12）。** 余下两项负责人动作：§8 条件 5 干净环境复核、条件 7 Windows 留档；完成后本文件升级为最终交付说明。
> 日期：2026-11-09。对应计划：[PHASE-1-PLAN.md](PHASE-1-PLAN.md)；清单依据 [AGENTS.md](../../AGENTS.md)"每个 Phase 完成时提供"。

## 1. 已完成任务清单

| 阶段 | 任务 | 主要提交 |
|---|---|---|
| A 工程骨架 | P1-01 ~ P1-05、P1-07（目录、锁文件、lint/类型/测试、import-linter、Makefile、compose、README） | `005fa03`（仓库重建时并入初始提交） |
| A 工程骨架 | P1-06 CI（lint+类型+单测 / 集成测 PG16 / 迁移检查 / 漏洞扫描 / secret 扫描，只调 `make` 目标） | `165f14f` |
| B 数据库与主数据 | P1-10 ~ P1-19（迁移 0001–0008、种子、canonical_hash、迁移检查） | `0518256` → `7bbbb3b` |
| B 文档 | DATABASE 哈希规则（16.4）与迁移/种子/检查说明（16.5）（P1-31 的一部分） | `2416318` |
| C 服务与接口 | P1-20 ~ P1-26（problem+json 与 trace_id、消歧与 listing 详情、认证与限流与审计、workspace 隔离、health 探针、OpenAPI 快照） | `2de0e22` → `ae1f6b4` |
| D 收口 | P1-31 CHANGELOG v1.8 与文档一致性核对；P1-30 本文件；dev-env 捆绑 Redis 改可选（[docker-compose.dev.yml](../../deploy/compose/docker-compose.dev.yml) profiles + [.env.example](../../.env.example) 双模式说明） | 本次提交（哈希见 git log） |

## 2. 未完成任务与阻塞项

1. **S2 行情 Provider PoC 未完成**（[ROADMAP.md](../ROADMAP.md) 第 195 行，与 Phase 1 并行的工作项，**不是** Phase 1 退出条件）：[ADR-0005](../adr/ADR-0005.md) 仍为 `proposed`。**阻塞 Phase 2 的供应商决策**，不阻塞 Phase 1 收口。
2. **canonical_hash 的 Windows 本地验证未留档**：期望摘要是独立用 `sha256sum` 计算的平台无关常量（`tests/unit/test_canonical_hash.py`），任何平台跑通即验证；但 CI 矩阵只有 Linux，Windows 上的运行记录缺失（本机为 WSL2）。建议负责人在 Windows 下执行 `uv run pytest tests/unit/test_canonical_hash.py` 一次并留档。
3. **GitHub Actions 不在本地交付范围内**：按 [README.md](../../README.md)"分支与合并约定"，CI 仅在负责人推送或发 PR 时运行，智能体交付以本地命令输出为准（见 §4 与 §8）；负责人推送后可自行核对 Actions 结果，不属本文件待补项。
4. P1-30 / P1-31 本身即阶段 D 工作，随本文件与 CHANGELOG v1.8 完成。

## 3. 数据库迁移说明

- Alembic 手写 SQL（D6），8 个版本，`base → head` 一键建立；本阶段**无数据回填、无破坏性变更**，升级路径即首次建库。

| 版本 | 内容 | 任务 |
|---|---|---|
| 0001 | 扩展 `pgcrypto`、`btree_gist`；函数 `trg_forbid_mutation`；`currencies` | P1-10 |
| 0002 | `workspaces`、`users`、`workspace_members`、`auth_sessions`、`audit_logs`（只追加触发器） | P1-11 |
| 0003 | `issuers`、`securities`、`venues`、`listings`（GIST 排他约束防 ticker 有效期重叠） | P1-12 |
| 0004 | `providers`、`data_sources`、`provider_entitlements`、`provider_coverage` | P1-13 |
| 0005 | `identifiers`（排他约束 + 实体存在性触发器 + 主数据删除保护触发器） | P1-14 |
| 0006 | `raw_payloads`（含 `retention` CHECK）、`ingest_log` | P1-15 |
| 0007 | `data_snapshots`、`data_snapshot_items`（不可变触发器、部分唯一索引） | P1-16 |
| 0008 | `countries` 参考表（ISO 3166 种子） | P1-17（v1.7 记录） |

- 顺序约束：`trg_forbid_mutation` 先于 `audit_logs`、`data_snapshots` 等触发器创建；`listings.valid_from` 默认 `CURRENT_DATE`，**历史上市记录必须显式给出**（[PHASE-1-PLAN.md](PHASE-1-PLAN.md) §5 阶段 B 注意事项）。
- 规范化哈希规则（D10）见 [DATABASE.md](../DATABASE.md) 16.4；迁移、种子与迁移检查说明见 16.5。
- 验证命令：`make migrate`（升级到 head）、`make check-migrations`（逐版本 downgrade 还原 + 版本链 + 模式快照无漂移，需 PostgreSQL）。2026-11-09 本地运行：**8 passed**（`tests/unit/test_migration_files.py` 4 + `tests/integration/test_schema_drift.py` 4）。

## 4. 自动化测试结果与覆盖范围

- **结构**：`tests/unit`（20 文件）、`tests/integration`（22 文件，真实 PostgreSQL 16）、`tests/contract`（5 文件）、`tests/security`（2 文件）；合计 45 个测试文件、360 个测试函数（`grep -rh "def test_" tests/ | wc -l`，2026-11-09）。
- **分层**：见 [PHASE-1-PLAN.md](PHASE-1-PLAN.md) §7 —— Unit（哈希、消歧排序、密码令牌、配置）；Integration（约束与触发器、种子幂等、迁移往返、ready 探针、认证与越权）；Contract（错误结构、`/instruments/*`、`/health/*`、OpenAPI 快照）；Security（未登录 401、会话撤销、限流、令牌不落明文、日志脱敏、workspace 越权）。
- **覆盖率目标**：`packages/` ≥ 90%，整体 ≥ 80%；约束类验收按"每个约束至少一正例一反例"计。2026-11-09 本地运行：**294 passed / 176 deselected**（集成标记，需真实 PG），**总覆盖率 84%**（整体目标达标）。分层：`packages/domain` 100%、`packages/application` 86–100%（仅 config.py 86%）；`packages/data_engine` 的仓储/种子/来源模块（auth_repository 31%、instrument_repository 53%、seeding 41%、sources 29%）在单元运行中未覆盖——其行为依赖真实 PostgreSQL，由集成测试覆盖（2026-11-12 `make test-integration`：**176 passed / 0 skipped**）。
- **其他检查**（2026-11-09 本地，集成测试 11-12 复跑）：`make ci` 通过（lint + 类型检查 + 测试，测试环节输出如上）；`make test-integration`：**176 passed / 0 skipped**；`make check-migrations`：**8 passed**；`make audit`：**No known vulnerabilities found**；`make secret-scan`（gitleaks v8.30.1 全历史）：**21 commits scanned, no leaks found**。

## 5. 本地启动与验证命令

前置：安装 `uv`、`make`、Docker；从 `.env.example` 复制生成 `.env`（不入库）。

| 命令 | 作用 |
|---|---|
| `uv sync` | 按 `uv.lock` 安装依赖（Python 3.12） |
| `make up` / `make down` | 启动 / 停止 `postgres`（postgres:16）、`redis`（redis:8，由 `.env` 的 `COMPOSE_PROFILES=bundled` 控制，缺省启用）、`api`；镜像缺失时自动拉取 |
| `make migrate` | 把 `GEI_DATABASE_URL` 指向的库迁移到 head |
| `make seed` | 幂等写入参考数据（币种、国家、美国 MIC、`system_mock`、`manual_import`） |
| `make create-owner EMAIL=…` | 创建唯一 Owner（密码取 `GEI_OWNER_PASSWORD` 或交互输入；已有用户时拒绝） |
| `make ci` | lint + 类型检查 + 单元/契约/安全测试（提交前必跑） |
| `make test-integration` | 集成测试，需真实 PostgreSQL 16（先 `make up`） |
| `make check-migrations` | 迁移往返 + 模式快照无漂移（需 PostgreSQL） |
| `make audit` | pip-audit 依赖漏洞扫描 |
| `make secret-scan` | gitleaks 全历史密钥扫描 |
| `make openapi` | 重写 OpenAPI 契约快照（接口变更须同一提交更新） |

> 环境注记（2026-11-12）：捆绑 Redis 已改为可选——[docker-compose.dev.yml](../../deploy/compose/docker-compose.dev.yml) 的 `redis` 服务挂 `profiles: ["bundled"]`（[.env.example](../../.env.example) 缺省 `COMPOSE_PROFILES=bundled`，新环境仍三服务齐全）；`api` 对 redis 为软依赖（`required: false`），容器内 Redis 地址可经 `.env` 的 `GEI_REDIS_URL_API` 覆盖（缺省 `redis://redis:6379/0`），并经 `host.docker.internal:host-gateway` 可达宿主；宿主侧（pytest、脚本）用 `GEI_REDIS_URL`。本机即采用共享模式：复用宿主已有 `iam-redis` 实例（地址含密码，密码只存于 `.env`，不入库），集成测试 176 用例全过、`curl /health/ready` 三项 ok。

## 6. 安全与许可影响

- **认证与会话（D1–D3）**：禁止开放注册，唯一 Owner 经 `make create-owner` 创建；argon2id 密码哈希（参数过期自动升级）；会话令牌 32 字节随机数、库中仅存 SHA-256 摘要；HttpOnly + SameSite=Lax + 生产环境 Secure；登出 / 撤销 / 禁用即时失效；登录限流（按邮箱摘要计数、指数退避）；全部认证事件写审计，`details_json` 只含邮箱摘要。
- **不泄露内部信息**：统一 problem+json，500 固定通用文案；`/health/ready` 只报哪项依赖失败、不报原因；422 不回显提交值；请求日志单行 JSON、不记录请求头 / 查询串 / 请求体并全面脱敏（P1-20，`tests/security/test_log_redaction_http.py`）。
- **workspace 隔离**（P1-24）：归属只从会话取得，请求参数不能指定；他人资源与不存在资源同返 404。
- **密钥管理**：`.env` 不入库（`.gitignore`）；Phase 1 不需要任何供应商 API Key，CI 无 secrets。
- **许可**：PostgreSQL 16（`postgres:16` 镜像）；Redis 8 为 RSALv2 / SSPLv1 / AGPLv3 三许可，本项目自托管、不对外分发（D4 结论，必要时可平替 Valkey）；依赖集哈希固定于 `uv.lock` 并经 `make audit` 扫描（2026-11-09：无已知漏洞）；全历史密钥扫描（2026-11-09：gitleaks 21 commits，no leaks found）。
- **测试数据**：一律 fixture / mock，不含真实供应商数据、密钥或个人数据。

## 7. 文档更新清单

| 文件 | 更新内容 | 提交 |
|---|---|---|
| [API_CONTRACT.md](../API_CONTRACT.md) | 24.1.1 登录与会话；25 端点表补齐；25.1 消歧语义；健康探针语义（P1-25）；OpenAPI 快照规则（P1-26）；25.4 错误结构 | `2de0e22` → `ae1f6b4` |
| [DATABASE.md](../DATABASE.md) | 16.4 规范化哈希规则（D10）；16.5 迁移、种子、迁移检查说明 | `2416318` |
| [CHANGELOG.md](../CHANGELOG.md) | v1.7（阶段 B 实施反馈）；v1.8（阶段 C 实施反馈） | `2416318`；本次 |
| [README.md](../../README.md) | 快速开始、分支与合并约定 | 阶段 A 起 |
| [AGENTS.md](../../AGENTS.md) | 工程命令表 | 阶段 A（P1-07） |
| [PHASE-1-PLAN.md](PHASE-1-PLAN.md) | D1–D10 决定记录、D8 调研结论 | 评审期间 |
| ADR 目录 | ADR-0001/0003/0004/0006/0007/0010/0011/0012/0014/0015/0016/0017 → `accepted`（v1.6） | v1.6 |
| 本文件 | Phase 1 交付说明（P1-30） | 本次 |

## 8. 退出条件逐项证据（计划 §1）

| # | 退出条件 | 证据 | 状态 |
|---|---|---|---|
| 1 | 迁移可一键建立、可从任一版本回滚 | `tests/unit/test_migration_files.py`（逐迁移 downgrade）+ `tests/integration/test_schema_drift.py`（往返 + 快照无漂移）+ CI "migration check" 作业（P1-19） | **通过**（2026-11-09 `make check-migrations`：8 passed） |
| 2 | 排他约束、实体存在性触发器、只追加触发器、`retention` CHECK 测试通过 | `tests/integration/test_migration_0002.py`（审计只追加）、`0005.py`（标识符排他与存在性）、`0006.py`（retention）、`0007.py`（快照不可变） | **通过**（2026-11-09 `make test-integration`：0002 共 9、0005 共 12、0006 共 10、0007 共 8 用例全过） |
| 3 | ticker / 外部标识符的场所与有效期约束 | `test_same_ticker_different_venue_ok`、`test_same_venue_overlapping_ticker_rejected`、`test_ticker_reuse_after_delisting_ok`（0003）；`test_identifier_overlap_rejected` 等（0005） | **通过**（2026-11-09 `make test-integration`：0003 共 10、0005 共 12 用例全过） |
| 4 | 单用户登录 / 会话 / 登出可用；无登录不能访问业务接口；`/health/*` 可用 | `tests/integration/test_api_auth.py`、`tests/security/test_routes_require_session.py`（对 OpenAPI 每个操作强制 401）、`tests/integration/test_api_ready.py`、`tests/contract/test_health_*.py` | **通过**（2026-11-12：test_api_auth 26 用例全过；401 强制与 health 契约含于 `make ci` 294 passed；`/health/ready` 含 Redis 探针在集成运行中全过——176 passed / 0 skipped；另实测 `curl /health/ready` 三项 ok） |
| 5 | 新开发者按 README 在干净环境启动三服务并通过基础测试 | README 快速开始 + [deploy/compose/docker-compose.dev.yml](../../deploy/compose/docker-compose.dev.yml)；CI 集成作业用同一 `postgres:16` 镜像作 service container | 【待补：负责人本地复核记录】 |
| 6 | CI 绿色：lint、类型、单测与集成、迁移检查、漏洞扫描 | 本地 `make ci` / `make test-integration` / `make check-migrations` / `make audit` / `make secret-scan` 输出（[.github/workflows/ci.yml](../../.github/workflows/ci.yml) 与这些 make 目标等价，仅在负责人推送/发 PR 后运行） | **全部通过**（2026-11-09/12：`make ci` 294 passed / 176 deselected、覆盖 84%；`make test-integration` 176 passed / 0 skipped；`make check-migrations` 8 passed；`make audit` 与 `make secret-scan` 无发现） |
| 7 | canonical_hash 固定向量跨平台一致 | `tests/unit/test_canonical_hash.py`：期望值独立以 `sha256sum` 计算、平台无关；浮点输入被拒 | Linux 通过（2026-11-09 `make test`，294 passed 含该用例）；Windows 留档缺失（见 §2.2） |

## 9. 结论

阶段 A/B/C 全部任务与 P1-31 已完成。本地验证全部通过（2026-11-09/12）：`make ci`（294 passed / 176 deselected、覆盖率 84%）、`make test-integration`（176 passed / 0 skipped，含 Redis 就绪探针）、`make check-migrations`（8 passed）、`make audit`（无已知漏洞）、`make secret-scan`（无泄漏）、canonical_hash Linux 固定向量（27 passed），并实测 `curl /health/ready` 三项 ok。仍待负责人完成：条件 5 的干净环境复核、条件 7 的 Windows 留档。按 README"分支与合并约定"，GitHub Actions 结果是负责人推送后的确认步骤，不属本地交付证据。补齐 §8 各【待补】项后，本文件即为 Phase 1 最终交付说明。
