# tokeize-ngm

> 版本 1.1.0 ｜ 支持流程图 + UML

把 `.ngm` 流程图、Mermaid、PlantUML、draw.io 的**流程图和 UML 图**编译成 **agent 可执行的构建逻辑 MD** 的 OpenCode 技能。

项目本名按你的要求使用 `tokeize-ngm`；安装后技能目录名为 `ngm-flow-tokenizer`（OpenCode 用目录名作为技能 ID）。

## 它能做什么

```text
.ngm / Mermaid / PlantUML / draw.io / JSON
        │
        ▼
  流程图 / UML tokenize
        │
        ▼
  任务类型 + 功能头 + S1..Sn 施工步骤
        │
        ▼
  xxx.logic.md（UML 附 §11 模型规格）
        │
        ▼
  另一个 agent 照文档改代码、跑验收、勾选 STATUS
```

核心特性：

- **`.ngm` 直接解析**：识别 ZIP 容器、draw.io XML、JSON、DOT、Mermaid、PlantUML。
- **流程图 + UML**：类图、时序图、状态机、ER、用例、组件、部署、活动图。
- **悬空边还原**：draw.io 只画了 `source` + `targetPoint` 的边，按几何坐标还原目标节点，并标注 `【推断】`。
- **首 3 行任务头**：`FLOW-TASK` / `FLOW-TARGET` / `FLOW-RULE`，下游 agent 先读任务类型再动手。
- **功能头**：21 个基础指令 + 15 个 UML 指令（`{CLASS}`、`{MESSAGE}`、`{STATE}` 等），参与类型判定和语义校验。
- **图论 + 模型自检**：节点覆盖、死端、可达性、回边、STATUS、flow-json、UML 模型表覆盖。

## 目录

```text
tokeize-ngm/
├─ SKILL.md                       # OpenCode 技能入口
├─ README.md
├─ CHANGELOG.md
├─ VERSION
├─ install.ps1                    # 安装到本机 OpenCode 技能目录
├─ references/
│  ├─ logic-md-contract.md        # 逻辑 MD 契约：首 3 行、章节、字段、flow-json
│  ├─ directive-catalog.md        # 功能头目录与校验规则
│  ├─ uml-support.md              # UML 支持矩阵、限制、施工顺序
│  ├─ build-mapping.md            # 图元素 → 软件结构
│  ├─ example-logic.md            # 流程图完整示例
│  ├─ example-uml-class.md        # 类图完整示例
│  └─ example-uml-sequence.md     # 时序图完整示例
├─ scripts/
│  ├─ ngm_tokens.py               # 流程图 + UML tokenizer
│  ├─ logic_check.py              # 逻辑 MD / UML 校验器
│  └─ directives.py               # 功能头目录（两个脚本共用）
└─ examples/
   ├─ 自动作答流程.ngm             # 真实 .ngm 输入
   ├─ 自动作答流程.logic.md        # 编译产物，14 步 / 13 边
   ├─ uml-class.mmd                # Mermaid 类图
   ├─ uml-sequence.puml            # PlantUML 时序图
   ├─ uml-state.mmd                # Mermaid 状态机
   └─ uml-er.mmd                   # Mermaid ER 图
```

验证全部样例：

```powershell
python tests\test_examples.py
```

## 环境

- Python **3.9+**
- 只用标准库，不需要 `pip install`
- Windows 下把 `python` 换成 `py -3` 也可以

## 安装

```powershell
# 在项目根目录
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

默认装到：

```text
%USERPROFILE%\.config\opencode\skills\ngm-flow-tokenizer
```

装完重启 OpenCode，或在新会话里使用 `ngm-flow-tokenizer` 技能。

也可以手动把 `SKILL.md`、`references/`、`scripts/` 复制到上面的目录。

## 快速开始

```powershell
# 1. 解析 .ngm，看节点/边/功能头
python scripts\ngm_tokens.py "examples\自动作答流程.ngm"

# 2. 输出机器可读 flow-json
python scripts\ngm_tokens.py "examples\自动作答流程.ngm" --json --out flow.json

# 3. 按 references\logic-md-contract.md 生成 xxx.logic.md

