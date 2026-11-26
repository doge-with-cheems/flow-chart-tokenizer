FLOW-TASK: build-software/uml-sequence
FLOW-TARGET: 下单接口时序 | source: uml-sequence.mmd | stack: Python 3.10+ / FastAPI / PostgreSQL | entry: S1 | end: S5
FLOW-RULE: 先完成需求确认再施工；顺序执行 S1→S5；每步验收通过后勾选 STATUS；消息顺序按 §11.2；范围外变更先问

# 下单接口时序 · 构建逻辑

> 来源: `uml-sequence.mmd`（UML 时序图）｜ 参与者: 3 ｜ 消息: 5 ｜ 生成: 2026-11-10

## 0. 任务卡

- **构建什么**: 下单接口 `POST /orders`：接收请求、写库、返回订单 ID。
- **成功标志**: 合法请求返回 201 与 `order_id`；支付失败返回 402。
- **运行环境**: Python 3.10+，FastAPI + PostgreSQL。

### 0.1 需求确认

| REQ | 需求 | 来源 | 优先级 | 验收标准 | 状态 | 确认 |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-01 | 提供 `POST /orders`，校验请求体 | Q2/Q8 + 图上 N1/N2 | P0 | 合法请求 201，缺字段 422 | 已确认 | 用户 2026-11-26 |
| REQ-02 | 订单与订单行事务写入数据库 | Q6 + 图上 N3 | P0 | 数据库能查回本次订单 | 已确认 | 用户 2026-11-26 |
| REQ-03 | 按支付结果返回 201 或 402，消息顺序正确 | Q8 + 图上消息 4/5 | P0 | 实测顺序 `POST→INSERT→order_id→402/201` | 已确认 | 用户 2026-11-26 |

### 0.2 非目标

- 不实现具体支付渠道，只返回 402。
- 不实现库存扣减与优惠计算。
- 不做管理后台和订单查询页。
- 不实现消息队列或异步任务。

### 0.3 追踪矩阵

| REQ | 步骤 | 落点 | 验收证据 | 门槛 | 状态 |
| --- | --- | --- | --- | --- | --- |
| REQ-01 | S1,S2 | `api/orders.py` | 201/422 各一次 | G1 | 待验收 |
| REQ-02 | S3 | `db/orders.py` | 查询订单与订单行 | G1 | 待验收 |
| REQ-03 | S4,S5 | `api/orders.py` | 402/201 与消息顺序 | G1,G2 | 待验收 |

## 1. 执行契约

- 按 S 编号施工；消息顺序必须与 §11.2 的序号一致。
- 每步完成后运行 `- 验收:`，通过才把 §8 的 `[ ]` 改成 `[x]`。
- `API` 不得直接拼 SQL；必须经仓储层访问 `DB`。
- 遇到时序与代码冲突，停止并写 §9。
- 范围外变更先登记 `### 9.1 变更台账`，只重跑受影响步骤。

### 1.1 Definition of Ready

- [x] 任务类型与交付物已确认。
- [x] §0.1 没有“待确认”需求。
- [x] 消息顺序与 §11.2 一致。
- [x] 范围外内容已写入 §0.2。
- [x] 验收命令在当前环境可执行。
- [x] 外部依赖与缺失密钥已写入 §9。

### 1.2 Definition of Done

- [ ] §8 所有应执行步骤为 `[x]`。
- [ ] §7 每个 G 有命令、结果和证据。
- [ ] §0.3 每条需求都有追踪行。
- [ ] §11.2 消息顺序与实测一致。
- [ ] `### 9.1 变更台账` 没有“待重跑”。
- [ ] 交付说明列明未实现范围。

## 2. 节点清单

| 节点ID | 功能头 | 原文标签 | 类型 | 入度 | 出度 | 软件落点 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| N1 | ACTOR | User | actor | 2 | 1 | 浏览器/客户端 | 外部参与者 |
| N2 | SERVICE | API | participant | 2 | 3 | `api/orders.py` | HTTP 入口 |
| N3 | DB | DB | database | 1 | 1 | `db/orders.py` | PostgreSQL |

## 3. 消息清单

| From | To | 消息 | 顺序 | 实现 |
| --- | --- | --- | --- | --- |
| N1 | N2 | POST /orders | 1 | `POST /orders` |
| N2 | N3 | INSERT order | 2 | `OrderRepository.insert()` |
| N3 | N2 | order_id | 3 | `RETURNING id` |
| N2 | N1 | 402 Payment Required | 4 | 支付失败分支 |
| N2 | N1 | 201 Created | 5 | 成功分支 |

## 4. 构建步骤

### S1 {API} · 定义下单端点
- 节点: N2 (participant)
- 目标: 暴露 `POST /orders`，校验请求体
- 落点: `api/orders.py`
- 动作: 定义请求模型 `CreateOrderRequest`；返回 `201` 或 `402`
- 输入: JSON body
- 产出: FastAPI 路由
- 验收: `curl -X POST /orders` 返回 201 或 402，不返回 500
- 下一步: S2

### S2 {MESSAGE} · 接收下单请求
- 节点: N1 (actor)
- 目标: 接收用户请求并转给 API
- 落点: `api/orders.py`
- 动作: 解析 `customer_id`、`items`；生成 `request_id`
- 输入: 客户端 JSON
- 产出: 领域命令 `CreateOrder`
- 验收: 合法请求进入 S3；缺字段返回 422
- 下一步: S3

