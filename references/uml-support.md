# UML 支持矩阵

`tokeize-ngm` 同时支持流程图和 UML。目标不是“画得像”，而是把 UML 模型编译成 agent 能施工的构建逻辑 MD。

## 1. 支持的图类型

| 图类型 | Mermaid | PlantUML | `.ngm` / draw.io | 输出 `diagram` |
| --- | --- | --- | --- | --- |
| 流程图 | `flowchart` / `graph` | 活动图基础语法 | draw.io 流程形状 | `flowchart` |
| 类图 | `classDiagram` | `class` / `interface` / `enum` / `object` | UML class 形状 | `uml-class` |
| 时序图 | `sequenceDiagram` | `participant` / 消息箭头 | UML lifeline / message | `uml-sequence` |
| 状态机 | `stateDiagram-v2` | `state` / `[*]` | UML state 形状 | `uml-state` |
| ER 图 | `erDiagram` | `entity` | 表/实体形状 | `uml-er` |
| 用例图 | 无原生语法（用 flowchart 近似） | `actor` / `usecase` | UML usecase 形状 | `uml-usecase` |
| 组件图 | 无原生语法（用 flowchart 近似） | `component` / `package` | UML component 形状 | `uml-component` |
| 部署图 | 无原生语法（用 flowchart 近似） | `node` / `artifact` / `cloud` | UML deployment 形状 | `uml-deployment` |
| 活动图 | 用 `flowchart` 表达 | `start` / `:action;` / `if` / `stop` | 活动图形状 | `uml-activity` |
| 对象图 | 无原生语法 | `object` | object 形状 | `uml-class` |
| 包图 | 无原生语法 | `package` | package 形状 | `uml-component` |

未覆盖：时序图的精确激活条、通信图、时间图、交互概览图。遇到这些图时，先降级成时序图或活动图，并在 §9 记录。

## 2. tokenizer 输出

```powershell
python scripts/ngm_tokens.py "uml-class.mmd"
python scripts/ngm_tokens.py "uml-sequence.puml" --json --out flow.json
python scripts/ngm_tokens.py "uml-state.mmd" --mermaid
```

输出会增加：

- `diagram: uml-class | uml-sequence | ...`
- 节点字段：`uml_type`、`attributes`、`operations`、`state_kind`、`stereotype`
- 边字段：`kind`、`order`、`message`、`message_kind`、`fragment`、`guard`、`action`、`left_multiplicity`、`right_multiplicity`
- `meta`：`messages`、`initial`、`final`、`entities`

## 3. UML → 软件结构

| UML 元素 | 代码落点 | 验收 |
| --- | --- | --- |
| class | 领域类/数据类 | 可导入、属性可构造 |
| interface | 协议/抽象基类 | 可被实现；方法签名一致 |
| enum | 枚举/常量 | 取值集合完整 |
| actor | 外部角色/客户端 | 能触发用例 |
| usecase | 应用服务/端点 | 主成功场景通过 |
| component | 模块/服务 | 可独立启动或导入 |
| node/artifact/cloud | 部署单元/运行环境 | 依赖可达 |
| state | 状态枚举/状态机 | 合法迁移通过 |
| transition | 事件处理器 | 非法迁移被拒 |
| message | API 调用/方法调用 | 发送者→接收者顺序正确 |
| entity | 领域实体/表 | 字段与主键正确 |
| ER relation | 外键/关联表 | 基数正确 |

## 4. 逻辑 MD 的额外要求

UML 图编译出的逻辑 MD 必须包含 `## 11. 模型规格`：

### 11.1 模型元素

```markdown
| 元素ID | UML类型 | 名称 | 代码落点 | 实现要点 | 验收 |
| --- | --- | --- | --- | --- | --- |
| N1 | class | Order | `domain/order.py` | 属性 id/total；操作 submit | 可导入 |
```

### 11.2 关系/消息

```markdown
| From | To | 关系/消息 | 顺序/多重性 | 实现 |
| --- | --- | --- | --- | --- |
| N1 | N2 | composition | 1..* | `Order.items` |
| N1 | N2 | POST /orders | 1 | `api/orders.py` |
```

校验器会检查：

- 每个 flow-json 节点都出现在 11.1 的第一列；
- 每条 flow-json 边都出现在 11.2 的 From/To 行；
- 时序图消息序号连续（1..N）；
- 状态图至少有一个初始状态和一个结束状态，非结束状态有出边；
- 用例图的每个 usecase 至少关联一个 actor（缺失给 WARN）；
- ER 实体没有字段给 WARN；
- 类图的继承/实现目标必须是 class/interface。

## 5. 各图类型的施工顺序

### 类图

1. 值对象/枚举 → 2. 实体 → 3. 接口/协议 → 4. 实现类 → 5. 关系（组合/聚合/继承/依赖）→ 6. 单元测试。

### 时序图

1. 参与者/外部边界 → 2. 入口端点 → 3. 每条消息对应的调用 → 4. 返回/错误分支 → 5. 顺序测试。

### 状态机

1. 状态枚举 → 2. 迁移表 → 3. 事件处理器 → 4. 守卫/动作 → 5. 非法迁移测试。

### 用例图

1. actor/外部接口 → 2. 用例主成功场景 → 3. include/extend → 4. 异常场景 → 5. 验收测试。

### 组件/部署图

1. 组件边界 → 2. 接口/依赖 → 3. 部署节点 → 4. 连接/协议 → 5. 启动与连通性测试。

### ER 图

1. 实体/字段 → 2. 主键/外键 → 3. 关系/基数 → 4. 迁移脚本 → 5. 查询验收。

## 6. 限制

- PlantUML 解析是**语法子集**，不是完整解释器。复杂嵌套、宏、预处理指令可能被忽略。
- Mermaid 的 `classDiagram` 泛型、注解、命名空间只做基础处理。
- 时序图的 `alt/else` 会转成 `fragment` 元数据；回环图可能输出多个独立 `alt` 块，而不是原始嵌套结构。
- 活动图的 `if/else/fork` 是基础映射，复杂嵌套需要人工在 §9 标注。
- draw.io/`.ngm` 的 UML 形状靠 `style` 关键字识别，未识别的形状会退化为普通节点。

## 7. 示例

- `references/example-uml-class.md`：类图 → 领域模型构建逻辑。
- `references/example-uml-sequence.md`：时序图 → 下单接口构建逻辑。
- `references/example-logic.md`：流程图 → 划词作答助手构建逻辑。
