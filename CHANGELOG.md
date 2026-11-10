# Changelog

## 1.1.0 — 2026-11-10

- 新增 UML 支持：类图、时序图、状态机、ER、用例、组件、部署、活动图。
- `ngm_tokens.py` 支持 Mermaid `classDiagram` / `sequenceDiagram` / `stateDiagram-v2` / `erDiagram`。
- `ngm_tokens.py` 支持 PlantUML 子集：class / sequence / state / usecase / component / deployment / activity。
- 新增 15 个 UML 功能头：`{CLASS}`、`{IFACE}`、`{ENUM}`、`{ACTOR}`、`{USECASE}`、`{COMPONENT}`、`{SERVICE}`、`{STATE}`、`{ENTITY}`、`{MESSAGE}`、`{RELATION}`、`{TRANSITION}`、`{TABLE}`、`{API}`、`{REPO}`。
- `logic_check.py` 新增 UML 校验：§11 模型元素/关系覆盖、时序消息顺序、状态初终态、用例 actor、ER 字段。
- 新增 `references/uml-support.md`、`example-uml-class.md`、`example-uml-sequence.md`。
- 修复：draw.io 边只画 `source` + `targetPoint` 时按坐标还原；Mermaid 标签里的 `{TAG}` 不再被误判为形状闭合。

## 1.0.0 — 2026-11-05

- 首个版本：`.ngm` / Mermaid / draw.io / DOT / JSON → 构建逻辑 MD。
- 首 3 行任务头、21 个基础功能头、图论校验、flow-json。
