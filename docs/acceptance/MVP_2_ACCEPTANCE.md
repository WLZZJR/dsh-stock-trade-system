# MVP-2 验收清单

> 本文件由《全球股票投资研究系统：产品需求与工程实施规格书》v1.5 拆分而来，**自此成为该部分内容的权威来源**。章节编号沿用原规格书；正文中的“见 X.Y / 第 N 节”请通过 [../README.md](../README.md) 的章节映射定位到对应文件。

> 每档只验收本档范围。MVP-1 不得因 Agent、MCP 或 Harness 尚未完成而判定失败。

### 33.2 MVP-2 验收

- [ ] Orchestrator 可创建、查询、取消和恢复 Research Run。
- [ ] Agent 只能调用授权工具；`fetch_filing_section` 严格限制 Form / Item / CIK / Accession。
- [ ] Agent 结论具备 Claim / Evidence / Assumption 引用；不符合 Schema 的输出不能进入报告。
- [ ] Risk Agent 能识别关键反例、假设缺陷和风险遗漏。
- [ ] 不可信 filing 内容不会被当作 Agent 指令（Prompt Injection 测试）。
- [ ] 研究报告可追溯 Prompt 与模型版本（`model_snapshot`）。
- [ ] MCP 工具可被 MCP Inspector 或兼容客户端发现；Schema 稳定，错误语义清晰。
- [ ] LLM 失败不会破坏 MVP-1 的计算和数据服务。
- [ ] 引用不存在的 `evidence_id`、或引文不是来源原文子串的 Claim 被降级为 `unverified`，且不进入“已验证”章节（23.2）。
- [ ] LLM 段落出现未占位数字时被拒收；重试后仍违规则该段落省略并记录 `NARRATIVE_REJECTED`（4.3.2）。
- [ ] 污染上下文的 Agent 调用无法触发任何 `write` 工具（注入测试，21.1）；`write` 调用缺少有效 `confirmation_token` 被拒绝。
- [ ] 每次 LLM 调用均有 `agent_invocations` 记录，重试与反馈修正不会删除既有记录，报告可追溯到 invocation id（21.3）。
- [ ] `token_budget` 超限时 Run 以 `TOKEN_BUDGET_EXCEEDED` 终止且不再重试（21.4）。
- [ ] 历史 Claim 不会作为事实输入新 Run（构造含旧结论的历史 Run，断言新 Run 上下文中无其内容，21.2）。
