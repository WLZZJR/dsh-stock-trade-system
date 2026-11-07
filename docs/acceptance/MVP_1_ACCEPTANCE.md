# MVP-1 验收清单

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [../README.md](../README.md) 的章节映射定位到对应文件。

> 每档只验收本档范围。MVP-1 不得因 Agent、MCP 或 Harness 尚未完成而判定失败。

### 33.1 MVP-1 验收

**数据层**
- [ ] Issuer / Security / Listing 已拆分；ticker 不能单独作为证券主键。
- [ ] `identifiers` 表启用 `btree_gist` 有效期防重叠约束与实体存在性校验触发器。
- [ ] `market_bars` 强制 `source_id NOT NULL` 并通过 OHLC 约束测试；UPDATE / DELETE 被触发器拒绝，供应商修订以新 `revision_no` 追加，修订后旧快照仍能复算出相同结果。
- [ ] `canonical_concepts`（40 项核心概念）与 `taxonomy_mappings` 完成初始化。
- [ ] SEC EDGAR、OpenFIGI、一家行情 Provider 完成端到端接入；行情 Provider 许可审查已签署。
- [ ] 数据源许可和市场覆盖可查看。
- [ ] `raw_payloads` 去重与 `ingest_log` 拉取事件可追溯（来源 URL、发布时间、接收时间、失败与重试）；`retention = stored` 的响应可回放，`hash_only` 的响应可校验哈希。
- [ ] PIT 查询通过自动化测试；修订数据不覆盖历史认知。
- [ ] 研究使用的数据和参数可以通过 `data_snapshot` 恢复并校验哈希。

**研究与计算**
- [ ] 可筛选美股并返回缺失数据标识。
- [ ] 可创建研究 Run，具备接口幂等与阶段重试 Clean-before-Write 幂等。
- [ ] Run 支持状态查询、重试、取消以及心跳超时自动回收（Reaper Job）。
- [ ] FY、季度、TTM 和主要指标可由固定 fixture 复算；公式有文档和单元测试。
- [ ] SBC 不加回规则及 CFO 起点调整有测试。
- [ ] Pre-flight 返回 PASS / WARN / BLOCK + 原因码，并正确映射到四种估值状态。
- [ ] DCF、Reverse DCF、PE TTM、Latest FY PE、EV/EBITDA 通过已知数值用例。
- [ ] Bear/Base/Bull 情景和敏感性可输出。
- [ ] 确定性风险指标可输出。
- [ ] 报告可追溯数据快照、假设、规则版本和代码版本。

**产品与部署**
- [ ] 用户登录后可在 Web 完成筛选、查看财务、执行估值和读取报告。
- [ ] REST API 文档由 OpenAPI 自动生成；错误码明确、分页和权限正确。
- [ ] Windows 本地 Docker 和 Linux 远程部署（TLS、认证、备份）通过验收。
- [ ] 关闭所有模型 API 后，MVP-1 全部核心功能仍可用。
