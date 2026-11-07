# HARNESS_ADAPTER：DeepSeek Harness 适配（MVP-3）

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [README.md](README.md) 的章节映射定位到对应文件。

## 27. DeepSeek Harness 集成策略

### 27.1 采用薄适配层

推荐结构：

```text
integrations/deepseek_harness/
├── README.md
├── package.json
├── cordis.yml
├── src/
│   ├── index.ts
│   ├── config.ts
│   ├── mcp-connection.ts
│   ├── tools/
│   │   ├── research.ts
│   │   ├── valuation.ts
│   │   └── watchlist.ts
│   └── ui/                 # 后续加入 Harness 原生 UI
└── tests/
```

Harness 层职责：
- 安装/配置 MCP Server 连接；
- 提供少量符合 Harness 工具接口的便利工具；
- 将返回的 `run_id`、报告链接和错误转成 Harness 可呈现结果；
- 管理用户配置和连接状态；
- 不实现财务公式、不直接查询供应商 API、不保存研究数据库。

### 27.2 兼容性策略

DeepSeek Harness 的 Cordis 插件和开发 API 处于演进状态。实现时：
- 以官方仓库当前 README、工具开发文档和 MCP Client 文档为准；
- 固定 Harness commit/tag 与 `@deepseek-ai/*` 包版本；
- 在 CI 中对目标 Harness 版本运行插件加载和工具调用 smoke test；
- 将所有 Harness 专属代码限制在 `integrations/deepseek_harness/`；
- 禁止核心 `packages/` 导入 Cordis、Harness 或 `dsh-*` 包；
- API 改动时只替换适配层，不改研究服务。

### 27.3 Creator Mode 使用说明

交给 DeepSeek Harness Creator Mode 时，要求它先读取本项目 `integrations/deepseek_harness/README.md` 和锁定版本的官方文档，再生成/安装 MCP Bundle。不得让 Creator Mode 猜测未公开的 Bundle 字段或 Cordis API。

### 27.4 Harness 插件阶段验收

- Harness 能安装或启用 Bundle；
- 可以连接开发环境的 GEI MCP Server；
- 工具清单能正常发现；
- 能调用 `resolve_instrument`、`research_company`、`get_research_run` 和 `get_research_report`；
- 长任务不会阻塞 Harness 对话；
- MCP 断线时返回可理解错误，不泄露密钥；
- 禁用 Harness 插件不会影响 GEI Web/API/数据库。
