#!/usr/bin/env python3
"""Validate an agent-executable logic MD produced by ngm-flow-tokenizer.

Usage:
  python logic_check.py <logic.md>
  python logic_check.py <logic.md> --json
  python logic_check.py <logic.md> --mermaid

Checks:
  - first three lines are FLOW-TASK / FLOW-TARGET / FLOW-RULE
  - task type is in the known enum
  - required sections exist and are numbered
  - every step has node/goal/landing/verify/next (or branch fields)
  - decisions have at least two outgoing branches
  - every edge/step target exists; no dead ends except end nodes
  - all nodes are covered by steps; all nodes are reachable and can reach an end
  - every back edge has a loop with an exit condition
  - STATUS checklist covers every step exactly once
  - flow-json parses and agrees with the document

Standard library only (3.9+).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from directives import DIRECTIVES, scan_tags

TASK_TYPES = {
    "build-software": "从零构建软件/工具",
    "extend-software": "在现有代码库增加功能",
    "fix-software": "定位并修复缺陷",
    "refactor-software": "重构现有实现",
    "build-automation": "脚本 / CI / 发布 / 运维自动化",
    "build-data-pipeline": "数据采集、转换、入库管道",
    "build-doc": "文档 / 报告 / 内容生产流程",
    "verify-only": "只做检查与验收，不写功能",
}

REQUIRED_SECTIONS = {
    0: ("任务卡",),
    1: ("执行契约", "使用契约"),
    2: ("节点清单",),
    3: ("边清单",),
    4: ("构建步骤",),
    5: ("分支与异常",),
    6: ("循环与并行",),
    7: ("验收门槛",),
    8: ("执行状态",),
    9: ("待确认",),
    10: ("回环图", "Mermaid"),
}

STEP_FIELDS = ("节点", "目标", "落点", "验收")
PLAIN_REQUIRED = STEP_FIELDS + ("下一步",)
DECISION_REQUIRED = STEP_FIELDS + ("判定",)
BRANCH_REQUIRED = ("节点", "目标", "落点", "验收", "触发")

STEP_RE = re.compile(r"^###\s+(S\d+)\s*(.*?)\s*$")
LOOP_RE = re.compile(r"^###\s+(L\d+)\s*(.*?)\s*$")
GATE_RE = re.compile(r"^###\s+(G\d+)\s*(.*?)\s*$")
FIELD_RE = re.compile(r"^-\s*([^:：]{1,12})\s*[:：]\s*(.*)$")
NODE_FIELD_RE = re.compile(r"^(N[0-9A-Za-z_-]+)\s*(?:\(([^)]+)\))?")
ARROW_RE = re.compile(r"(?:→|->|=>)\s*(S\d+)")
ANY_STEP_RE = re.compile(r"\bS\d+\b")


class Report:
    def __init__(self) -> None:
        self.pass_count = 0
        self.fail_count = 0
        self.warn_count = 0
        self.items: list[tuple[str, str, int, str]] = []

    def ok(self, name: str, detail: str = "", line: int = 0) -> None:
        self.pass_count += 1
        self.items.append(("PASS", name, line, detail))

    def fail(self, name: str, detail: str, line: int = 0) -> None:
        self.fail_count += 1
        self.items.append(("FAIL", name, line, detail))

    def warn(self, name: str, detail: str, line: int = 0) -> None:
        self.warn_count += 1
        self.items.append(("WARN", name, line, detail))

    def render(self) -> None:
        for status, name, line, detail in self.items:
            loc = f" (line {line})" if line else ""
            tail = f": {detail}" if detail else ""
            print(f"[{status}] {name}{loc}{tail}")
        print()
        print(f"PASS {self.pass_count}  FAIL {self.fail_count}  WARN {self.warn_count}")
        if self.fail_count:
            print("结果: 未通过。先修 FAIL 再交付/执行。")
        elif self.warn_count:
            print("结果: 通过（有警告，执行时注意）。")
        else:
            print("结果: 通过。")


def field_map(block: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block:
        match = FIELD_RE.match(line.strip())
        if match:
            key = match.group(1).strip()
            if key not in fields:
                fields[key] = match.group(2).strip()
    return fields


def section_ranges(lines: list[str]) -> dict[int, tuple[int, int, str]]:
    headers: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        match = re.match(r"^##\s+(\d+)\.?\s*(.*)$", line)
        if match:
            headers.append((int(match.group(1)), i, match.group(2).strip()))
    out: dict[int, tuple[int, int, str]] = {}
    for idx, (num, start, title) in enumerate(headers):
        end = headers[idx + 1][1] if idx + 1 < len(headers) else len(lines)
        out[num] = (start, end, title)
    return out


def blocks_in(lines: list[str], start: int, end: int, pattern: re.Pattern[str]) -> list[tuple[str, str, int, list[str]]]:
    found: list[tuple[int, str, str]] = []
    for i in range(start, end):
        match = pattern.match(lines[i])
        if match:
            found.append((i, match.group(1), match.group(2)))
    out: list[tuple[str, str, int, list[str]]] = []
    for idx, (line_no, sid, title) in enumerate(found):
        block_end = found[idx + 1][0] if idx + 1 < len(found) else end
        out.append((sid, title, line_no + 1, lines[line_no + 1:block_end]))
    return out


def parse_steps(lines: list[str], sections: dict[int, tuple[int, int, str]]) -> dict[str, dict[str, Any]]:
    steps: dict[str, dict[str, Any]] = {}
    for sec in (4, 5):
        if sec not in sections:
            continue
        start, end, _ = sections[sec]
        for sid, title, line_no, block in blocks_in(lines, start, end, STEP_RE):
            fields = field_map(block)
            title_clean, title_tags, title_unknown = scan_tags(title)
            title_clean = re.sub(r"^[\s·:：\-]+", "", title_clean) or title
            _, field_tags, field_unknown = scan_tags(fields.get("指令", ""))
            directives = list(dict.fromkeys(title_tags + field_tags))
            unknown_directives = list(dict.fromkeys(title_unknown + field_unknown))
            node_raw = fields.get("节点", "")
            node_match = NODE_FIELD_RE.match(node_raw)
            node_id = node_match.group(1) if node_match else node_raw.split()[0] if node_raw else ""
            node_type = ""
            if node_match and node_match.group(2):
                node_type = node_match.group(2).strip().lower()
            targets: list[str] = []
            if fields.get("下一步"):
                targets.extend(ANY_STEP_RE.findall(fields["下一步"]))
            branch_lines: list[str] = []
            for line in block:
                text_line = line.strip()
                match = re.match(r"^-\s*(?P<label>.+?)\s*(?:→|->)\s*(?P<target>S\d+)", text_line)
                if not match:
                    continue
                label = match.group("label").strip()
                if re.match(r"^(下一步|失败|触发|结果|判定|指令|目标|落点|动作|输入|产出|验收)\s*[:：]", label):
                    continue
                branch_lines.append(text_line)
                targets.append(match.group("target"))
            # Deduplicate, preserve order.
            targets = list(dict.fromkeys(targets))
            fail_targets = ARROW_RE.findall(fields.get("失败", ""))
            steps[sid] = {
                "id": sid,
                "title": title_clean,
                "line": line_no,
                "fields": fields,
                "node": node_id,
                "node_type": node_type,
                "targets": targets,
                "branch_lines": branch_lines,
                "fail_targets": fail_targets,
                "directives": directives,
                "unknown_directives": unknown_directives,
                "section": sec,
                "block": block,
            }
    return steps


def check_header(lines: list[str], report: Report) -> str:
    if len(lines) < 3:
        report.fail("首 3 行任务头", "文件少于 3 行")
        return ""
    l1, l2, l3 = (lines[0].strip(), lines[1].strip(), lines[2].strip())

    match = re.match(r"^FLOW-TASK\s*[:：]\s*(\S+)", l1)
    if not match:
        report.fail("首 3 行任务头", "第 1 行必须是 `FLOW-TASK: <type>`", 1)
    else:
        raw = match.group(1)
        task_type = raw.split("/")[0].strip()
        if task_type not in TASK_TYPES:
            report.fail("任务类型", f"未知类型 `{raw}`，可选: {', '.join(TASK_TYPES)}", 1)
        else:
            report.ok("任务类型", f"{task_type} — {TASK_TYPES[task_type]}", 1)

    if not re.match(r"^FLOW-TARGET\s*[:：]\s*\S", l2):
        report.fail("首 3 行任务头", "第 2 行必须是 `FLOW-TARGET: ...`（含 source/stack/entry）", 2)
    else:
        report.ok("目标行", l2[:120], 2)
        if "source" not in l2.lower():
            report.warn("目标行", "建议包含 `source: <源文件>`", 2)
        if "entry" not in l2.lower():
            report.warn("目标行", "建议包含 `entry: S1`", 2)

    if not re.match(r"^FLOW-RULE\s*[:：]\s*\S", l3):
        report.fail("首 3 行任务头", "第 3 行必须是 `FLOW-RULE: ...`", 3)
    else:
        report.ok("规则行", l3[:120], 3)
        if "验收" not in l3:
            report.warn("规则行", "建议写明“每步验收”", 3)
        if "STATUS" not in l3.upper():
            report.warn("规则行", "建议写明“勾选 STATUS”", 3)

    return match.group(1).split("/")[0].strip() if match else ""


def check_sections(lines: list[str], sections: dict[int, tuple[int, int, str]], report: Report, uml: bool = False) -> None:
    required = dict(REQUIRED_SECTIONS)
    if uml:
        required[11] = ("模型规格",)
    for num, keywords in required.items():
        if num not in sections:
            report.fail("章节", f"缺少 `## {num}. {keywords[0]}`", 0)
            continue
        title = sections[num][2]
        allowed = keywords
        if uml and num == 3:
            allowed = ("边清单", "关系清单", "消息清单")
        if not any(k in title for k in allowed):
            report.fail("章节", f"`## {num}.` 标题应包含“{keywords[0]}”，实际为“{title}”", sections[num][0] + 1)
        else:
            report.ok("章节", f"{num}. {title}", sections[num][0] + 1)


def check_steps(steps: dict[str, dict[str, Any]], report: Report, uml: bool = False) -> None:
    if not steps:
        report.fail("构建步骤", "没有找到 `### S1 · ...` 形式的步骤")
        return

    seen_nodes: dict[str, str] = {}
    for sid, step in steps.items():
        fields = step["fields"]
        line = step["line"]
        if not step["node"]:
            report.fail(f"{sid} 节点引用", "缺少 `- 节点: Nx (type)`", line)
        else:
            if step["node"] in seen_nodes and step["section"] == 4 and not uml:
                report.warn(f"{sid} 节点复用", f"节点 {step['node']} 已在 {seen_nodes[step['node']]} 出现", line)
            seen_nodes[step["node"]] = sid

        directives = step.get("directives", [])
        is_or = "OR" in directives
        is_decision = (step["node_type"] == "decision" or "判定" in fields or "DQ" in directives) and not is_or
        is_end = step["node_type"] == "end" or "END" in directives
        is_branch = step["section"] == 5

        if is_or:
            required = STEP_FIELDS
        elif is_decision:
            required = DECISION_REQUIRED
        elif is_end:
            required = STEP_FIELDS + ("结果",)
        elif is_branch:
            required = BRANCH_REQUIRED
        else:
            required = PLAIN_REQUIRED

        for key in required:
            if not fields.get(key):
                report.fail(f"{sid} 字段", f"缺少 `- {key}: ...`", line)

        if is_or:
            branches = step["branch_lines"]
            if len(branches) < 2:
                report.fail(f"{sid} 或分支", f"{{OR}} 至少要有 2 条带标签分支，实际 {len(branches)} 条", line)
            if len(step["targets"]) < 2:
                report.fail(f"{sid} 或去向", "{{OR}} 至少要有 2 个去向", line)

        if is_decision:
            branches = step["branch_lines"]
            if len(branches) < 2:
                report.fail(f"{sid} 判断分支", f"判断步骤至少要有 2 条 `- 是/否 → Sx`，实际 {len(branches)} 条", line)
            if len(step["targets"]) < 2:
                report.fail(f"{sid} 判断去向", "判断步骤至少要有 2 个去向", line)

        if not is_end and not step["targets"]:
            report.fail(f"{sid} 下一步", "非结束步骤必须给出 `- 下一步: Sx` 或分支去向", line)

        if step["section"] == 5 and not fields.get("触发"):
            report.fail(f"{sid} 触发条件", "分支步骤必须写 `- 触发: Sx = 是/否`", line)

        if is_end and step["targets"]:
            report.warn(f"{sid} 结束步骤", "结束步骤不应再有下一步", line)

        if not is_decision and not is_or and not is_end and len(step["targets"]) > 1 and not uml:
            report.warn(f"{sid} 多去向", "非判断步骤出现多个去向，确认不是把判断写成了处理", line)

    # Target existence.
    for sid, step in steps.items():
        for target in step["targets"]:
            if target not in steps:
                report.fail(f"{sid} 去向", f"指向不存在的步骤 {target}", step["line"])
        for target in step.get("fail_targets", []):
            if target not in steps:
                report.fail(f"{sid} 失败去向", f"指向不存在的步骤 {target}", step["line"])

    report.ok("步骤完整性", f"共 {len(steps)} 个步骤，字段/去向已检查")


def check_status(lines: list[str], steps: dict[str, dict[str, Any]], sections: dict[int, tuple[int, int, str]], report: Report) -> None:
    if 8 not in sections:
        return
    start, end, _ = sections[8]
    checked: dict[str, int] = {}
    for i in range(start + 1, end):
        match = re.match(r"^\s*-\s*\[[ xX]\]\s*(S\d+)\b", lines[i])
        if match:
            sid = match.group(1)
            if sid in checked:
                report.fail("执行状态", f"{sid} 在 STATUS 中重复", i + 1)
            checked[sid] = i + 1
    missing = sorted(set(steps) - set(checked), key=lambda s: int(s[1:]))
    unknown = sorted(set(checked) - set(steps), key=lambda s: int(s[1:]))
    if missing:
        report.fail("执行状态", f"STATUS 缺少: {', '.join(missing)}", start + 1)
    if unknown:
        report.fail("执行状态", f"STATUS 包含不存在的步骤: {', '.join(unknown)}", start + 1)
    if not missing and not unknown:
        report.ok("执行状态", f"{len(checked)} 个步骤都有勾选项", start + 1)


def check_loops(lines: list[str], sections: dict[int, tuple[int, int, str]], graph: dict[str, Any], report: Report) -> None:
    back_edges = graph.get("back_edges", [])
    loops: list[tuple[str, dict[str, str], int]] = []
    if 6 in sections:
        start, end, _ = sections[6]
        for lid, _title, line_no, block in blocks_in(lines, start, end, LOOP_RE):
            loops.append((lid, field_map(block), line_no))

    for lid, fields, line_no in loops:
        for key in ("回边", "继续条件", "退出条件", "最大次数"):
            if not fields.get(key):
                report.fail(f"{lid} 字段", f"循环缺少 `- {key}: ...`", line_no)
        if fields.get("最大次数") and not re.search(r"\d", fields["最大次数"]):
            report.warn(f"{lid} 最大次数", "建议写成明确数字，如 3", line_no)

    if back_edges and not loops:
        report.fail("循环", f"检测到回边 {back_edges}，但 §6 没有 `### L1` 循环定义", 0)
    if loops:
        report.ok("循环", f"{len(loops)} 个循环，回边 {len(back_edges)} 条", 0)


def _step_text(step: dict[str, Any]) -> str:
    fields = step["fields"]
    return " ".join([step["title"]] + [str(value) for value in fields.values()])


HINTS: dict[str, tuple[tuple[str, ...], str]] = {
    "PREPARE": (("初始化", "准备", "安装", "配置", "建目录", "创建", "依赖"),
                "预备步骤应说明初始化/安装/配置动作"),
    "CARD": (("卡片", "面板", "界面", "显示", "渲染"),
             "卡片步骤应说明界面位置或展示内容"),
    "DB": (("数据库", "表", "schema", "SQLite", "repository", "模型"),
           "数据库步骤应说明库/表/schema"),
    "STORGE": (("保存", "写入", "持久化", "存", "库"),
               "储存步骤应说明写到哪里、如何查回"),
    "DATA": (("数据", "结构", "字段", "schema", "JSON", "类型", "契约", "prompt", "请求体"),
             "数据步骤应说明字段/结构/契约"),
    "DELAY": (("等待", "延迟", "超时", "sleep", "ms", "毫秒", "秒", "节流"),
              "延迟步骤应说明等待时长或超时值"),
    "PRINT": (("显示", "渲染", "输出", "打印", "面板", "界面", "粘贴板"),
              "显示步骤应说明用户能看到什么"),
    "FILE": (("文件", "路径", "目录", ".md", ".json", ".txt", ".csv"),
             "文件步骤应说明具体路径或格式"),
    "MFL": (("批量", "目录", "多文件", "多文档", "遍历"),
            "多文档步骤应说明批量范围"),
    "INPUT": (("输入", "手动", "用户", "填写", "粘贴", "选"),
              "手动输入步骤应说明谁输入什么"),
    "CTIHD": (("点击", "按键", "右键", "拖拽", "手动", "人工", "确认", "操作"),
              "手动操作步骤应说明具体人工动作"),
    "SUM": (("求和", "合计", "总计", "总数", "sum", "count", "聚合"),
            "求和步骤应说明聚合字段与口径"),
    "TRANSMUTE": (("发送", "接收", "上传", "下载", "传输", "请求", "HTTP", "API", "接口", "调用", "队列", "剪贴板"),
                  "传输步骤应说明源、目标与协议"),
    "LINEAR": (("排序", "顺序", "order", "sort", "按"),
               "排序步骤应说明排序键与方向"),
    "OR": (("或", "分支", "选择", "任一"),
           "或分支应给每条分支加标签"),
    "CLASS": (("类", "属性", "操作", "职责", "class"),
              "类步骤应说明属性/操作/职责"),
    "IFACE": (("接口", "协议", "方法", "interface"),
              "接口步骤应说明方法契约"),
    "ENUM": (("枚举", "常量", "值", "enum"),
             "枚举步骤应说明取值集合"),
    "ACTOR": (("参与者", "用户", "角色", "actor"),
              "参与者步骤应说明外部角色"),
    "USECASE": (("用例", "场景", "功能", "use case"),
                "用例步骤应说明触发场景与验收"),
    "COMPONENT": (("组件", "模块", "服务", "component"),
                  "组件步骤应说明职责与依赖"),
    "SERVICE": (("服务", "部署", "端口", "service"),
                "服务步骤应说明部署与端口"),
    "STATE": (("状态", "迁移", "事件", "state"),
              "状态步骤应说明事件与迁移"),
    "ENTITY": (("实体", "表", "字段", "entity"),
               "实体步骤应说明字段与主键"),
    "MESSAGE": (("消息", "发送", "接收", "调用", "message"),
                "消息步骤应说明发送者、接收者与顺序"),
    "RELATION": (("关系", "关联", "组合", "聚合", "继承", "依赖", "relation"),
                 "关系步骤应说明实现方式"),
    "TRANSITION": (("迁移", "事件", "守卫", "动作", "transition"),
                   "迁移步骤应说明事件、守卫与动作"),
    "TABLE": (("表", "字段", "主键", "索引", "table"),
              "数据表步骤应说明字段与主键"),
    "API": (("API", "端点", "请求", "响应", "endpoint"),
            "API 步骤应说明请求/响应契约"),
    "REPO": (("仓储", "repository", "查询", "保存", "写入"),
             "仓储步骤应说明查询与保存接口"),
}


def check_directives(step: dict[str, Any], loop_text: str,
                     graph: dict[str, Any], report: Report) -> int:
    sid = step["id"]
    line = step["line"]
    tags = step["directives"]
    for tag in step.get("unknown_directives", []):
        report.fail(f"{sid} 功能头", f"未知指令 {{{tag}}}；请查阅 references/directive-catalog.md", line)
    if not tags:
        return 0

    fields = step["fields"]
    targets = step["targets"]
    control = [tag for tag in tags if DIRECTIVES[tag]["category"] == "control"]
    text = _step_text(step)

    if "START" in control and "END" in control:
        report.fail(f"{sid} 功能头冲突", "{START} 与 {END} 不能同时出现", line)
    elif "END" in control and len(control) > 1:
        report.fail(f"{sid} 功能头冲突", "{END} 不能和其他控制指令组合", line)
    if "DQ" in control and "OR" in control:
        report.fail(f"{sid} 功能头冲突", "{DQ} 与 {OR} 不能同时出现", line)

    if "END" in control:
        if targets:
            report.fail(f"{sid} {{END}}", "结束步骤不能再有下一步", line)
        if not fields.get("结果"):
            report.fail(f"{sid} {{END}}", "结束步骤必须写 `- 结果:`", line)

    if "START" in control:
        if sid != "S1" and step["node_type"] != "start":
            report.warn(f"{sid} {{START}}", "起始指令通常放在 S1；确认这是新的子流程入口", line)

    if "DQ" in control:
        if not fields.get("判定"):
            report.fail(f"{sid} {{DQ}}", "判断步骤必须写 `- 判定:`", line)
        if len(targets) < 2:
            report.fail(f"{sid} {{DQ}}", f"判断步骤至少 2 个去向，实际 {len(targets)} 个", line)

    if "OR" in control:
        if len(targets) < 2:
            report.fail(f"{sid} {{OR}}", f"或分支至少 2 个去向，实际 {len(targets)} 个", line)
        if not step["branch_lines"]:
            report.warn(f"{sid} {{OR}}", "建议用 `- 分支名 → Sx` 标出每条分支", line)

    if "LOOP" in control:
        back_edges = graph.get("back_edges", [])
        participates = any(step["node"] in str(edge).split("→") for edge in back_edges)
        if not participates:
            participates = any(int(target[1:]) <= int(sid[1:]) for target in targets if target[1:].isdigit())
        if not back_edges or not participates:
            report.fail(f"{sid} {{LOOP}}", "标了循环，但 flow-json 中没有对应回边", line)
        if "退出条件" not in loop_text:
            report.fail(f"{sid} {{LOOP}}", "§6 缺少循环退出条件", line)

    if "LPAR" in control:
        if "最大次数" not in text and "最大次数" not in loop_text:
            report.fail(f"{sid} {{LPAR}}", "循环限制必须写 `- 最大次数: <数字>`", line)

    if "MSE" in tags:
        if not re.search(r"\d", text) and not any(
                word in text for word in ("测量", "断言", "阈值", "基准", "校验")):
            report.warn(f"{sid} {{MSE}}", "测量步骤应有数字阈值或可断言指标", line)

    for tag, (keywords, message) in HINTS.items():
        if tag in tags and not any(word in text for word in keywords):
            report.warn(f"{sid} {{{tag}}}", message, line)

    return 1


def check_gates(lines: list[str], sections: dict[int, tuple[int, int, str]], report: Report) -> None:
    if 7 not in sections:
        return
    start, end, _ = sections[7]
    gates = blocks_in(lines, start, end, GATE_RE)
    if not gates:
        report.fail("验收门槛", "§7 至少要有一个 `### G1 · ...` 总验收", start + 1)
        return
    for gid, _title, line_no, block in gates:
        fields = field_map(block)
        for key in ("命令", "通过"):
            if not fields.get(key):
                report.fail(f"{gid} 字段", f"验收门槛缺少 `- {key}: ...`", line_no)
    report.ok("验收门槛", f"{len(gates)} 个总验收", start + 1)


def load_flow_json(text: str) -> tuple[dict[str, Any] | None, int]:
    fence = re.search(r"```(?:flow-json|json)\s*\n(.*?)\n```", text, re.S)
    if not fence:
        return None, 0
    try:
        data = json.loads(fence.group(1))
    except json.JSONDecodeError as exc:
        return {"__error__": str(exc)}, fence.start(1) and text[:fence.start(1)].count("\n") + 1
    return data, text[:fence.start(1)].count("\n") + 1


def check_uml_graph(diagram: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
                    node_type: dict[str, str], out: dict[str, list[str]],
                    report: Report, line_offset: int) -> None:
    if diagram == "uml-sequence":
        orders = sorted(int(edge.get("order", 0)) for edge in edges if edge.get("order"))
        if orders:
            expected = list(range(1, len(orders) + 1))
            if orders != expected:
                report.fail("时序消息", f"消息顺序应为 1..{len(orders)}，实际 {orders}", line_offset)
            else:
                report.ok("时序消息", f"{len(orders)} 条消息顺序连续", line_offset)
        else:
            report.warn("时序消息", "flow-json 的边缺少 order 字段，无法校验消息顺序", line_offset)
        for edge in edges:
            if not edge.get("from") or not edge.get("to"):
                report.fail("时序消息", f"消息缺少发送者/接收者: {edge}", line_offset)

    elif diagram == "uml-state":
        initial = [n for n in nodes if n.get("state_kind") == "initial"]
        final = [n for n in nodes if n.get("state_kind") == "final"]
        if not initial:
            report.fail("状态图", "缺少初始状态 [*]", line_offset)
        if not final:
            report.fail("状态图", "缺少结束状态 [*]", line_offset)
        for node in nodes:
            nid = str(node.get("id"))
            if node.get("state_kind") in ("initial", "final"):
                continue
            if not out.get(nid):
                report.fail("状态图", f"状态 {nid} 没有出边，也不是结束状态", line_offset)
        if initial and final:
            report.ok("状态图", f"{len(nodes)} 个状态 / {len(edges)} 条迁移", line_offset)

    elif diagram == "uml-usecase":
        actors = [nid for nid, value in node_type.items() if value == "actor"]
        usecases = [nid for nid, value in node_type.items() if value == "usecase"]
        if not actors:
            report.fail("用例图", "缺少 actor", line_offset)
        if not usecases:
            report.fail("用例图", "缺少 usecase", line_offset)
        for usecase in usecases:
            has_actor = any(
                (edge["from"] in actors and edge["to"] == usecase)
                or (edge["to"] in actors and edge["from"] == usecase)
                for edge in edges
            )
            if not has_actor:
                report.warn("用例图", f"用例 {usecase} 没有关联任何 actor", line_offset)
        if actors and usecases:
            report.ok("用例图", f"{len(actors)} 个参与者 / {len(usecases)} 个用例", line_offset)

    elif diagram == "uml-er":
        for node in nodes:
            if node.get("type") == "entity" and not node.get("attributes"):
                report.warn("ER 图", f"实体 {node.get('id')} 没有字段", line_offset)
        report.ok("ER 图", f"{len(nodes)} 个实体 / {len(edges)} 个关系", line_offset)

    elif diagram == "uml-class":
        for edge in edges:
            if edge.get("kind") in ("inheritance", "realization") and node_type.get(edge["to"]) not in ("class", "interface"):
                report.warn("类图", f"{edge['from']}→{edge['to']} 的父类型不是 class/interface", line_offset)
        report.ok("类图", f"{len(nodes)} 个类/接口 / {len(edges)} 个关系", line_offset)

    elif diagram in ("uml-component", "uml-deployment"):
        if not any(value in ("component", "node", "artifact", "cloud", "database") for value in node_type.values()):
            report.fail(diagram, "没有 component/node/artifact/database 元素", line_offset)
        else:
            report.ok(diagram, f"{len(nodes)} 个组件/节点 / {len(edges)} 条连接", line_offset)

    elif diagram == "uml-activity":
        if not any(value == "start" for value in node_type.values()):
            report.warn("活动图", "没有 start 节点", line_offset)
        if not any(value == "end" for value in node_type.values()):
            report.warn("活动图", "没有 stop/end 节点", line_offset)
        report.ok("活动图", f"{len(nodes)} 个动作/判断 / {len(edges)} 条流", line_offset)


def _split_table_row(line: str) -> list[str]:
    text = line.strip().strip("|")
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if text[i] == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(text[i])
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _markdown_tables(lines: list[str], start: int, end: int) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    i = start
    while i < end:
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < end and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            header = _split_table_row(line)
            rows: list[list[str]] = []
            j = i + 2
            while j < end and lines[j].strip().startswith("|"):
                cells = _split_table_row(lines[j])
                if len(cells) == len(header):
                    rows.append(cells)
                j += 1
            tables.append((header, rows))
            i = j
        else:
            i += 1
    return tables


def _cell_id(value: str) -> str:
    text = value.strip().strip("`[]() ")
    match = re.match(r"[A-Za-z0-9_.-]+", text)
    return match.group(0) if match else text


def check_uml_model(lines: list[str], sections: dict[int, tuple[int, int, str]],
                    steps: dict[str, dict[str, Any]], graph: dict[str, Any], report: Report) -> None:
    if 11 not in sections:
        report.fail("UML 模型规格", "UML 图必须包含 `## 11. 模型规格`", 0)
        return
    start, end, _ = sections[11]
    tables = _markdown_tables(lines, start, end)
    model_header: list[str] = []
    model_rows: list[list[str]] = []
    rel_header: list[str] = []
    rel_rows: list[list[str]] = []
    for header, rows in tables:
        joined = " ".join(header).lower()
        if ("元素id" in joined or "模型元素" in joined) and ("uml" in joined or "类型" in joined):
            model_header, model_rows = header, rows
        if "from" in joined and "to" in joined and ("关系" in joined or "消息" in joined):
            rel_header, rel_rows = header, rows

    if not model_header:
        report.fail("UML 模型规格", "缺少模型元素表（表头需含 元素ID / UML类型 / 名称 / 代码落点）", start + 1)
    if not rel_header:
        report.fail("UML 模型规格", "缺少关系/消息表（表头需含 From / To / 关系或消息）", start + 1)

    node_ids = {str(nid) for nid in graph.get("node_ids", [])}
    edges = graph.get("edges", [])
    diagram = str(graph.get("diagram", ""))

    if model_header:
        if not any("落点" in header or "代码" in header for header in model_header):
            report.warn("UML 模型规格", "模型元素表建议包含“代码落点”列", start + 1)
        model_ids = {_cell_id(row[0]) for row in model_rows if row}
        missing = node_ids - model_ids
        extra = model_ids - node_ids
        if missing:
            report.fail("UML 元素覆盖", f"模型元素表缺少: {', '.join(sorted(missing))}", start + 1)
        if extra:
            report.fail("UML 元素覆盖", f"模型元素表包含不存在的元素: {', '.join(sorted(extra))}", start + 1)
        if not missing and not extra:
            report.ok("UML 元素覆盖", f"{len(model_ids)} 个元素与 flow-json 一致", start + 1)

    if rel_header:
        pairs = {(_cell_id(row[0]), _cell_id(row[1])) for row in rel_rows if len(row) >= 2}
        missing_edges = [
            f"{edge['from']}→{edge['to']}" for edge in edges
            if (edge["from"], edge["to"]) not in pairs and (edge["to"], edge["from"]) not in pairs
        ]
        if missing_edges:
            report.fail("UML 关系覆盖", f"关系/消息表缺少: {', '.join(missing_edges)}", start + 1)
        else:
            report.ok("UML 关系覆盖", f"{len(edges)} 条关系/消息均已登记", start + 1)

        if diagram == "uml-sequence":
            order_index = next((i for i, header in enumerate(rel_header)
                                if "顺序" in header or "序号" in header), None)
            if order_index is None:
                report.warn("UML 时序", "关系/消息表建议包含“顺序/序号”列", start + 1)
            else:
                orders = []
                for row in rel_rows:
                    if len(row) > order_index:
                        match = re.search(r"\d+", row[order_index])
                        if match:
                            orders.append(int(match.group(0)))
                expected = list(range(1, len(edges) + 1))
                if sorted(orders) != expected:
                    report.fail("UML 时序", f"消息顺序应覆盖 1..{len(edges)}，实际 {sorted(orders)}", start + 1)
                else:
                    report.ok("UML 时序", f"{len(orders)} 条消息顺序连续", start + 1)

    if diagram == "uml-class" and model_rows:
        model_text = " ".join(" | ".join(row) for row in model_rows)
        for node in graph.get("nodes", []):
            members = list(node.get("attributes") or []) + list(node.get("operations") or [])
            if members and not any(_cell_id(member) in model_text or member in model_text for member in members):
                report.warn("UML 类成员", f"{node.get('id')} 的属性/操作未在模型表中体现", start + 1)


def check_flow_json(data: dict[str, Any], steps: dict[str, dict[str, Any]], report: Report,
                    line_offset: int, uml: bool = False) -> dict[str, Any]:
    if "__error__" in data:
        report.fail("flow-json", f"JSON 解析失败: {data['__error__']}", line_offset)
        return {}
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        report.fail("flow-json", "必须包含 nodes[] 和 edges[] 数组", line_offset)
        return {}

    node_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or not node.get("id"):
            report.fail("flow-json 节点", "每个节点必须有 id", line_offset)
            continue
        if node["id"] in node_ids:
            report.fail("flow-json 节点", f"节点 id 重复: {node['id']}", line_offset)
        node_ids.add(str(node["id"]))

    for node in nodes:
        if not isinstance(node, dict):
            continue
        raw = node.get("directive") or node.get("directives")
        if not raw:
            continue
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            text = str(entry).strip()
            if not text:
                continue
            if "{" not in text:
                text = "{" + text + "}"
            _, _known, unknown = scan_tags(text)
            for tag in unknown:
                report.fail("flow-json 功能头", f"节点 {node.get('id')} 使用了未知指令 {{{tag}}}", line_offset)

    edges_clean: list[dict[str, str]] = []
    for edge in edges:
        if not isinstance(edge, dict) or not edge.get("from") or not edge.get("to"):
            report.fail("flow-json 边", "每条边必须有 from/to", line_offset)
            continue
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            report.fail("flow-json 边", f"边 {edge['from']}→{edge['to']} 引用了不存在的节点", line_offset)
            continue
        edges_clean.append(edge)

    # Step coverage.
    json_steps = data.get("steps") or []
    if not json_steps:
        report.fail("flow-json 步骤", "缺少 steps[] 数组", line_offset)
    json_step_ids = {str(s.get("id")) for s in json_steps if isinstance(s, dict) and s.get("id")}
    md_ids = set(steps)
    if json_step_ids:
        if json_step_ids != md_ids:
            missing = sorted(md_ids - json_step_ids)
            extra = sorted(json_step_ids - md_ids)
            detail = []
            if missing:
                detail.append("缺少 " + ", ".join(missing))
            if extra:
                detail.append("多余 " + ", ".join(extra))
            report.fail("flow-json 步骤", "与正文步骤不一致：" + "；".join(detail), line_offset)
        else:
            report.ok("flow-json 步骤", f"{len(json_step_ids)} 个步骤与正文一致", line_offset)

    # Node coverage by steps. UML nodes are covered by §11 model table instead.
    step_nodes: set[str] = set()
    for step in steps.values():
        if step["node"]:
            step_nodes.add(step["node"])
    unknown = step_nodes - node_ids
    if unknown:
        report.fail("节点覆盖", f"步骤引用了 flow-json 中不存在的节点: {', '.join(sorted(unknown))}", line_offset)
    if not uml:
        uncovered = node_ids - step_nodes
        if uncovered:
            report.fail("节点覆盖", f"这些节点没有对应步骤: {', '.join(sorted(uncovered))}", line_offset)
        if not uncovered and not unknown:
            report.ok("节点覆盖", f"{len(node_ids)} 个节点全部有步骤", line_offset)
    else:
        report.ok("UML 节点", f"{len(node_ids)} 个模型元素，覆盖由 §11 校验", line_offset)

    diagram = str(data.get("diagram", "flowchart"))
    out: dict[str, list[str]] = {nid: [] for nid in node_ids}
    indeg: dict[str, int] = {nid: 0 for nid in node_ids}
    for edge in edges_clean:
        out[edge["from"]].append(edge["to"])
        indeg[edge["to"]] += 1

    node_type = {str(n.get("id")): str(n.get("type", "")) for n in nodes if isinstance(n, dict) and n.get("id")}
    back_edges: list[tuple[str, str]] = []

    if not uml:
        starts = [nid for nid in node_ids if node_type.get(nid) == "start" or indeg.get(nid, 0) == 0]
        ends = {nid for nid in node_ids if node_type.get(nid) == "end" or not out.get(nid)}
        if not starts:
            report.fail("flow-json 起点", "没有 start / 入度为 0 的节点", line_offset)
        if not ends:
            report.fail("flow-json 终点", "没有 end / 出度为 0 的节点", line_offset)

        for nid in node_ids:
            if node_type.get(nid) == "decision" and len(out.get(nid, [])) < 2:
                report.fail("判断节点", f"{nid} 是 decision，但出边只有 {len(out.get(nid, []))} 条", line_offset)
            if node_type.get(nid) != "end" and not out.get(nid):
                report.fail("死端", f"{nid} 不是 end，却没有出边", line_offset)

        def reachable(seeds: list[str], adjacency: dict[str, list[str]]) -> set[str]:
            seen: set[str] = set()
            stack = list(seeds)
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                stack.extend(adjacency.get(cur, []))
            return seen

        if starts:
            reached = reachable(starts, out)
            unreachable = node_ids - reached
            if unreachable:
                report.fail("可达性", f"从起点无法到达: {', '.join(sorted(unreachable))}", line_offset)
            else:
                report.ok("可达性", f"{len(node_ids)} 个节点均可从起点到达", line_offset)

        if ends:
            reverse: dict[str, list[str]] = {nid: [] for nid in node_ids}
            for edge in edges_clean:
                reverse[edge["to"]].append(edge["from"])
            can_end = reachable(list(ends), reverse)
            stuck = node_ids - can_end
            if stuck:
                report.fail("终止性", f"这些节点无法到达任何 end: {', '.join(sorted(stuck))}", line_offset)
            else:
                report.ok("终止性", f"{len(node_ids)} 个节点均可到达 end", line_offset)

        color: dict[str, int] = {nid: 0 for nid in node_ids}

        def dfs(nid: str) -> None:
            color[nid] = 1
            for nxt in out.get(nid, []):
                if color.get(nxt) == 1:
                    back_edges.append((nid, nxt))
                elif color.get(nxt, 0) == 0:
                    dfs(nxt)
            color[nid] = 2

        for nid in node_ids:
            if color.get(nid, 0) == 0:
                dfs(nid)
        report.ok("flow-json 图", f"{len(node_ids)} 节点 / {len(edges_clean)} 边 / 回边 {len(back_edges)}", line_offset)
    else:
        check_uml_graph(diagram, nodes, edges_clean, node_type, out, report, line_offset)
        report.ok("UML 图", f"{diagram} / {len(node_ids)} 元素 / {len(edges_clean)} 关系", line_offset)

    return {
        "diagram": diagram,
        "back_edges": [f"{a}→{b}" for a, b in back_edges],
        "node_ids": sorted(node_ids),
        "edges": edges_clean,
        "nodes": nodes,
    }


def to_mermaid(data: dict[str, Any]) -> str:
    diagram = str(data.get("diagram", "flowchart"))
    nodes = {str(n["id"]): n for n in data.get("nodes", []) if isinstance(n, dict) and n.get("id")}
    edges = [e for e in data.get("edges", []) if isinstance(e, dict)]
    if diagram == "uml-class":
        lines = ["classDiagram"]
        for nid, node in nodes.items():
            attrs = node.get("attributes") or []
            ops = node.get("operations") or []
            uml = node.get("uml_type") or node.get("type") or "class"
            stereo = {"interface": "<<interface>>", "enum": "<<enumeration>>"}.get(uml)
            if not attrs and not ops and not stereo:
                lines.append(f"    class {nid}")
                continue
            lines.append(f"    class {nid} {{")
            if stereo:
                lines.append(f"        {stereo}")
            for item in attrs + ops:
                lines.append(f"        {item}")
            lines.append("    }")
        for edge in edges:
            kind = edge.get("kind", "association")
            left, right = edge["from"], edge["to"]
            label = f' : {edge["label"]}' if edge.get("label") else ""
            if kind == "inheritance":
                lines.append(f"    {right} <|-- {left}{label}")
            elif kind == "realization":
                lines.append(f"    {right} <|.. {left}{label}")
            elif kind == "composition":
                lines.append(f"    {left} *-- {right}{label}")
            elif kind == "aggregation":
                lines.append(f"    {left} o-- {right}{label}")
            elif kind == "dependency":
                lines.append(f"    {left} ..> {right}{label}")
            else:
                lines.append(f"    {left} --> {right}{label}")
        return "\n".join(lines) + "\n"
    if diagram == "uml-sequence":
        lines = ["sequenceDiagram"]
        for nid, node in nodes.items():
            keyword = {"actor": "actor", "database": "database", "queue": "queue"}.get(node.get("type", ""), "participant")
            lines.append(f"    {keyword} {nid}")
        for edge in sorted(edges, key=lambda item: int(item.get("order", 0) or 0)):
            arrow = {"return": "-->>", "async": "->>", "error": "-x"}.get(edge.get("message_kind", ""), "->")
            lines.append(f"    {edge['from']}{arrow}{edge['to']}: {edge.get('label', '')}")
        return "\n".join(lines) + "\n"
    if diagram == "uml-state":
        lines = ["stateDiagram-v2"]
        for edge in edges:
            label = f" : {edge['label']}" if edge.get("label") else ""
            lines.append(f"    {edge['from']} --> {edge['to']}{label}")
        return "\n".join(lines) + "\n"
    if diagram == "uml-er":
        lines = ["erDiagram"]
        for edge in edges:
            lines.append(f"    {edge['from']} ||--o{{ {edge['to']} : {edge.get('label', '')}")
        return "\n".join(lines) + "\n"

    lines = ["flowchart TD"]
    for nid, node in nodes.items():
        prefix = f"{{{node['directive']}}} " if node.get("directive") else ""
        label = (prefix + str(node.get("label", nid))).replace('"', "'")
        ntype = str(node.get("type", "process"))
        if ntype in ("start", "end"):
            lines.append(f'    {nid}(["{label}"])')
        elif ntype == "decision":
            lines.append(f'    {nid}{{"{label}"}}')
        elif ntype == "database":
            lines.append(f'    {nid}[("{label}")]')
        elif ntype == "io":
            lines.append(f'    {nid}[/"{label}"/]')
        elif ntype == "subprocess":
            lines.append(f'    {nid}[["{label}"]]')
        else:
            lines.append(f'    {nid}["{label}"]')
    for edge in data.get("edges", []):
        label = str(edge.get("label", "")).replace('"', "'")
        if label:
            lines.append(f'    {edge["from"]} -- "{label}" --> {edge["to"]}')
        else:
            lines.append(f'    {edge["from"]} --> {edge["to"]}')
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Validate an agent-executable logic MD")
    parser.add_argument("source", help="logic markdown file")
    parser.add_argument("--json", action="store_true", help="print parsed summary as JSON")
    parser.add_argument("--mermaid", action="store_true", help="print Mermaid rebuilt from flow-json")
    args = parser.parse_args(argv)

    path = Path(args.source)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    report = Report()
    uml = bool(re.search(r'"diagram"\s*:\s*"uml-', text))
    task_type = check_header(lines, report)
    sections = section_ranges(lines)
    check_sections(lines, sections, report, uml)
    steps = parse_steps(lines, sections)
    check_steps(steps, report, uml)
    check_status(lines, steps, sections, report)
    check_gates(lines, sections, report)

    data, line_offset = load_flow_json(text)
    graph: dict[str, Any] = {}
    if data is None:
        report.fail("flow-json", "缺少 ```flow-json 代码块（机器可读图）", 0)
    else:
        if 9 not in sections and not data.get("warnings"):
            pass
        graph = check_flow_json(data, steps, report, line_offset, uml)
        if uml:
            check_uml_model(lines, sections, steps, graph, report)
    loop_text = ""
    if 6 in sections:
        start, end, _ = sections[6]
        loop_text = "\n".join(lines[start:end])
    directive_steps = sum(check_directives(step, loop_text, graph, report) for step in steps.values())
    if directive_steps:
        report.ok("功能头", f"{directive_steps} 个步骤使用了功能头指令")
    else:
        report.warn("功能头", "未使用 {TAG} 功能头；建议对关键节点标注，便于下游 agent 识别")
    if not uml:
        check_loops(lines, sections, graph, report)

    if args.mermaid:
        if not data:
            print("ERROR: no flow-json", file=sys.stderr)
            return 1
        print(to_mermaid(data), end="")
        return 0

    if args.json:
        payload = {
            "file": str(path),
            "task": task_type,
            "sections": {str(k): v[2] for k, v in sorted(sections.items())},
            "steps": {sid: {"node": s["node"], "next": s["targets"]} for sid, s in steps.items()},
            "graph": graph,
            "result": {
                "pass": report.pass_count,
                "fail": report.fail_count,
                "warn": report.warn_count,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        report.render()

    return 0 if report.fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
