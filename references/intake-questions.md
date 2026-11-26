# 需求澄清提问库（Intake Questions）

编译逻辑 MD 前，先用 `question` 工具问一轮。**一次最多 6 问**，分两批；不要一个问题一问。

规则：

1. 先扫源图和用户消息，已知的不要问。
2. 优先问“答案会改变步骤/落点/验收”的问题；纯偏好不问。
3. 用户不答时按推荐项落笔，并在 §9 写 `【推断】`。
4. 答案写进 `### 0.1 需求确认`，不是留在聊天里。
5. 与图冲突时以图为准，并在 §9 记 `【冲突】`。
6. 密钥只写“需要哪个环境变量”，不写值。

## 第一批：定位与范围（Q1–Q6）

```json
[
  {
    "header": "作业模式",
    "question": "这次是只把图编译成逻辑 MD，还是编译完直接照着施工？",
    "options": [
      { "label": "先编译再确认", "description": "（推荐）只交付 .logic.md，跑到 logic_check.py FAIL 0 就停下，等你确认再动代码" },
      { "label": "编译完直接施工", "description": "一次交付逻辑 MD + 代码 + 验收结果，中途不打断" },
      { "label": "只施工", "description": "已有 .logic.md，跳过编译，从 §8 第一个未勾选的 S 开始" }
    ]
  },
  {
    "header": "FLOW-TASK",
    "question": "任务类型定成哪个？它决定首行 FLOW-TASK，也决定 agent 是新建骨架还是先读现有代码。",
    "options": [
      { "label": "build-software", "description": "（推荐）从零做一个软件/工具，先搭骨架再按 S 补功能" },
      { "label": "extend-software", "description": "在现有仓库加功能，先读结构再找最小改动点" },
      { "label": "fix-software", "description": "修 bug，先复现、再改、再回归" },
      { "label": "build-automation", "description": "脚本/CI/发布/运维，重点幂等、失败回滚、密钥处理" }
    ]
  },
  {
    "header": "交付物",
    "question": "除了 .logic.md 本体，还要哪些交付物？",
    "multiple": true,
    "options": [
      { "label": "过 logic_check", "description": "（推荐）交付前跑 scripts/logic_check.py，FAIL 0 才算完" },
      { "label": "单独 flow.json", "description": "把附录 flow-json 另存一份，方便别的工具或 CI 消费" },
      { "label": "Mermaid 回环图", "description": "用 --mermaid 额外导出 .mmd，便于和源图肉眼比对" },
      { "label": "施工上手提示", "description": "附 5 行说明：从哪个 S 开始、先跑哪条命令、哪里最容易卡" }
    ]
  },
  {
    "header": "范围边界",
    "question": "图之外的东西做到什么程度？这一档决定 §0 的非目标和 §5 的分支数量。",
    "options": [
      { "label": "严格按图", "description": "（推荐）只实现图上节点；缺的配置、日志、异常出口只标【推断】写进 §9，不实现" },
      { "label": "补最小必需件", "description": "允许补“能跑起来”必需的配置、日志、异常出口，作为分支步骤写进 §5" },
      { "label": "补交互细节", "description": "允许按平台惯例补默认值、快捷键、空状态等图上没画的细节" },
      { "label": "含部署脚本", "description": "图里没有也要一并产出打包、部署或 CI 脚本" }
    ]
  },
  {
    "header": "平台与栈",
    "question": "运行平台和技术栈按哪个来？会原样写进 FLOW-TARGET 的 stack 字段。",
    "options": [
      { "label": "沿用我给的", "description": "（推荐）直接用消息里已写的语言、框架、版本，不再追问" },
      { "label": "Python 纯标准库", "description": "Python 3.11+，不装第三方包，写完直接能跑" },
      { "label": "Python + 第三方", "description": "允许 pip 安装（GUI、HTTP、DB 驱动等），编译时在 §0 列依赖清单" },
      { "label": "Node / TypeScript", "description": "Node 20+，npm 管理依赖" }
    ]
  },
  {
    "header": "数据与依赖",
    "question": "会碰哪些数据和外部依赖？涉及密钥的只说“需要”，不写具体值。",
    "multiple": true,
    "options": [
      { "label": "本地文件 / SQLite", "description": "（推荐）数据全在本机，不访问网络，无外部服务" },
      { "label": "外部 HTTP API", "description": "要调第三方接口；编译时在 §9 列 endpoint、鉴权方式和缺失的密钥" },
      { "label": "现有库 / 内网系统", "description": "要读已有库或内网服务，需要连接方式与只读/可写权限说明" },
      { "label": "第三方 CLI 工具", "description": "依赖 ffmpeg / git / pandoc 等外部命令，需在 §0 写版本要求和缺失时的降级" }
    ]
  }
]
```

