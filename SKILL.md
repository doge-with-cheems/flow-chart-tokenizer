---
name: NGM Flow Tokenizer
description: 把坚果云绘图 .ngm、Mermaid、PlantUML、draw.io 的流程图和 UML 图（类图、时序图、状态机、ER、用例、组件、部署、活动图）tokenize 成 agent 可直接执行的“构建逻辑 MD”：支持 `{START}`、`{DQ}`、`{DB}`、`{LOOP}`、`{CLASS}`、`{MESSAGE}` 等功能头，文件首 3 行声明任务类型，正文按 S1..Sn 给出落点、动作、产出、验收、去向，agent 照此从零构建软件并逐项勾选 STATUS。当用户说“把 ngm/流程图/UML 转成逻辑文档”“tokenize 流程图或 UML”“照着图建软件/写代码”“按图施工”时使用。
---

# NGM Flow Tokenizer：把流程图编译成可施工的逻辑 MD

## 0. 两种模式

| 用户意图 | 模式 | 产物 |
| --- | --- | --- |
| “把这张 ngm 转成 agent 能读的流程/逻辑文档” | **A 编译** | `<源文件名>.logic.md` |
| “照着这个流程把软件做出来” | **B 执行** | 代码 + 验收结果 + 更新后的 STATUS |

编译和执行必须分开：**先有逻辑 MD，再动代码**。不要一边看图一边猜着写。

核心链路：

```
.ngm → 节点/边清单 → 任务类型判定 → S1..Sn 构建步骤 → 验收门槛 → 逻辑 MD →（另一个 agent）逐步施工
```

## 1. 铁律

1. **首 3 行必须是任务头**，顺序和字段固定，不能有空行或标题挡在前面：

   ```text
   FLOW-TASK: build-software
   FLOW-TARGET: 划词作答助手 | source: 自动作答流程.ngm | stack: Python 3.10+ / tkinter / SQLite | entry: S1
   FLOW-RULE: 顺序执行 S1→S9；每步验收通过后勾选 STATUS；判断按实测分支；范围外变更先问
   ```

   - `FLOW-TASK` 是任务类型，决定 agent 的工作方式（见 §4）。
   - `FLOW-TARGET` 一句话说清构建什么、源文件、技术栈、入口步骤。
   - `FLOW-RULE` 是执行契约，必须包含“验收”和“STATUS”。

2. **不发明图上没有的动作**。需要补常识时标 `【推断】`，写进 §9 待确认。
3. **一个 process 节点 ≈ 一个可独立验收的落点**（文件/模块/命令）。同一节点有多个副作用时拆成子步骤，但保留同一个节点引用。
4. **每个步骤都必须有 `- 验收:`**，且验收要能实际执行（命令、文件存在、接口返回、界面现象）。
5. **判断步骤写在主流程里**，它指向的分支步骤放到 §5；每个判断至少 2 条出边。
6. **不改写**命令、参数、错误码、版本号、界面文案。
7. 解析不出、看不清的标签记 `[?]`，绝不猜。

### 1.1 功能头指令（`{TAG}`）

功能头是写在步骤标题或节点标签里的受控标记，用来补充图里没有明说的语义。完整目录见 `references/directive-catalog.md`。

```markdown
### S4 {DB}{STORGE} · 储存数据
```

- 常用：`{START}`、`{END}`、`{DQ}`（判断）、`{LOOP}`、`{LPAR}`、`{DB}`、`{STORGE}`、`{DATA}`、`{PRINT}`、`{INPUT}`、`{CTIHD}`、`{TRANSMUTE}`。
- 控制类必须与图一致：`{DQ}` 至少 2 个去向；`{OR}` 至少 2 条带标签分支；`{END}` 不能有下一步；`{LOOP}` 必须有回边和退出条件；`{LPAR}` 必须有 `- 最大次数:`。
- 功能头是**编译结论**，不是装饰。图上无法确认的，不要挂标签；写进 §9。
- 未知功能头会让 `logic_check.py` 直接 FAIL。

## 2. 模式 A：编译 `.ngm` → 逻辑 MD

### 2.1 先识别输入

| 输入 | 做法 |
| --- | --- |
| `.ngm` | 先跑 `ngm_tokens.py`；它按 JSON / XML / ZIP / 文本自动嗅探 |
| `.svg` / `.drawio` / `.xml` | 脚本可直接抽 `mxCell` / `<text>` |
| `.mmd` / `.mermaid` / `.dot` | 脚本可直接解析；Mermaid 支持 flowchart / class / sequence / state / ER |
| `.puml` / `.plantuml` | PlantUML 子集：class / sequence / state / usecase / component / deployment / activity |
| `.json`（React Flow 等） | 脚本走通用 `nodes`/`edges` 抽取 |
| `.png` / `.jpg` / 截图 | 用 `read` 看图；文字小就先裁剪放大 |
| `.pdf` | 用 `read` 逐页看 |

