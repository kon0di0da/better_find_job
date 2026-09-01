# Archive Policy（v0.2）

每个 Accepted/Superseded 版本在 `/archive/spec/<version>/` 生成只读归档；飞书文档保留历史 revision 链接。

| 归档项 | 位置 | 负责人 | 保留期 |
|---|---|---|---|
| Accepted Spec、历史版本、签署记录 | Lark history + `archive/spec/vX.Y/spec.pdf` | Document Owner | 项目生命周期+3年 |
| WP 状态、Git commit/tag | `archive/spec/vX.Y/delivery.yaml` | Backend Owner | 项目生命周期+3年 |
| OpenAPI/DDL/Event/Mock/fixture checksum | `archive/spec/vX.Y/checksums.sha256` | Backend Owner | 项目生命周期+3年 |
| Mock、fixture 与版本 manifest | `archive/spec/vX.Y/mocks` | Backend + QA | 项目生命周期+3年 |
| 测试、性能、安全报告 | `archive/spec/vX.Y/reports` | QA + Security | 项目生命周期+3年 |
| REQ×TC×WP×实现矩阵 | `archive/spec/vX.Y/traceability.yaml` | QA | 项目生命周期+3年 |
| 偏差、SCR、ADR、风险、回滚版本 | `archive/spec/vX.Y/governance` | Document Owner | 项目生命周期+3年 |

归档 manifest 必须列出每个文件的 SHA-256、字节数、生成时间和 Git commit。`make archive-check VERSION=vX.Y` 必须返回 0；缺文件、checksum 不一致、签署缺失或矩阵悬空时不得改为 Archived。该命令属于后续 WP，本 WP 不实现。