## 第二批：约束与执行治理（Q7–Q12）

```json
[
  {
    "header": "UI 与交互",
    "question": "界面和交互按哪种处理？决定 §2 里 io 节点的落点，以及 §4 的文案能不能改。",
    "options": [
      { "label": "沿用图上文案", "description": "（推荐）控件、按钮文字、提示语照图一字不改，只补落点" },
      { "label": "允许调整布局", "description": "文案保留，布局和顺序可按平台惯例调整，改动清单写进 §9" },
      { "label": "无界面", "description": "纯 CLI 或后台服务，io 节点映射到 stdin/stdout、日志或 HTTP" },
      { "label": "只要最小原型", "description": "能点通主路径即可，样式和异常态放第二轮" }
    ]
  },
  {
    "header": "验收门槛",
    "question": "§7 的验收门槛用什么形式？契约要求每个 G 都有可执行的“命令”和“通过”判据。",
    "options": [
      { "label": "命令式自动验收", "description": "（推荐）测试脚本 + 退出码 + 固定输出（如 31/31），失败回到对应 S" },
      { "label": "端到端跑一遍", "description": "以完成一次真实任务为唯一门槛，附操作步骤和预期现象" },
      { "label": "允许人工检查", "description": "可以有肉眼项，但每项要写清看哪里、看到什么算通过" },
      { "label": "带量化指标", "description": "额外要求耗时、成功率、资源占用数字，阈值待补充" }
    ]
  },
  {
    "header": "非功能约束",
    "question": "有没有性能、安全、兼容上的硬约束？没有就选第一项，别写空话。",
    "multiple": true,
    "options": [
      { "label": "无特殊要求", "description": "（推荐）只写可验证的软约束，例如“不得阻塞主流程”，不编具体数字" },
      { "label": "性能上限", "description": "给出可测阈值（如单次响应 < 2s、1 万条 < 30s），数值待补充" },
      { "label": "安全与隐私", "description": "数据不出本机、密钥不落盘不进 MD、日志脱敏、删除要彻底" },
      { "label": "兼容范围", "description": "限定 OS 版本、Python 版本、分辨率或浏览器，超出即不支持" }
    ]
  },
  {
    "header": "部署与回滚",
    "question": "产物怎么上线，出问题怎么退？",
    "options": [
      { "label": "本地运行不部署", "description": "（推荐）单机双击或命令行跑，§7 不写部署门槛，§5 不写回滚分支" },
      { "label": "要部署步骤", "description": "需要安装、打包、发布命令，写成 G 门槛，失败即不算完成" },
      { "label": "要回滚方案", "description": "需要备份点、版本回退或开关，作为异常分支写进 §5" },
      { "label": "服务器 / 内网部署", "description": "需要环境清单、审批和灰度，编译时在 §9 列未确认项" }
    ]
  },
  {
    "header": "变更审批",
    "question": "施工时碰到图外的事，agent 可以自己做主到哪一步？会写进 FLOW-RULE。",
    "options": [
      { "label": "越界即停", "description": "（推荐）范围外一律先问，提问前不改任何文件" },
      { "label": "允许小修", "description": "同一文件内、不影响验收的修复可自行做，交付时列清单" },
      { "label": "允许换实现", "description": "可选替代库或写法，只要验收命令不变，需在交付时说明理由" },
      { "label": "允许改验收", "description": "验收命令本身可调整，但必须保持同等严格度并在 §9 注明" }
    ]
  },
  {
    "header": "优先级与工期",
    "question": "时间和优先级怎么排？决定要不要拆成“先跑通主路径”的两段交付。",
    "options": [
      { "label": "正确优先", "description": "（推荐）不设死线，验收不过不交付，慢一点没关系" },
      { "label": "有截止时间", "description": "到点交付已完成部分，未做的 S 保持未勾选并列进交付报告，日期待补充" },
      { "label": "先最小闭环", "description": "先让主路径端到端跑通，分支、异常、样式放第二轮" },
      { "label": "一次做完", "description": "中途不停，全部 S 和 G 过完再汇报" }
    ]
  }
]
```

