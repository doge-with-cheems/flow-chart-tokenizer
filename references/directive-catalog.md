# 功能头指令目录（Directive Catalog）

功能头是写在节点标签或步骤标题里的 `{TAG}`，用**受控词汇**告诉 tokenizer 和下游 agent“这个节点是什么语义”。它不是装饰，会改变类型判定和校验规则。

倡议书原文的 21 个标记全部收录；拼写 `{STORGE}` 保留，同时接受 `{STORAGE}`。另外增加 15 个 UML 扩展标记（`{CLASS}`、`{MESSAGE}` 等），用于类图、时序图、状态机、用例图、组件/部署图和 ER 图。

## 1. 放置位置

三种写法等价，推荐第一种：

```markdown
### S4 {DB}{STORGE} · 储存数据
```

```markdown
### S4 · 储存数据
- 节点: N6 (database)
- 指令: {DB}{STORGE}
```

```markdown
| N6 | {DB}{STORGE} 储存数据 | database | ...
```

规则：

- 标签大小写不敏感，统一大写输出。
- 一个步骤可以有多个功能头，但控制类最多一个（`{LOOP}{LPAR}` 除外，`{START}{DQ}` 允许）。
- 功能头只影响**语义和校验**，不替代 `- 判定:`、`- 验收:`、`- 下一步:` 这些施工字段。
- 不要给每个节点都硬套功能头。只标“看图就能确定”的；不确定就不标，写进 §9。

## 2. 控制类

| 功能头 | 中文 | 节点类型 | 含义 | 硬性规则 |
| --- | --- | --- | --- | --- |
| `{START}` | 开始 | start | 流程入口/触发点 | 通常在 S1；不能与 `{END}` 同用 |
| `{END}` | 结束 | end | 流程终点 | 不能有下一步；必须有 `- 结果:` |
| `{DQ}` | 判断 | decision | 条件判断 | 必须有 `- 判定:`，至少 2 个去向 |
| `{OR}` | 或 | decision | 多选一分支 | 至少 2 个去向；每条分支建议带标签 |
| `{LOOP}` | 循环 | process | 循环体/回边入口 | flow-json 必须有回边；§6 必须有退出条件 |
| `{LPAR}` | 循环限制 | process | 循环上限/重试次数 | 必须有 `- 最大次数:`，或 §6 写明 |

允许组合：

- `{START}{DQ}`：入口本身就是分支判断。
- `{LOOP}{DQ}`：循环条件判断。
- `{LOOP}{LPAR}`：循环与上限写在同一节点。

禁止组合：

- `{START}{END}`
- `{END}` + 任何其他控制指令
- `{DQ}{OR}`（判断和或分支二选一）

## 3. 数据类

| 功能头 | 中文 | 节点类型 | 含义 | 校验提示 |
| --- | --- | --- | --- | --- |
| `{DB}` | 数据库 | database | 库、表、schema | 落点应说明库/表/schema |
| `{STORGE}` / `{STORAGE}` | 储存 | database | 持久化写入 | 验收应能查回数据 |
| `{DATA}` | 数据 | process | 数据契约、字段、转换 | 输入/产出应说明结构 |
| `{SUM}` | 求和 | process | 求和、计数、聚合 | 应说明聚合字段与口径 |
| `{LINEAR}` | 排序 | process | 排序、线性化 | 应说明排序键与方向 |

## 4. IO / 界面类

| 功能头 | 中文 | 节点类型 | 含义 | 校验提示 |
| --- | --- | --- | --- | --- |
| `{CARD}` | 卡片 | io | 界面卡片/展示单元 | 应说明展示内容 |
| `{PRINT}` | 显示 | io | 显示、渲染、打印、输出 | 验收应能看到结果 |
| `{INPUT}` | 手动输入 | io | 人输入内容 | 应说明谁输入什么 |
| `{CTIHD}` | 手动操作 | io | 点击/按键/拖拽/确认 | 应说明人工动作 |
| `{FILE}` | 文档 | io | 单文件读写 | 应有路径或格式 |
| `{MFL}` | 多文档 | io | 批量文件/目录 | 应说明批量范围 |
| `{TRANSMUTE}` | 传输 | io | 网络/队列/上传下载/跨进程 | 应说明源、目标、协议 |

## 5. 运行时类

| 功能头 | 中文 | 节点类型 | 含义 | 校验提示 |
| --- | --- | --- | --- | --- |
| `{PREPARE}` | 预备 | process | 初始化、安装、配置、建目录 | 应说明准备动作 |
| `{DELAY}` | 延迟 | process | 等待、超时、节流 | 应说明时长或超时值 |
| `{MSE}` | 测量 | process | 度量、断言、基准、阈值 | 应有数字阈值或可断言指标 |

## 5.5 UML 扩展