`.ngm` 是坚果云绘图的源文件，可能是 JSON、XML、ZIP 或私有二进制。**不要假设格式**，先跑脚本。

### 2.2 跑 tokenizer

```powershell
python scripts/ngm_tokens.py "自动作答流程.ngm"
python scripts/ngm_tokens.py "自动作答流程.ngm" --json --out flow.json
python scripts/ngm_tokens.py "自动作答流程.ngm" --mermaid

# UML
python scripts/ngm_tokens.py "uml-class.mmd"
python scripts/ngm_tokens.py "uml-sequence.puml" --json --out flow.json
python scripts/ngm_tokens.py "uml-state.mmd" --mermaid
```

Windows 下 `python` 不在 PATH 时用 `py -3`。脚本只用标准库，要求 Python 3.9+。

- 输出包含节点表（ID/功能头/标签/类型/入度/出度）和边表（From/To/条件/类型）。
- 标签里的 `{TAG}` 会被抽成功能头，并影响节点类型；未知大写 tag 会给出 warning。
- `--json` 的 `warnings` 必须读：出现“仅按字符串抽取”说明没恢复连线。
- 解析失败时，**不要硬编**。让用户用坚果云绘图「文件 → 导出为 → SVG（推荐）/ PNG 2x / PDF」，导出文件放到 `.ngm` 旁边再跑；或让用户把节点与连线清单贴过来。
- 图片/PDF 直接用 `read` 读，无法确认的标签标 `[?]`。

如果 `ngm_tokens.py` 输出的节点/边与图上明显不符，以**人工读图结果**为准，并在 §9 记录脚本误判。

### 2.3 建两张表（写正文前必须完成）

节点表：

| 节点ID | 原文标签 | 类型 | 入度 | 出度 | 软件落点 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |

边表：

| From | To | 条件/标签（原文） | 边类型 |
| --- | --- | --- | --- |

类型按形状和语义判断：`start` / `end` / `process` / `decision` / `io` / `subprocess` / `database` / `parallel` / `note`。

同标签 + 同连接 = 同一节点；跨页/跨泳道重复出现的记 `aliases`。

### 2.4 把图映射成软件结构

| 图中元素 | 软件落点 |
| --- | --- |
| start | 入口：`main()`、路由、事件处理器、CLI 命令 |
| process | 函数 / 模块 / 服务方法 / 脚本步骤 |
| decision | `if` / 状态迁移 / 守卫 / 参数校验 |
| io | UI、剪贴板、文件、HTTP API、消息队列边界 |
| database | schema / model / repository / 迁移 |
| subprocess | 独立模块、worker、子服务；主流程写“调用 SP1” |
| parallel | 线程/协程/队列 + fork/join 点 |
| loop | 重试、轮询、消费者循环；必须有退出条件 |
| end | 退出码、响应、持久化终态、通知 |
| note | 约束或注释，不单独成为步骤 |

更细的对应关系和常见架构模式见 `references/build-mapping.md`。

### 2.5 写逻辑 MD

按 `references/logic-md-contract.md` 的固定骨架写，必须包含：

```
首 3 行任务头
# 名称 · 构建逻辑
## 0. 任务卡
## 1. 执行契约
## 2. 节点清单
## 3. 边清单
## 4. 构建步骤        S1..Sn
## 5. 分支与异常
## 6. 循环与并行      L1..
## 7. 验收门槛        G1..
## 8. 执行状态        - [ ] S1 ...
## 9. 待确认
## 10. 回环图
## 附录：flow-json
```

步骤必须写成“施工指令”，不是“流程描述”。最小字段：

```markdown
### S3 {DB}{STORGE} · 建立本地存储
- 节点: N4 (database)
- 目标: 每次捕获都写入 SQLite，供历史页读取
- 落点: `snapanswer/store.py`（新建）
- 动作: 定义 `Store` 类和 `insert_capture()`；建 `captures` 表
- 输入: `Capture` 数据类
- 产出: `store.py`、`%APPDATA%/SnapAnswer/history.db`
- 验收: `python tools/selfcheck.py` 的 store 用例通过
- 失败: 写盘异常 → S12
- 下一步: S4
```