## 问题 → 写入位置

| 问题 | header | 何时问 | 写入逻辑 MD |
| --- | --- | --- | --- |
| Q1 | 作业模式 | 消息没分清编译/执行 | 不写；决定是否产出文件 |
| Q2 | FLOW-TASK | 图看不出终态产物 | 首行 + §0.1 |
| Q3 | 交付物 | 要接 CI / 给别人看 | §0 + §7 |
| Q4 | 范围边界 | 图有 note 但没写边界 | §0.2 非目标 |
| Q5 | 平台与栈 | 图没有语言/框架线索 | FLOW-TARGET.stack + §0.1 |
| Q6 | 数据与依赖 | 有 database/io 节点但数据源不明 | §0.1 + §9 |
| Q7 | UI 与交互 | 有 UI 但没稿/文案要求 | §2 io 落点 + §4 |
| Q8 | 验收门槛 | 没有现成测试命令 | §7 G1..Gn |
| Q9 | 非功能约束 | 涉及网络/隐私/分发 | §1 + §7 + §9 |
| Q10 | 部署与回滚 | 要上服务器/给非技术用户 | §0 + §5 + §7 |
| Q11 | 变更审批 | 每次都问 | FLOW-RULE + §9.1 |
| Q12 | 优先级与工期 | 步骤多/用户赶时间 | §1 + §8 批次 |

## 设计确认（第二批之后，最多 4 问）

编译完逻辑 MD、动代码之前，用 `question` 再问一次：

1. “按 §2 的落点、§4/§5 的拆分、§7 的 G 施工，是否可以？”
2. “验收命令在当前环境能跑吗？缺哪个依赖？”
3. “有没有必须保留的现有行为/兼容性？”
4. “施工中范围外变更，找谁确认？”

把结果写进 §1：`设计确认: 用户 2026-11-26`。

## 变更控制（用户中途提新需求时问）

1. “这是澄清、范围变更、缺陷，还是技术栈变更？”
2. “影响哪些已完成的 S？是否接受回退这些 S？”
3. “是否需要重跑全部 G，还是只跑受影响的 G？”

分类规则：

- **澄清**：不改代码/不改 STATUS，只改 §0.1 或 §9。
- **范围变更**：新增 REQ + `### 9.1 变更台账`，重新过设计确认，只重跑受影响 S 与 G。
- **缺陷**：只回滚失败 S 及其后继，记 CHG 类型=缺陷。
- **技术栈变更**：冻结施工，改 `FLOW-TARGET.stack` 与 §2 落点，全部 S 回 `[ ]`，先跑最小基线。

受影响步骤算法：从命中的 S 出发，沿 flow-json 的 `steps[].next` 做 DFS 取后继闭包；只把闭包内已勾选的 S 改回 `[ ]`，其余保持。