| 功能头 | 中文 | 节点类型 | 含义 | 校验提示 |
| --- | --- | --- | --- | --- |
| `{CLASS}` | 类 | class | UML 类 | 应说明属性/操作/职责 |
| `{IFACE}` | 接口 | interface | 协议/抽象接口 | 应说明方法契约 |
| `{ENUM}` | 枚举 | enum | 枚举/常量集合 | 应说明取值 |
| `{ACTOR}` | 参与者 | actor | 用例图外部角色 | 应说明外部角色 |
| `{USECASE}` | 用例 | usecase | 用例图功能单元 | 应说明场景与验收 |
| `{COMPONENT}` | 组件 | component | 组件/模块 | 应说明职责与依赖 |
| `{SERVICE}` | 服务 | component | 可部署服务 | 应说明部署与端口 |
| `{STATE}` | 状态 | state | 状态机状态 | 应说明事件与迁移 |
| `{ENTITY}` | 实体 | entity | ER/领域实体 | 应说明字段与主键 |
| `{MESSAGE}` | 消息 | process | 时序图消息 | 应说明发送者、接收者、顺序 |
| `{RELATION}` | 关系 | process | 类/ER 关系 | 应说明实现方式 |
| `{TRANSITION}` | 迁移 | process | 状态迁移 | 应说明事件/守卫/动作 |
| `{TABLE}` | 数据表 | database | ER 实体落库 | 应说明字段/主键/索引 |
| `{API}` | 接口端点 | io | 对外 API | 应说明请求/响应契约 |
| `{REPO}` | 仓储 | database | 数据访问层 | 应说明查询/保存接口 |

## 6. 类型优先级

一个节点有多个功能头时，按下面顺序决定图形类型：

```text
END > START > DQ > OR > LOOP > LPAR
    > CLASS > IFACE > ENUM > ACTOR > USECASE > COMPONENT > SERVICE > STATE > ENTITY
    > DB > STORGE > TABLE > REPO > PRINT > API
    > INPUT > CTIHD > FILE > MFL > TRANSMUTE
    > CARD > DATA > DELAY > MSE > SUM > LINEAR > PREPARE
    > MESSAGE > RELATION > TRANSITION
```

例子：

- `{START}{DQ}` → start；判断语义由步骤的 `- 判定:` 提供。
- `{DB}{STORGE}` → database。
- `{PRINT}{INPUT}` → io。

## 7. tokenizer 行为

`ngm_tokens.py` 会：

1. 从节点标签里抽出已知 `{TAG}`，从标签正文中移除。
2. 把 tag 写进节点：`directive`（主指令）和 `directives`（全部）。
3. 用 tag 覆盖形状推断的类型。
4. 未知的大写 tag（如 `{FOO}`）保留原文并给出 warning。
5. 在输出的节点表增加“功能头”列，`--json` 输出带 `directive` 字段，`--mermaid` 会把指令加回标签前缀。

例子：

```text
| 节点ID | 功能头 | 标签 | 类型 |
| N6 | DB | 储存数据 | database |
```

## 8. 校验器行为

`logic_check.py` 会：

- 拒绝未知功能头。
- 检查控制类指令的组合冲突和硬性规则。
- 检查 `{LOOP}` 是否真的有回边、`{LPAR}` 是否有最大次数。
- 对数据/IO/运行时类给出语义提示（WARN）：
  - `{DELAY}` 没有时长；
  - `{MSE}` 没有数字阈值；
  - `{TRANSMUTE}` 没说源/目标/协议；
  - `{FILE}` 没有路径/格式；
  - 等等。
- 没有任何功能头时给一条 WARN，建议对关键节点标注（不阻断交付）。

## 9. 最小示例

```markdown
### S1 {START}{DQ} · 收到请求
- 节点: N1 (start)
- 目标: 判断请求是否合法
- 落点: `api/handler.py`
- 判定: `request.is_valid()` 为真
- 是 → S2
- 否 → S5
- 验收: 合法/非法请求各跑一次

### S2 {DB}{STORGE} · 写入记录
- 节点: N2 (database)
- 目标: 把请求写入 `requests` 表
- 落点: `db/repository.py`
- 验收: `SELECT` 能查回本次请求
- 下一步: S3
```

```json
{
  "id": "N2",
  "label": "写入记录",
  "type": "database",
  "directive": "DB",
  "directives": ["DB", "STORGE"]
}
```

## 10. 使用建议

- **先读图，再挂标签**：标签是编译结论，不是装饰。图上没有的判断，不要靠标签补出来。
- **控制类必须与图一致**：`{DQ}` 必须有两条出边；`{LOOP}` 必须有回边。图不完整时先写进 §9，不要硬标。
- **数据/IO 类用于提示下游**：它们不会强行改变图，但会提醒 agent 写清落点、契约和验收。
- **一个节点一个主指令**：需要表达“存到数据库”时用 `{DB}{STORGE}`，不要硬造新词。
- **未知功能头会 FAIL**：需要扩展词汇时，先改 `scripts/directives.py` 和本文件，再使用。