判断步骤：

```markdown
### S4 {DQ} · 判断：是否有选中文字
- 节点: N3 (decision)
- 目标: 决定弹面板还是放行原生右键菜单
- 落点: `snapanswer/selection.py`
- 判定: `probe_selection()` 返回非空文本
- 是 → S5
- 否 → S10
- 验收: 选中文本时返回 True；空白处返回 False
```

关键节点按 `references/directive-catalog.md` 挂功能头：判断用 `{DQ}`、存储用 `{DB}{STORGE}`、界面输出用 `{PRINT}`、结束用 `{END}`。没有把握的不要挂。

`## 8. 执行状态` 是**唯一**的进度源，每个步骤一行：

```markdown
- [ ] S1 · 环境与目录
- [ ] S2 · 数据模型
```

flow-json 放在文件末尾，供 `logic_check.py` 做图论校验（节点覆盖、死端、回边）。

### 2.6 自检后再交付

```powershell
python scripts/logic_check.py "自动作答流程.logic.md"
```

必须 `FAIL 0`。检查项包括：首 3 行、任务类型、章节、步骤字段、判断分支、去向存在、死端、可达性、终止性、回边、STATUS 覆盖、flow-json 与正文一致、功能头语义。

改完再跑；**数量不一致就先修，不要交付**。

### 2.7 UML 图（完整支持）

`ngm_tokens.py` 会自动识别并解析：

| 输入 | 识别关键字 | 输出 `diagram` |
| --- | --- | --- |
| Mermaid 类图 | `classDiagram` | `uml-class` |
| Mermaid 时序图 | `sequenceDiagram` | `uml-sequence` |
| Mermaid 状态机 | `stateDiagram-v2` | `uml-state` |
| Mermaid ER 图 | `erDiagram` | `uml-er` |
| PlantUML 类图 | `class` / `interface` / `enum` / `object` | `uml-class` |
| PlantUML 时序图 | `participant` / `->>` / `-->>` | `uml-sequence` |
| PlantUML 状态机 | `state` / `[*]` | `uml-state` |
| PlantUML 用例图 | `actor` / `usecase` | `uml-usecase` |
| PlantUML 组件图 | `component` / `package` | `uml-component` |
| PlantUML 部署图 | `node` / `artifact` / `cloud` | `uml-deployment` |
| PlantUML 活动图 | `start` / `:action;` / `stop` | `uml-activity` |
| draw.io / `.ngm` | UML 形状关键字 | 按形状推断 |

UML 图编译出的逻辑 MD **必须增加 `## 11. 模型规格`**：

```markdown
## 11. 模型规格

### 11.1 模型元素
| 元素ID | UML类型 | 名称 | 代码落点 | 实现要点 | 验收 |
| --- | --- | --- | --- | --- | --- |
| N1 | class | Order | `domain/order.py` | 属性 id/total；操作 submit | 可导入 |

### 11.2 关系/消息
| From | To | 关系/消息 | 顺序/多重性 | 实现 |
| --- | --- | --- | --- | --- |
| N1 | N2 | composition | 1..* | `Order.items` |
```

要求：

- 11.1 和 11.2 的 ID 必须与 flow-json 的 `nodes` / `edges` 一致。
- 时序图在 11.2 写 `顺序`（1..N）；状态机写 `事件/守卫/动作`；类图写 `多重性`。
- 每个 UML 元素都要有代码落点和验收；类图的关系要写实现方式。
- flow-json 必须带 `"diagram": "uml-*"` 和对应的 UML 字段（`attributes`、`operations`、`order`、`state_kind` 等）。
- 详细支持矩阵、限制和施工顺序见 `references/uml-support.md`。

类图样例：`references/example-uml-class.md`。
时序图样例：`references/example-uml-sequence.md`。

## 3. 模式 B：照逻辑 MD 构建软件

### 3.1 开工前

1. 读**首 3 行**，确认 `FLOW-TASK` 与用户这次的要求一致。不一致就停下来问，不要硬套。
2. 读 §0 任务卡和 §7 验收门槛，先知道“做成什么样算完”。
3. 读 §8 STATUS，找到第一个未勾选的步骤；已完成的不重做。
4. 确认工作目录、技术栈、依赖和权限；不满足就写进 §9 并问。

### 3.2 逐步施工协议

对每个步骤严格按顺序：

