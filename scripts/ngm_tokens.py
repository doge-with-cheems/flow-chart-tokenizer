#!/usr/bin/env python3
"""Tokenize .ngm / Mermaid / draw.io / DOT / JSON / SVG into nodes and edges.

Usage:
  python ngm_tokens.py <file>            # human-readable node/edge tables
  python ngm_tokens.py <file> --json     # normalized flow-json
  python ngm_tokens.py <file> --mermaid  # Mermaid round-trip source
  python ngm_tokens.py <file> --json --out flow.json

Only the Python standard library is required (3.9+).

.ngm is the source file of Nutstore Draw (坚果云绘图). Its container may be
JSON, XML, ZIP, or another binary form. This script sniffs the bytes, walks any
JSON/XML payload generically, and never invents labels. When the file cannot be
decoded it prints a warning and tells you to export SVG/PNG instead.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

from directives import TAG_RE, scan_tags, type_for

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

NODE_ID_KEYS = ("id", "_id", "uid", "key", "nodeId", "node_id", "shapeId", "shape_id")
NODE_LABEL_KEYS = (
    "label", "text", "title", "name", "content", "value", "html",
    "caption", "displayName", "display_name",
)
FROM_KEYS = ("from", "source", "sourceId", "source_id", "start", "startId", "tail", "begin")
TO_KEYS = ("to", "target", "targetId", "target_id", "end", "endId", "head")
TYPE_KEYS = ("type", "shape", "kind", "category", "nodeType", "node_type")
NEXT_KEYS = ("next", "nextNode", "next_node", "successor", "successors", "out", "outgoing")


class Graph:
    def __init__(self, source: str = "", fmt: str = "") -> None:
        self.source = source
        self.fmt = fmt
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, str]] = []
        self.warnings: list[str] = []
        self.order: list[str] = []

    def add_node(self, nid: str, label: str = "", ntype: str | None = None,
                 shape: str | None = None) -> None:
        nid = str(nid).strip()
        if not nid:
            return
        raw_label = clean_label(label)
        clean, tags, unknown = scan_tags(raw_label)
        for tag in unknown:
            warning = f"未知功能头 {{{tag}}}（节点 {nid}），已保留原文。"
            if warning not in self.warnings:
                self.warnings.append(warning)
        directive_type = type_for(tags)
        label = clean
        node = self.nodes.get(nid)
        if node is None:
            self.nodes[nid] = {
                "id": nid,
                "label": label,
                "type": directive_type or normalize_type(ntype, label, shape),
                "shape": shape or "",
                "directive": tags[0] if tags else "",
                "directives": tags,
            }
            self.order.append(nid)
        else:
            if label and not node["label"]:
                node["label"] = label
            if tags:
                merged = list(dict.fromkeys(node.get("directives", []) + tags))
                node["directives"] = merged
                node["directive"] = merged[0]
                if directive_type:
                    node["type"] = directive_type
            if ntype and node["type"] in ("process", ""):
                node["type"] = normalize_type(ntype, label or node["label"], shape)
            if shape and not node["shape"]:
                node["shape"] = shape
                new_type = normalize_type(None, label or node["label"], shape)
                if new_type and node["type"] in ("process", ""):
                    node["type"] = new_type

    def add_edge(self, src: str, dst: str, label: str = "", kind: str = "") -> None:
        src, dst = str(src).strip(), str(dst).strip()
        if not src or not dst or src == dst and not label:
            return
        self.add_node(src)
        self.add_node(dst)
        label = clean_label(label)
        entry = {"from": src, "to": dst, "label": label,
                 "kind": kind or edge_kind(label)}
        if entry not in self.edges:
            self.edges.append(entry)


def clean_label(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    text = str(value)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def normalize_type(raw: str | None, label: str, shape: str | None = None) -> str:
    raw_value = (raw or "").strip().lower()
    shape_value = (shape or "").strip().lower()
    mapping = {
        "start": "start", "end": "end", "decision": "decision",
        "process": "process", "io": "io", "subprocess": "subprocess",
        "database": "database", "parallel": "parallel", "note": "note",
        "rect": "process", "rectangle": "process", "box": "process",
        "activity": "process", "行动": "process", "矩形": "process",
        "hexagon": "process", "六边形": "process",
        "diamond": "decision", "rhombus": "decision", "菱形": "decision",
        "ellipse": "capsule", "circle": "capsule", "oval": "capsule",
        "capsule": "capsule", "rounded": "capsule", "圆角矩形": "capsule",
        "cylinder": "database", "storage": "database", "db": "database",
        "圆柱": "database", "数据库": "database",
        "parallelogram": "io", "document": "io", "input": "io",
        "output": "io", "平行四边形": "io",
        "module": "subprocess", "service": "subprocess",
        "subroutine": "subprocess", "双边框": "subprocess",
        "comment": "note",
    }
    kind = mapping.get(raw_value)
    if not kind:
        kind = {
            "([": "capsule", "[[": "subprocess", "[(": "database",
            "[/": "io", "{{": "process", "(": "capsule", "[": "process",
            "{": "decision", ">": "io",
        }.get(shape_value)
    if kind == "capsule":
        low = (label or "").lower()
        if any(w in low for w in ("结束", "完成", "end", "finish", "done", "终止", "exit")):
            return "end"
        if any(w in low for w in ("开始", "start", "触发", "入口", "begin")):
            return "start"
        return "process"
    if kind:
        return kind
    return infer_type(label, shape_value)


def infer_type(label: str, shape: str | None = None) -> str:
    low = (label or "").lower()
    shp = (shape or "").lower()
    if "?" in low or "？" in low or any(w in low for w in ("是否", "if ", "if(", "switch", "条件")):
        return "decision"
    if shp in ("decision", "diamond", "rhombus"):
        return "decision"
    if any(w in low for w in ("结束", "完成", "end", "finish", "done", "终止", "exit")):
        return "end"
    if any(w in low for w in ("开始", "start", "触发", "入口", "begin")) or shp in ("start", "ellipse-start"):
        return "start"
    if shp in ("database", "cylinder", "storage"):
        return "database"
    if shp in ("subprocess", "module", "service"):
        return "subprocess"
    if shp in ("input", "output", "io", "document", "parallelogram"):
        return "io"
    return "process"


def edge_kind(label: str) -> str:
    low = (label or "").strip().lower()
    if low in ("是", "yes", "y", "true", "通过", "成功", "ok"):
        return "yes"
    if low in ("否", "no", "n", "false", "不通过", "失败", "error"):
        return "no"
    if any(w in low for w in ("error", "错误", "异常", "失败", "超时", "timeout")):
        return "error"
    return "normal"


# ---------------------------------------------------------------------------
# Generic JSON walk
# ---------------------------------------------------------------------------

def _first(obj: dict, keys: Iterable[str]) -> Any:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def _id_of(value: Any) -> str:
    if isinstance(value, dict):
        got = _first(value, NODE_ID_KEYS)
        return str(got).strip() if got not in (None, "") else ""
    if isinstance(value, (str, int)):
        return str(value).strip()
    return ""


def _label_of(obj: dict) -> str:
    value = _first(obj, NODE_LABEL_KEYS)
    if value not in (None, "") and not isinstance(value, (dict, list)):
        return clean_label(value)
    for nested in obj.values():
        if not isinstance(nested, dict):
            continue
        value = _first(nested, NODE_LABEL_KEYS)
        if value not in (None, "") and not isinstance(value, (dict, list)):
            return clean_label(value)
    return ""


def walk_json(root: Any, graph: Graph) -> None:
    """Find node-ish and edge-ish dicts anywhere in a JSON tree."""
    stack: list[Any] = [root]
    seen: set[int] = set()
    found_nodes = found_edges = 0

    while stack:
        cur = stack.pop()
        if isinstance(cur, list):
            stack.extend(reversed(cur))
            continue
        if not isinstance(cur, dict):
            continue
        if id(cur) in seen:
            continue
        seen.add(id(cur))

        frm = _first(cur, FROM_KEYS)
        to = _first(cur, TO_KEYS)
        # An edge must have both ends; a lone "source" key is often a node field.
        if frm not in (None, "") and to not in (None, ""):
            src, dst = _id_of(frm), _id_of(to)
            if src and dst:
                label = _label_of(cur)
                graph.add_edge(src, dst, label)
                found_edges += 1

        nid = _id_of(cur)
        label = _label_of(cur)
        if nid and (label or _first(cur, TYPE_KEYS) is not None):
            ntype = _first(cur, TYPE_KEYS)
            graph.add_node(
                nid,
                label,
                str(ntype) if isinstance(ntype, (str, int)) else None,
                str(ntype) if isinstance(ntype, str) else None,
            )
            found_nodes += 1

        # Explicit "next" links.
        nxt = _first(cur, NEXT_KEYS)
        if nid and nxt:
            items = nxt if isinstance(nxt, list) else [nxt]
            for item in items:
                dst = _id_of(item)
                if dst:
                    graph.add_edge(nid, dst)

        values = [value for value in cur.values() if isinstance(value, (list, dict))]
        stack.extend(reversed(values))

    if found_nodes == 0 and found_edges == 0:
        graph.warnings.append("JSON 中没有找到带 id/label 或 from/to 的对象。")
    elif found_nodes == 0:
        graph.warnings.append("JSON 中只找到边，没有找到节点标签。")


# ---------------------------------------------------------------------------
# XML / draw.io / SVG
# ---------------------------------------------------------------------------

def parse_xml(text: str, graph: Graph) -> None:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        graph.warnings.append(f"XML 解析失败: {exc}")
        return

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def geom_of(elem: Any) -> Any:
        for child in elem:
            if local(child.tag) == "mxGeometry":
                return child
        return None

    # Pass 1: collect vertex boxes so dangling edges can be recovered.
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for elem in root.iter():
        if local(elem.tag) != "mxCell" or elem.attrib.get("vertex") != "1":
            continue
        nid = elem.attrib.get("id") or ""
        geom = geom_of(elem)
        if not nid or geom is None:
            continue
        try:
            boxes[nid] = (
                float(geom.attrib.get("x", 0)),
                float(geom.attrib.get("y", 0)),
                float(geom.attrib.get("width", 0)),
                float(geom.attrib.get("height", 0)),
            )
        except ValueError:
            continue

    def owner_at(px: float, py: float) -> str | None:
        hits: list[tuple[int, float, str]] = []
        for nid, (x, y, w, h) in boxes.items():
            tol = 16
            if x - tol <= px <= x + w + tol and y - tol <= py <= y + h + tol:
                inside = 0 if x <= px <= x + w and y <= py <= y + h else 1
                hits.append((inside, abs(px - x), nid))
        return min(hits)[2] if hits else None

    def endpoint_point(elem: Any, kind: str) -> tuple[float, float] | None:
        geom = geom_of(elem)
        if geom is None:
            return None
        for child in geom:
            if local(child.tag) == "mxPoint" and child.attrib.get("as") == kind:
                try:
                    return float(child.attrib["x"]), float(child.attrib["y"])
                except (KeyError, ValueError):
                    return None
        return None

    # Pass 2: vertices and edges.
    for elem in root.iter():
        tag = local(elem.tag)
        if tag not in ("mxCell", "cell", "node", "vertex", "shape", "object", "edge"):
            continue
        attrs = elem.attrib
        nid = attrs.get("id") or attrs.get("nodeId") or ""
        is_edge = tag == "edge" or attrs.get("edge") == "1"

        if is_edge:
            src = attrs.get("source") or attrs.get("from") or attrs.get("start") or ""
            dst = attrs.get("target") or attrs.get("to") or attrs.get("end") or ""
            label = attrs.get("value") or attrs.get("label") or ""
            if not label:
                for child in elem:
                    if local(child.tag) == "mxCell" and child.attrib.get("value"):
                        label = child.attrib["value"]
                        break
            if src and not dst:
                point = endpoint_point(elem, "targetPoint")
                if point:
                    dst = owner_at(*point) or ""
                    if dst:
                        graph.warnings.append(
                            f"【推断】边 {nid} 缺少 target，按 targetPoint "
                            f"({point[0]:g},{point[1]:g}) 还原为 {src}→{dst}。")
            elif dst and not src:
                point = endpoint_point(elem, "sourcePoint")
                if point:
                    src = owner_at(*point) or ""
                    if src:
                        graph.warnings.append(
                            f"【推断】边 {nid} 缺少 source，按 sourcePoint "
                            f"({point[0]:g},{point[1]:g}) 还原为 {src}→{dst}。")
            graph.add_edge(src, dst, label)
            continue

        label = attrs.get("value") or attrs.get("label") or attrs.get("text") or ""
        if not label:
            texts = [c.text for c in elem.iter() if local(c.tag) == "text" and c.text]
            label = " ".join(t for t in texts if t)
        style = attrs.get("style", "")
        if not label and not style:
            # Root/container cells in draw.io have no text and no style.
            continue
        low_style = style.lower()
        low_label = label.lower()
        shape = ""
        if "decision" in low_style or "rhombus" in low_style or "diamond" in low_style:
            shape = "decision"
        elif "terminator" in low_style:
            shape = "end"
        elif "start" in low_style:
            shape = "start"
        elif "stored_data" in low_style or "cylinder" in low_style or "database" in low_style:
            shape = "database"
        elif "parallelogram" in low_style or "document" in low_style or "data" in low_style:
            shape = "io"
        elif "ellipse" in low_style:
            shape = "end" if any(w in low_label for w in ("end", "结束", "完成")) else "start"
        graph.add_node(nid, label, None, shape)

    if not graph.nodes:
        graph.warnings.append("XML 中没有找到 mxCell/cell/node/vertex 节点。")


# ---------------------------------------------------------------------------
# Mermaid
# ---------------------------------------------------------------------------

MERMAID_ID = r"[A-Za-z0-9_][A-Za-z0-9_-]*"
MERMAID_KEYWORDS = {
    "flowchart", "graph", "subgraph", "end", "style", "classdef", "class",
    "click", "linkstyle", "direction", "td", "tb", "lr", "rl", "bt",
}
NODE_DEF_RE = re.compile(
    r"(?<![\w-])(?P<id>" + MERMAID_ID + r")\s*"
    r"(?P<open>\(\[|\[\[|\[\(|\{\{|\(\(|\[|\(|\{|>)\s*"
    r"(?P<label>.*?)\s*"
    r"(?P<close>\)\]|\]\)|\]\]|\)\]|\}\)|\)|\]|\})"
)
PLAIN_ID_RE = re.compile(r"(?<![\w-])(" + MERMAID_ID + r")(?![\w-])")
EDGE_TOKEN_RE = re.compile(
    r"(?:"
    r"--\s*(?P<label1>[^->\n]+?)\s*-->"
    r"|(?P<op>-->|--x|--o|==>|-\.->|-\.-|---|===)"
    r")\s*(?:\|(?P<label2>[^|]*)\|)?"
)


def _parse_segment(segment: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    spans: list[tuple[int, int]] = []
    for match in NODE_DEF_RE.finditer(segment):
        nid = match.group("id")
        if nid.lower() in MERMAID_KEYWORDS:
            continue
        label = clean_label(match.group("label") or "")
        label = label.replace("\ue000", "{").replace("\ue001", "}")
        out.append((nid, label, match.group("open")))
        spans.append(match.span())

    remainder = list(segment)
    for start, end in spans:
        for i in range(start, end):
            remainder[i] = " "
    for match in PLAIN_ID_RE.finditer("".join(remainder)):
        nid = match.group(1)
        if nid.lower() in MERMAID_KEYWORDS:
            continue
        out.append((nid, "", ""))

    # Deduplicate by id inside one segment, keeping the first label/shape.
    deduped: dict[str, tuple[str, str, str]] = {}
    for nid, label, shape in out:
        if nid not in deduped or (not deduped[nid][1] and label):
            deduped[nid] = (nid, label, shape)
    return list(deduped.values())


def _split_mermaid_edges(line: str) -> tuple[list[str], list[str]]:
    segments: list[str] = []
    labels: list[str] = []
    pos = 0
    for match in EDGE_TOKEN_RE.finditer(line):
        segments.append(line[pos:match.start()])
        labels.append((match.group("label1") or match.group("label2") or "").strip())
        pos = match.end()
    segments.append(line[pos:])
    return segments, labels


def parse_mermaid(text: str, graph: Graph) -> None:
    text = re.sub(r"%%[^\n]*", "", text)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("flowchart", "graph", "subgraph", "end",
                            "style", "classDef", "class ", "click", "linkStyle",
                            "direction", "%%")):
            continue

        # Protect {TAG} braces so they are not mistaken for Mermaid shape closes.
        line = TAG_RE.sub(lambda m: "\ue000" + m.group(1) + "\ue001", line)
        segments, labels = _split_mermaid_edges(line)
        node_groups = [_parse_segment(segment) for segment in segments]
        for group in node_groups:
            for nid, label, shape in group:
                graph.add_node(nid, label, None, shape)
        for idx, label in enumerate(labels):
            left = node_groups[idx]
            right = node_groups[idx + 1] if idx + 1 < len(node_groups) else []
            if left and right:
                graph.add_edge(left[-1][0], right[0][0], label)

    if not graph.nodes:
        graph.warnings.append("Mermaid 解析后没有节点，检查是否是受支持的 flowchart 语法。")


# ---------------------------------------------------------------------------
# DOT
# ---------------------------------------------------------------------------

def parse_dot(text: str, graph: Graph) -> None:
    for match in re.finditer(
            r'"?(?P<a>[\w.-]+)"?\s*->\s*"?(?P<b>[\w.-]+)"?\s*(?:\[(?P<attrs>[^\]]*)\])?', text):
        attrs = match.group("attrs") or ""
        label = ""
        lm = re.search(r'label\s*=\s*"([^"]*)"', attrs)
        if lm:
            label = lm.group(1)
        graph.add_edge(match.group("a"), match.group("b"), label)
    for match in re.finditer(
            r'"?(?P<id>[\w.-]+)"?\s*\[(?P<attrs>[^\]]*)\]', text):
        attrs = match.group("attrs")
        label = ""
        lm = re.search(r'label\s*=\s*"([^"]*)"', attrs)
        if lm:
            label = lm.group(1)
        shape = ""
        sm = re.search(r'shape\s*=\s*"?(\w+)"?', attrs)
        if sm:
            shape = sm.group(1)
        graph.add_node(match.group("id"), label, None, shape)
    if not graph.nodes:
        graph.warnings.append("DOT 解析后没有节点。")


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _text_from_bytes(data: bytes) -> str | None:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            text = data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if text and sum(ch.isprintable() or ch.isspace() for ch in text[:2000]) / max(1, len(text[:2000])) > 0.9:
            return text
    return None


def _parse_text_payload(text: str, graph: Graph) -> bool:
    """Route a decoded text payload to the right parser. Returns True on success."""
    stripped = text.lstrip()
    lowered = stripped.lower()
    if lowered.startswith(("{", "[")):
        try:
            walk_json(json.loads(stripped), graph)
            graph.fmt = graph.fmt or "json"
            return True
        except json.JSONDecodeError:
            pass
    if lowered.startswith("<") or "mxfile" in lowered or "mxgraphmodel" in lowered:
        parse_xml(stripped, graph)
        graph.fmt = graph.fmt or "xml"
        return True
    if "digraph" in lowered:
        parse_dot(stripped, graph)
        graph.fmt = graph.fmt or "dot"
        return True
    if "flowchart" in lowered or re.search(r"-->|---|-\.->", stripped):
        parse_mermaid(stripped, graph)
        graph.fmt = graph.fmt or "mermaid"
        return True
    return False


def load(path: Path, graph: Graph) -> None:
    data = path.read_bytes()
    if not data:
        graph.warnings.append("文件为空。")
        return

    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
        graph.warnings.append("检测到 GZIP，已解压。")

    if data[:2] == b"PK" or zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            graph.warnings.append(f"ZIP 容器，条目: {', '.join(names[:12])}")
            for name in names:
                inner = zf.read(name)
                text = _text_from_bytes(inner)
                if text and _parse_text_payload(text, graph):
                    continue
                lowered = name.lower()
                if lowered.endswith((".json", ".ngm")):
                    try:
                        walk_json(json.loads(inner.decode("utf-8-sig")), graph)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        pass
                elif lowered.endswith((".mmd", ".mermaid", ".txt")):
                    if text:
                        parse_mermaid(text, graph)
            if not graph.nodes:
                graph.warnings.append("ZIP 内没有可识别的 JSON/XML/Mermaid 内容。")
        return

    text = _text_from_bytes(data)
    if text is None:
        graph.warnings.append("无法按文本解码（可能是私有二进制格式）。")
        _fallback_strings(data, graph)
        return

    stripped = text.lstrip()
    lowered = stripped.lower()
    if lowered.startswith(("{", "[")):
        try:
            walk_json(json.loads(text), graph)
            graph.fmt = "json"
            return
        except json.JSONDecodeError:
            pass
    if lowered.startswith("<"):
        parse_xml(text, graph)
        graph.fmt = "xml"
        return
    if "digraph" in lowered:
        parse_dot(text, graph)
        graph.fmt = "dot"
        return
    if "flowchart" in lowered or re.search(r"-->|---|-\.->", text):
        parse_mermaid(text, graph)
        graph.fmt = "mermaid"
        return

    # Last resort: look for JSON/XML embedded in a wrapper text.
    start = min([i for i in (stripped.find("{"), stripped.find("<")) if i >= 0], default=-1)
    if start >= 0:
        chunk = stripped[start:]
        try:
            walk_json(json.loads(chunk), graph)
            graph.fmt = "json"
            return
        except json.JSONDecodeError:
            pass
        parse_xml(chunk, graph)
        graph.fmt = "xml"
        return

    _fallback_strings(data, graph)
    graph.warnings.append("未识别出结构化图数据。")


def _fallback_strings(data: bytes, graph: Graph) -> None:
    """Recover printable runs so the agent at least sees candidate labels."""
    runs = re.findall(rb"[\x20-\x7e\x80-\xff]{4,}", data)
    labels: list[str] = []
    for run in runs:
        text = _text_from_bytes(run)
        if not text:
            continue
        text = text.strip()
        if not text or len(text) > 120:
            continue
        if text.lower().startswith(("http", "mozilla", "version", "utf-", "xml")):
            continue
        if text not in labels:
            labels.append(text)
    for i, label in enumerate(labels[:80], 1):
        graph.add_node(f"X{i}", label)
    if labels:
        graph.warnings.append(
            f"仅按字符串抽取了 {len(labels)} 条候选文本，未恢复连线；"
            "请导出 SVG/PNG 后重新 tokenize。")


# ---------------------------------------------------------------------------
# Analysis / output
# ---------------------------------------------------------------------------

def finalize(graph: Graph) -> None:
    if getattr(graph, "_finalized", False):
        return
    graph._finalized = True
    indeg = {nid: 0 for nid in graph.nodes}
    outdeg = {nid: 0 for nid in graph.nodes}
    for edge in graph.edges:
        outdeg[edge["from"]] = outdeg.get(edge["from"], 0) + 1
        indeg[edge["to"]] = indeg.get(edge["to"], 0) + 1

    for nid, node in graph.nodes.items():
        node["in"] = indeg.get(nid, 0)
        node["out"] = outdeg.get(nid, 0)
        if node["in"] == 0 and node["type"] not in ("start", "end"):
            node["type"] = "start"
        elif node["out"] == 0 and node["type"] not in ("start", "end"):
            node["type"] = "end"

    if not any(n["type"] == "start" for n in graph.nodes.values()) and graph.nodes:
        first = graph.order[0]
        graph.nodes[first]["type"] = "start"
        graph.warnings.append(f"没有入度为 0 的起点，暂用 {first} 作为 start【推断】。")
    if not any(n["type"] == "end" for n in graph.nodes.values()) and graph.nodes:
        graph.warnings.append("没有出度为 0 的终点，检查是否漏边。")


def to_payload(graph: Graph) -> dict[str, Any]:
    finalize(graph)
    return {
        "name": Path(graph.source).stem or "flow",
        "source": graph.source,
        "format": graph.fmt or "auto",
        "nodes": [graph.nodes[nid] for nid in graph.order if nid in graph.nodes],
        "edges": graph.edges,
        "warnings": graph.warnings,
    }


def to_mermaid(graph: Graph) -> str:
    finalize(graph)
    shape_open = {
        "start": "([", "end": "([", "decision": "{", "database": "[(",
        "io": "[/", "subprocess": "[[",
    }
    shape_close = {
        "start": "])", "end": "])", "decision": "}", "database": ")]",
        "io": "/]", "subprocess": "]]",
    }
    lines = ["flowchart TD"]
    for nid in graph.order:
        node = graph.nodes[nid]
        ntype = node["type"] if node["type"] in shape_open else "process"
        prefix = f"{{{node['directive']}}} " if node.get("directive") else ""
        label = (prefix + (node["label"] or nid)).replace('"', "'")
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
    for edge in graph.edges:
        if edge["label"]:
            lines.append(f'    {edge["from"]} -- "{edge["label"]}" --> {edge["to"]}')
        else:
            lines.append(f'    {edge["from"]} --> {edge["to"]}')
    return "\n".join(lines) + "\n"


def print_tables(payload: dict[str, Any]) -> None:
    nodes = payload["nodes"]
    edges = payload["edges"]
    print(f"source: {payload['source']}")
    print(f"format: {payload['format']}")
    print(f"nodes: {len(nodes)}  edges: {len(edges)}")
    print()
    print("| 节点ID | 功能头 | 标签 | 类型 | 入度 | 出度 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for node in nodes:
        label = node["label"].replace("|", "\\|")
        directive = node.get("directive", "")
        print(f"| {node['id']} | {directive} | {label} | {node['type']} | {node['in']} | {node['out']} |")
    print()
    print("| From | To | 条件/标签 | 边类型 |")
    print("| --- | --- | --- | --- |")
    for edge in edges:
        label = edge["label"].replace("|", "\\|")
        print(f"| {edge['from']} | {edge['to']} | {label} | {edge['kind']} |")
    if payload["warnings"]:
        print()
        print("warnings:")
        for warning in payload["warnings"]:
            print(f"- {warning}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Tokenize .ngm / diagrams into nodes and edges")
    parser.add_argument("source", help="input file")
    parser.add_argument("--json", action="store_true", help="emit normalized JSON")
    parser.add_argument("--mermaid", action="store_true", help="emit Mermaid")
    parser.add_argument("--out", help="write output to this path")
    parser.add_argument("--encoding", help="force text encoding")
    args = parser.parse_args(argv)

    path = Path(args.source)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    graph = Graph(str(path), path.suffix.lower().lstrip("."))
    load(path, graph)

    if not graph.nodes:
        print_tables({"source": str(path), "format": graph.fmt, "nodes": [], "edges": [],
                      "warnings": graph.warnings + [
                          "没有节点。请用坚果云绘图导出 SVG（推荐）、PNG 2x 或 PDF，"
                          "或把节点/连线清单直接贴给 agent。"]})
        return 1

    if args.mermaid:
        text = to_mermaid(graph)
    elif args.json:
        text = json.dumps(to_payload(graph), ensure_ascii=False, indent=2)
    else:
        print_tables(to_payload(graph))
        return 0

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
