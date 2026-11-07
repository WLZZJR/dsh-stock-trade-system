# DEPLOYMENT：运行服务与部署模式

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

> 备注：备份恢复 runbook、Windows / Linux 部署指南在 Phase 4（EPIC 9）补充到本文件。

## 8. 推荐运行服务

MVP Docker Compose 服务：

| 服务名 | 作用 | 必需性 |
|---|---|---|
| `web` | Next.js 前端 | 必需（MVP-1 起） |
| `api` | FastAPI REST API | 必需（MVP-1 起） |
| `worker` | 研究任务执行 | 必需（MVP-1 起） |
| `scheduler` | 周期更新与告警任务 | 必需（MVP-1 起） |
| `postgres` | PostgreSQL | 必需（MVP-1 起） |
| `redis` | 队列和缓存 | 必需（MVP-1 起） |
| `mcp` | MCP Server，部署模式可独立进程 | 必需（**仅 MVP-2 起**）；MVP-1 的 `docker-compose.dev.yml` 不得包含该服务，以符合 0.3 节"MVP-1 禁止依赖任何 LLM、MCP、Harness"的约束 |
| `minio` | 文件对象存储 | 可选，MVP 可用本地卷 |
| `caddy` / `traefik` | TLS 反向代理 | 远程服务器必需，本地可选 |

本地开发建议使用 `docker-compose.dev.yml`（MVP-1 阶段不含 `mcp` 服务），远程服务器使用 `docker-compose.prod.yml`。MVP-2 起新增 `docker-compose.mcp.yml` 或在既有 compose 文件中追加 `mcp` 服务，不得提前合并进 MVP-1 的默认启动集。生产环境禁止直接暴露 PostgreSQL、Redis、MinIO 管理端口到公网。

## 9. 部署模式

### 9.1 Windows 本地部署

- Windows 10/11 + WSL2 + Docker Desktop；
- 项目代码放在 WSL2 Linux 文件系统中，避免高频 I/O 全部落在 `/mnt/c`；
- `docker compose up -d` 启动核心服务；
- Web 默认仅绑定 localhost；
- 本地 MCP 可使用 stdio 子进程方式供本地 Agent 调用；
- `.env` 中的密钥不得进入 Git。

### 9.2 Linux 服务器部署

- Ubuntu LTS 或同类受支持 Linux；
- Docker Engine + Compose Plugin；
- Caddy/Traefik 负责 HTTPS；
- API、Web、Worker、Scheduler、MCP 放在私有 Docker 网络；
- 仅反向代理对外开放必要端口；
- 数据卷加密备份；
- 远程 MCP 使用 Streamable HTTP + 身份认证 + TLS；
- 设置 CPU、内存、磁盘、队列长度、API 配额和数据供应商速率限制。

### 9.3 配置文件

提供：
- `.env.example`：环境变量模板；
- `configs/default.yaml`：非敏感系统默认设置；
- `configs/providers.example.yaml`：供应商配置样例；
- `configs/research_profiles.yaml`：Balanced/Value/Growth Profile；
- `configs/markets.yaml`：市场和交易日历配置；
- `configs/risk_rules.yaml`：风险规则。

不要将 API Key、数据库密码、邮箱密码写入 YAML 或源代码仓库。
