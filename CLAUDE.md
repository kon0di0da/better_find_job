# Claude 执行约束

执行任何修改前先阅读 `AGENTS.md`、`specs/baseline.yaml` 和目标 `specs/work-packages/*.yaml`。

- 一次仅执行一个 `READY` WP。
- 先运行 `make spec-check`，基线或 checksum 不一致即停止。
- 严格遵守 WP `path_allowlist`，禁止越界实现后续业务。
- 遇到歧义填写 SCR，不自行补充行为。
- 验证失败即停止，不绕过门禁。
- 不复用或改写稳定 REQ/WP/TC/MOCK ID。
- 未经明确要求，不 push、不创建 MR。

当前范围仅为 `WP-FOUNDATION-007`：GitHub Actions、八项 required gate、PostgreSQL 15+ 迁移测试环境、出口扫描与 CI 专项测试；不调用远程 Codebase CI，不提交生成证据、测试数据库内容或凭证。