# 4. 交付前校验，必须 FAIL 0
python scripts\logic_check.py "examples\自动作答流程.logic.md"
```

样例结果：

```text
nodes: 14  edges: 13
PASS 23  FAIL 0  WARN 0
```

UML：

```powershell
# 类图（Mermaid）
python scripts\ngm_tokens.py "uml-class.mmd"
python scripts\ngm_tokens.py "uml-class.mmd" --json --out flow.json

# 时序图（PlantUML）
python scripts\ngm_tokens.py "uml-sequence.puml"
python scripts\ngm_tokens.py "uml-sequence.puml" --mermaid

# 校验 UML 逻辑 MD（必须有 §11 模型规格）
python scripts\logic_check.py "references\example-uml-class.md"
python scripts\logic_check.py "references\example-uml-sequence.md"
```

UML 样例结果：

```text
uml-class      PASS 25  FAIL 0
uml-sequence   PASS 26  FAIL 0
```

## 逻辑 MD 首 3 行

```text
FLOW-TASK: build-software/desktop-python
FLOW-TARGET: 划词作答助手（自动作答流程） | source: 自动作答流程.ngm | stack: Python 3.10+ / tkinter / SQLite / OpenAI 兼容 API | entry: S1 | end: S10
FLOW-RULE: 顺序执行 S1→S14；每步验收通过后勾选 STATUS；判断按实测分支；无选区走 S11，非问题走 S13
```

`FLOW-TASK` 枚举：

| 值 | 用途 |
| --- | --- |
| `build-software` | 从零构建软件 |
| `extend-software` | 现有仓库加功能 |
| `fix-software` | 修 bug |
| `refactor-software` | 重构 |
| `build-automation` | 脚本 / CI / 发布 / 运维 |
| `build-data-pipeline` | 采集、转换、入库 |
| `build-doc` | 文档 / 报告 |
| `verify-only` | 只检查不写功能 |

## 功能头

写在步骤标题或节点标签里：

```markdown
### S4 {DB}{STORGE} · 储存数据
```

| 类别 | 指令 |
| --- | --- |
| 控制 | `{START}` `{END}` `{DQ}` `{OR}` `{LOOP}` `{LPAR}` |
| 数据 | `{DB}` `{STORGE}` `{DATA}` `{SUM}` `{LINEAR}` |
| IO/界面 | `{CARD}` `{PRINT}` `{INPUT}` `{CTIHD}` `{FILE}` `{MFL}` `{TRANSMUTE}` |
| 运行时 | `{PREPARE}` `{DELAY}` `{MSE}` |
| UML | `{CLASS}` `{IFACE}` `{ENUM}` `{ACTOR}` `{USECASE}` `{COMPONENT}` `{SERVICE}` `{STATE}` `{ENTITY}` `{MESSAGE}` `{RELATION}` `{TRANSITION}` `{TABLE}` `{API}` `{REPO}` |

`{STORAGE}` 是 `{STORGE}` 的别名。完整语义、组合规则和校验行为见 `references/directive-catalog.md`。

## 已知边界

- `.ngm` 的内部结构可能随工具版本变化。当前支持 ZIP + draw.io XML、JSON、DOT、Mermaid、PlantUML；无法解码时会提示导出 SVG/PNG/PDF。
- 图片和扫描件不做 OCR；看不清的标签会标 `[?]`。
- 悬空边只在 `targetPoint` 落在节点包围盒附近时还原，并写入 §9 待确认。
- UML 解析是语法子集，不是完整解释器；复杂嵌套、PlantUML 宏和部分交互图可能被忽略。
- 功能头是编译结论，不能用来凭空补出图上不存在的分支。

## 校验器检查项

- 首 3 行任务头、任务类型枚举
- 章节完整性与编号
- 步骤字段、判断分支、去向存在
- 死端、可达性、终止性
- 回边与循环退出条件
- STATUS 覆盖
- flow-json 与正文一致
- UML：§11 模型元素/关系覆盖、时序顺序、状态初终态、用例 actor、ER 字段
- 功能头组合与语义提示

退出码 `0` 表示无 FAIL；`1` 表示存在 FAIL。