### S3 {REPO} · 写入订单
- 节点: N3 (database)
- 目标: 在事务中写入 `orders` 与 `order_items`
- 落点: `db/orders.py`
- 动作: `INSERT ... RETURNING id`；失败回滚
- 输入: `CreateOrder`
- 产出: `order_id`
- 验收: 数据库能查到本次订单与订单行
- 下一步: S4

### S4 {MESSAGE} · 返回结果
- 节点: N2 (participant)
- 目标: 按支付结果返回 201 或 402
- 落点: `api/orders.py`
- 动作: 成功返回 `{"order_id": ...}`；支付失败返回 402
- 输入: `order_id`、支付结果
- 产出: HTTP 响应
- 验收: 两个分支各跑一次，状态码与消息顺序正确
- 下一步: S5

### S5 {END} · 完成
- 节点: N2 (participant)
- 目标: 下单接口可交付
- 落点: `api/orders.py`、`db/orders.py`
- 验收: `pytest tests/test_orders_api.py -q` 退出码 0
- 结果: 时序实现完成

## 5. 分支与异常

- 支付失败：S4 返回 402，不写订单（或回滚），对应消息 4。
- 参数缺失：S1 返回 422，不进入后续消息。

## 6. 循环与并行

无。消息按 1→5 串行。

## 7. 验收门槛

### G1 · 接口测试
- 命令: `pytest tests/test_orders_api.py -q`
- 通过: 退出码 0
- 失败: 回到 S1/S4 检查路由与状态码

### G2 · 消息顺序
- 命令: `python tools/check_trace.py`
- 通过: 实际调用顺序为 `POST → INSERT → order_id → 402/201`
- 失败: 回到 S2/S3 检查调用链

## 8. 执行状态

- [ ] S1 · 定义下单端点
- [ ] S2 · 接收下单请求
- [ ] S3 · 写入订单
- [ ] S4 · 返回结果
- [ ] S5 · 完成

## 9. 待确认

- 【推断】`DB` 按 PostgreSQL 实现；原图未写数据库类型。
- [`?`] 支付失败是否回滚订单不明确；示例按回滚实现。
- [`?`] `order_id` 的格式未给出；示例使用 UUID。

### 9.1 变更台账

| CHG | 日期 | 类型 | 描述 | 命中REQ/步骤 | 影响步骤 | 批准 | 状态 | 关闭证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CHG-01 | 2026-11-26 | 澄清 | 支付失败按回滚实现，不保留半成品订单 | REQ-03 | S3,S4 | 用户 | 已关闭 | §0.1 REQ-03 |
| CHG-02 | 2026-11-26 | 澄清 | order_id 使用 UUID | REQ-02 | — | 用户 | 已关闭 | §9 待确认 |

## 10. 回环图

```mermaid
sequenceDiagram
    actor User
    participant API
    database DB
    User->>API: POST /orders
    API->>DB: INSERT order
    DB-->>API: order_id
    API-->>User: 402 Payment Required
    API-->>User: 201 Created
```

## 11. 模型规格

### 11.1 模型元素

| 元素ID | UML类型 | 名称 | 代码落点 | 实现要点 | 验收 |
| --- | --- | --- | --- | --- | --- |
| N1 | actor | User | 客户端 | 发起下单请求 | 请求可达 |
| N2 | participant | API | `api/orders.py` | 校验、编排、返回状态码 | 201/402 |
| N3 | database | DB | `db/orders.py` | 事务写入订单与订单行 | 可查回 |

### 11.2 关系/消息

| From | To | 关系/消息 | 顺序/多重性 | 实现 |
| --- | --- | --- | --- | --- |
| N1 | N2 | POST /orders | 1 | 路由入口 |
| N2 | N3 | INSERT order | 2 | 仓储插入 |
| N3 | N2 | order_id | 3 | `RETURNING id` |
| N2 | N1 | 402 Payment Required | 4 | 支付失败 |
| N2 | N1 | 201 Created | 5 | 成功 |

## 附录：flow-json

```flow-json
{
  "name": "order-sequence",
  "task": "build-software/uml-sequence",
  "source": "uml-sequence.mmd",
  "diagram": "uml-sequence",
  "nodes": [
    { "id": "N1", "label": "User", "type": "actor", "uml_type": "actor", "directive": "ACTOR" },
    { "id": "N2", "label": "API", "type": "participant", "uml_type": "participant", "directive": "SERVICE" },
    { "id": "N3", "label": "DB", "type": "database", "uml_type": "database", "directive": "DB" }
  ],
  "edges": [
    { "from": "N1", "to": "N2", "label": "POST /orders", "kind": "message", "order": 1 },
    { "from": "N2", "to": "N3", "label": "INSERT order", "kind": "message", "order": 2 },
    { "from": "N3", "to": "N2", "label": "order_id", "kind": "message", "order": 3 },
    { "from": "N2", "to": "N1", "label": "402 Payment Required", "kind": "message", "order": 4 },
    { "from": "N2", "to": "N1", "label": "201 Created", "kind": "message", "order": 5 }
  ],
  "steps": [
    { "id": "S1", "node": "N2", "next": ["S2"] },
    { "id": "S2", "node": "N1", "next": ["S3"] },
    { "id": "S3", "node": "N3", "next": ["S4"] },
    { "id": "S4", "node": "N2", "next": ["S5"] },
    { "id": "S5", "node": "N2", "next": [] }
  ],
  "loops": [],
  "assumptions": ["【推断】DB 为 PostgreSQL"],
  "unresolved": ["[?] 支付失败是否回滚订单不明确"]
}
```
