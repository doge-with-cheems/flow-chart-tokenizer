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


def check_sections(lines: list[str], sections: dict[int, tuple[int, int, str]], report: Report) -> None:
    for num, keywords in REQUIRED_SECTIONS.items():
        if num not in sections:
            report.fail("章节", f"缺少 `## {num}. {keywords[0]}`", 0)
            continue
        title = sections[num][2]
        if not any(k in title for k in keywords):
            report.fail("章节", f"`## {num}.` 标题应包含“{keywords[0]}”，实际为“{title}”", sections[num][0] + 1)
        else:
            report.ok("章节", f"{num}. {title}", sections[num][0] + 1)


def check_steps(steps: dict[str, dict[str, Any]], report: Report) -> None:
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
            if step["node"] in seen_nodes and step["section"] == 4:
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

        if not is_decision and not is_or and not is_end and len(step["targets"]) > 1:
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


def check_flow_json(data: dict[str, Any], steps: dict[str, dict[str, Any]], report: Report, line_offset: int) -> dict[str, Any]:
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

    # Node coverage by steps.
    step_nodes: set[str] = set()
    for step in steps.values():
        if step["node"]:
            step_nodes.add(step["node"])
    uncovered = node_ids - step_nodes
    if uncovered:
        report.fail("节点覆盖", f"这些节点没有对应步骤: {', '.join(sorted(uncovered))}", line_offset)
    unknown = step_nodes - node_ids
    if unknown:
        report.fail("节点覆盖", f"步骤引用了 flow-json 中不存在的节点: {', '.join(sorted(unknown))}", line_offset)
    if not uncovered and not unknown:
        report.ok("节点覆盖", f"{len(node_ids)} 个节点全部有步骤", line_offset)

    # Degrees, reachability, back edges.
    out: dict[str, list[str]] = {nid: [] for nid in node_ids}
    indeg: dict[str, int] = {nid: 0 for nid in node_ids}
    for edge in edges_clean:
        out[edge["from"]].append(edge["to"])
        indeg[edge["to"]] += 1

    node_type = {str(n.get("id")): str(n.get("type", "")) for n in nodes if isinstance(n, dict) and n.get("id")}
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

    # DFS back edges.
    color: dict[str, int] = {nid: 0 for nid in node_ids}
    back_edges: list[tuple[str, str]] = []

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
    return {"back_edges": [f"{a}→{b}" for a, b in back_edges]}


def to_mermaid(data: dict[str, Any]) -> str:
    nodes = {str(n["id"]): n for n in data.get("nodes", []) if isinstance(n, dict) and n.get("id")}
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
    task_type = check_header(lines, report)
    sections = section_ranges(lines)
    check_sections(lines, sections, report)
    steps = parse_steps(lines, sections)
    check_steps(steps, report)
    check_status(lines, steps, sections, report)
    check_gates(lines, sections, report)

    data, line_offset = load_flow_json(text)
    graph: dict[str, Any] = {}
    if data is None:
        report.fail("flow-json", "缺少 ```flow-json 代码块（机器可读图）", 0)
    else:
        if 9 not in sections and not data.get("warnings"):
            pass
        graph = check_flow_json(data, steps, report, line_offset)
    loop_text = ""
    if 6 in sections:
        start, end, _ = sections[6]
        loop_text = "\n".join(lines[start:end])
    directive_steps = sum(check_directives(step, loop_text, graph, report) for step in steps.values())
    if directive_steps:
        report.ok("功能头", f"{directive_steps} 个步骤使用了功能头指令")
    else:
        report.warn("功能头", "未使用 {TAG} 功能头；建议对关键节点标注，便于下游 agent 识别")
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
