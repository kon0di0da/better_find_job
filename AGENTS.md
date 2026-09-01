# Agent 执行规则

本仓库采用 Spec-Driven Development。所有 Agent 必须遵守：

1. 一次只执行一个状态为 `READY` 的 Work Package（WP），不得夹带后续 WP 的实现。
2. 开始前运行 `make spec-check`；失败时立即停止，不得以 warning 或 waiver 绕过。
3. 只修改当前 WP 的 `path_allowlist`。需新增路径或扩大范围时，先提交 Spec Change Request（SCR）并获批。
4. 以 `specs/baseline.yaml` 锁定的 Lark revision 与本地 canonical 文件 SHA-256 为基线；不一致时停止并提交 SCR。
5. 需求、API、DDL、事件、测试、Mock 或路径存在歧义时，不猜测业务行为；填写 `specs/governance/change-request-template.yaml`。
6. 禁止无规格扩展、顺手重构、新增未批准外部依赖或越界实现业务服务。
7. 仅在依赖全部完成、Gate-SPEC=PASS 且 WP 明确为 READY 时执行；验证命令非 0 时不得继续下一 WP。
8. 变更必须可追踪至稳定的 REQ/WP/TC/MOCK ID，并按 WP 的 rollback 执行回滚。

当前执行单元：`WP-FOUNDATION-003 数据库迁移框架`。本 WP 仅允许建立 PostgreSQL 迁移、测试与 `make migration-test`，不得实现仓储、业务 API、Mock adapter 或后续 WP。
