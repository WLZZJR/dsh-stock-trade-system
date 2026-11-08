# Global Equity Intelligence（GEI）

全球股票投资研究系统：数据可追溯、财务可复算、估值可校验，人工保留最终投资决策权。不下单、不自动交易、不承诺收益。

## 状态

**Phase 1 进行中（阶段 A：工程骨架）。** 工程基础设施已建立，尚无业务功能。规格已拆分为 [docs/](docs/README.md) 下的各文档；Phase 1 所需 ADR 已 `accepted`，其余 ADR 为 `proposed`。

## 交付档位

| 档位 | 内容 |
|---|---|
| MVP-1 | 美股确定性研究产品，零 LLM 依赖 |
| MVP-2 | Agent 与 MCP |
| MVP-3 | DeepSeek Harness 适配 |

详见 [docs/PRD.md](docs/PRD.md) 0.3 节与 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 快速开始

前置：[uv](https://docs.astral.sh/uv/)、GNU make、Docker（含 Compose）。建议把仓库放在 WSL Linux 文件系统中，不要放在 `/mnt/c`。

```bash
git clone git@github.com:WLZZJR/dsh-stock-trade-system.git && cd dsh-stock-trade-system
uv sync                      # 安装依赖（自动使用 Python 3.12）
make ci                      # lint + 类型检查 + 单元测试，应全部通过

cp .env.example .env         # 然后把 .env 里的 change-me 改成你自己的本地密码
                             # 注意：GEI_POSTGRES_PASSWORD 与 GEI_DATABASE_URL 中的密码须一致
make check-config            # 校验配置
make up                      # 启动 postgres、redis、api（首次需要拉取镜像）
make migrate                 # 建表（Alembic 迁移到最新版本）
make seed                    # 写入币种、国家、美国交易场所、内部来源（可重复执行）
make create-owner EMAIL=you@example.com   # 创建唯一的 Owner（提示输入密码；没有开放注册）
curl http://127.0.0.1:8000/health/live      # {"status":"ok"}
make test-integration        # 对真实 PostgreSQL 16 的集成测试（用临时数据库，不碰开发库）
make down                    # 停止服务（数据卷保留；如需清空数据，手动执行 docker compose 的 down -v）
```

所有命令的完整说明见 [AGENTS.md](AGENTS.md)“工程命令”。

## 给贡献者与 AI 编程智能体

先读 [AGENTS.md](AGENTS.md) 与 [docs/README.md](docs/README.md)。

## 分支与合并约定

仓库为 GitHub Free 账号下的 private 仓库，**平台不提供分支保护**，因此靠约定：

- AI 编程智能体只在**本地分支**上开发并提交（提交前本地跑 `make ci`），**不推送、不发 PR、不合并**。
- 推送到远程、发起 PR、合并到 `main` 均由项目负责人本人操作。
- CI（`.github/workflows/ci.yml`）只在“发起 PR”和“推送到 `main`”时运行；推送功能分支本身不会触发。需要合并前的 CI 检查时，由负责人发起 PR。
- 建议执行一次 `make install-hooks`，安装 pre-commit 与 pre-push 钩子：推送 `main` 会被拒绝，推送前自动运行 `make ci`。

钩子只约束安装它的本机，不是安全边界；多人协作或上生产前需重新评估（见 [PHASE-1-PLAN.md](docs/plans/PHASE-1-PLAN.md) D8）。