1. 读该步骤的 `目标 / 落点 / 动作 / 输入 / 产出 / 验收 / 失败 / 下一步`。
2. 只做这一步范围内的修改。不要顺手重构无关代码。
3. 跑 `- 验收:` 里的命令或检查。
4. 通过后，把 §8 的 `- [ ] S3` 改成 `- [x] S3`；失败则不勾选。
5. 记录一行执行日志（步骤、命令、结果、耗时/异常），再进入下一步。

分支步骤只在触发条件成立时执行；判断步骤必须**实测**条件，不能按“应该会走这边”来假设。

循环按 §6 的 `继续条件 / 退出条件 / 最大次数` 执行。达到最大次数仍失败 → 停止，写阻塞，问用户，不要无限重试。

### 3.3 收尾

按 §7 的每个 `G` 门槛跑一遍，全部通过才算完成。交付时报告：

- 完成了哪些 S，哪些 S 被分支跳过
- 每个 G 的命令与结果
- 改了哪些文件
- §9 里仍未确认/未解决的问题
- 未实现的范围（明确说“没做”）

### 3.4 阻塞处理

遇到以下情况立刻停，不要猜：

- 逻辑 MD 与实际代码/环境冲突
- 验收命令本身不可执行
- 需要新增图上没有的依赖或外部服务
- 判断条件无法观测

把现象、已尝试的命令、需要用户决定的问题写进 §9，并把当前步骤保持未勾选。

## 4. 任务类型（`FLOW-TASK`）

| 值 | 什么时候用 | agent 的重点 |
| --- | --- | --- |
| `build-software` | 从零做一个软件/工具 | 先搭骨架，再按 S 补功能 |
| `extend-software` | 在现有仓库加功能 | 先读现有结构，找最小改动点 |
| `fix-software` | 修 bug | 先复现，再改，再回归 |
| `refactor-software` | 重构 | 行为不变，验收先跑基线 |
| `build-automation` | 脚本 / CI / 发布 / 运维 | 幂等、失败回滚、密钥处理 |
| `build-data-pipeline` | 采集→转换→入库 | 数据契约、幂等、断点续跑 |
| `build-doc` | 报告/文档生产 | 结构、模板、事实来源 |
| `verify-only` | 只检查不写功能 | 输出证据，不改代码 |

判定顺序：先看图的**终态产物**，再看节点语义。拿不准时默认 `build-software`，并在 §9 写“任务类型为推断”。

## 5. 文件与参考

- `references/logic-md-contract.md`：首 3 行规范、章节骨架、字段定义、flow-json schema。
- `references/directive-catalog.md`：21 + UML 功能头 `{TAG}` 的语义、组合规则和校验行为。
- `references/uml-support.md`：UML 支持矩阵、元素映射、限制和施工顺序。
- `references/build-mapping.md`：流程图元素 → 软件结构、常见架构模式、拆分粒度。
- `references/example-logic.md`：流程图完整样例。
- `references/example-uml-class.md`：类图 → 领域模型完整样例。
- `references/example-uml-sequence.md`：时序图 → 接口实现完整样例。
- `scripts/ngm_tokens.py`：`.ngm` / Mermaid / PlantUML / draw.io / DOT / JSON / SVG tokenizer（流程图 + UML）。
- `scripts/logic_check.py`：逻辑 MD 校验器 + Mermaid 回环。
- `scripts/directives.py`：功能头目录（两个脚本共用）。

## 6. 编译交付清单

- [ ] 首 3 行是 `FLOW-TASK` / `FLOW-TARGET` / `FLOW-RULE`，且没有前置空行。
- [ ] 任务类型在 §4 的枚举内，并与图的实际产物一致。
- [ ] 每个节点至少出现在一个步骤里；每个步骤的 `节点` 都能在节点表找到。
- [ ] 每条边都被主路径、分支、循环或并行覆盖。
- [ ] 每个判断至少 2 个去向；每个非结束步骤都有下一步。
- [ ] 每个循环都有退出条件和最大次数。
- [ ] 每个步骤都有可执行的验收；§7 至少一个总验收 G。
- [ ] 关键节点挂了功能头：`{DQ}` 有 2 个去向，`{END}` 无下一步，`{LOOP}` 有回边和退出条件。
- [ ] §8 STATUS 覆盖全部步骤且每步只出现一次。
- [ ] flow-json 可解析，节点/边/步骤与正文一致。
- [ ] UML 图包含 §11 模型规格，11.1/11.2 覆盖全部元素与关系；时序图序号 1..N 连续。
- [ ] `logic_check.py` 输出 `FAIL 0`。
- [ ] §9 列出所有 `[?]`、`【推断】` 和脚本误判。
