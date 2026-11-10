#!/usr/bin/env python3
"""功能头指令目录（single source of truth）。

逻辑 MD 和 tokenizer 共用这一份定义，避免两个脚本对同一个标记理解不一致。
"""

from __future__ import annotations

import re
from typing import Iterable

# tag -> metadata
DIRECTIVES: dict[str, dict[str, str]] = {
    "START": {
        "label": "开始", "category": "control", "node_type": "start",
        "desc": "流程入口/触发点",
    },
    "END": {
        "label": "结束", "category": "control", "node_type": "end",
        "desc": "流程终点",
    },
    "PREPARE": {
        "label": "预备", "category": "runtime", "node_type": "process",
        "desc": "初始化、安装依赖、准备目录/配置",
    },
    "CARD": {
        "label": "卡片", "category": "io", "node_type": "io",
        "desc": "界面卡片或可独立展示的 UI 单元",
    },
    "DB": {
        "label": "数据库", "category": "data", "node_type": "database",
        "desc": "数据库、schema、表结构",
    },
    "STORGE": {
        "label": "储存", "category": "data", "node_type": "database",
        "desc": "持久化写入/保存",
    },
    "DATA": {
        "label": "数据", "category": "data", "node_type": "process",
        "desc": "数据契约、结构、字段转换",
    },
    "DELAY": {
        "label": "延迟", "category": "runtime", "node_type": "process",
        "desc": "等待、超时、节流、sleep",
    },
    "DQ": {
        "label": "判断", "category": "control", "node_type": "decision",
        "desc": "条件判断，至少两条出边",
    },
    "PRINT": {
        "label": "显示", "category": "io", "node_type": "io",
        "desc": "显示、渲染、打印、输出到用户可见位置",
    },
    "FILE": {
        "label": "文档", "category": "io", "node_type": "io",
        "desc": "单个文件/文档的读写",
    },
    "MFL": {
        "label": "多文档", "category": "io", "node_type": "io",
        "desc": "批量文件、目录、多文档处理",
    },
    "MSE": {
        "label": "测量", "category": "runtime", "node_type": "process",
        "desc": "度量、断言、基准测试、阈值检查",
    },
    "LOOP": {
        "label": "循环", "category": "control", "node_type": "process",
        "desc": "循环体或回边入口，必须配退出条件",
    },
    "LPAR": {
        "label": "循环限制", "category": "control", "node_type": "process",
        "desc": "循环上限/重试次数参数",
    },
    "INPUT": {
        "label": "手动输入", "category": "io", "node_type": "io",
        "desc": "需要人输入内容",
    },
    "CTIHD": {
        "label": "手动操作", "category": "io", "node_type": "io",
        "desc": "需要人点击/按键/拖拽/确认",
    },
    "SUM": {
        "label": "求和", "category": "data", "node_type": "process",
        "desc": "求和、计数、聚合",
    },
    "TRANSMUTE": {
        "label": "传输", "category": "io", "node_type": "io",
        "desc": "网络请求、队列、上传下载、跨进程传递",
    },
    "LINEAR": {
        "label": "排序", "category": "data", "node_type": "process",
        "desc": "排序、线性化、按序输出",
    },
    "OR": {
        "label": "或", "category": "control", "node_type": "decision",
        "desc": "多选一分支，每个分支要有标签",
    },
    # ------------------------------------------------------------------
    # UML 扩展
    # ------------------------------------------------------------------
    "CLASS": {
        "label": "类", "category": "uml", "node_type": "class",
        "desc": "UML 类：属性、操作、关系",
    },
    "IFACE": {
        "label": "接口", "category": "uml", "node_type": "interface",
        "desc": "UML 接口/协议",
    },
    "ENUM": {
        "label": "枚举", "category": "uml", "node_type": "enum",
        "desc": "UML 枚举/常量集合",
    },
    "ACTOR": {
        "label": "参与者", "category": "uml", "node_type": "actor",
        "desc": "用例图参与者/外部角色",
    },
    "USECASE": {
        "label": "用例", "category": "uml", "node_type": "usecase",
        "desc": "用例图功能单元",
    },
    "COMPONENT": {
        "label": "组件", "category": "uml", "node_type": "component",
        "desc": "组件图构件/模块",
    },
    "SERVICE": {
        "label": "服务", "category": "uml", "node_type": "component",
        "desc": "可独立部署的服务",
    },
    "STATE": {
        "label": "状态", "category": "uml", "node_type": "state",
        "desc": "状态机状态",
    },
    "ENTITY": {
        "label": "实体", "category": "uml", "node_type": "entity",
        "desc": "ER 实体/领域实体",
    },
    "MESSAGE": {
        "label": "消息", "category": "uml", "node_type": "process",
        "desc": "时序图消息",
    },
    "RELATION": {
        "label": "关系", "category": "uml", "node_type": "process",
        "desc": "类/ER 关系",
    },
    "TRANSITION": {
        "label": "迁移", "category": "uml", "node_type": "process",
        "desc": "状态迁移",
    },
    "TABLE": {
        "label": "数据表", "category": "uml", "node_type": "database",
        "desc": "ER 实体落库表",
    },
    "API": {
        "label": "接口端点", "category": "uml", "node_type": "io",
        "desc": "对外 API 端点",
    },
    "REPO": {
        "label": "仓储", "category": "uml", "node_type": "database",
        "desc": "数据访问/仓储层",
    },
}

ALIASES = {
    "STORAGE": "STORGE",   # 倡议书里的 STORGE 是常用拼写，同时接受 STORAGE
}

# 一个节点有多个功能头时，按这个优先级决定图形类型。
TYPE_PRIORITY = (
    "END", "START", "DQ", "OR", "LOOP", "LPAR",
    "CLASS", "IFACE", "ENUM", "ACTOR", "USECASE", "COMPONENT", "SERVICE",
    "STATE", "ENTITY",
    "DB", "STORGE", "TABLE", "REPO", "PRINT", "API",
    "INPUT", "CTIHD", "FILE", "MFL", "TRANSMUTE",
    "CARD", "DATA", "DELAY", "MSE", "SUM", "LINEAR", "PREPARE",
    "MESSAGE", "RELATION", "TRANSITION",
)

TAG_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")


def canonical(tag: str) -> str:
    value = (tag or "").strip().upper()
    return ALIASES.get(value, value)


def is_known(tag: str) -> bool:
    return canonical(tag) in DIRECTIVES


def scan_tags(text: str) -> tuple[str, list[str], list[str]]:
    """Return (text without known tags, known tags, unknown UPPER tags)."""
    known: list[str] = []
    unknown: list[str] = []

    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        tag = canonical(raw)
        if tag in DIRECTIVES:
            if tag not in known:
                known.append(tag)
            return " "
        if raw == raw.upper() and len(raw) >= 2:
            if raw not in unknown:
                unknown.append(raw)
        return match.group(0)

    clean = TAG_RE.sub(replace, text or "")
    clean = re.sub(r"[ \t]+", " ", clean).strip()
    return clean, known, unknown


def type_for(tags: Iterable[str]) -> str | None:
    values = {canonical(tag) for tag in tags}
    for tag in TYPE_PRIORITY:
        if tag in values:
            return DIRECTIVES[tag]["node_type"]
    return None


def describe(tag: str) -> str:
    meta = DIRECTIVES.get(canonical(tag))
    if not meta:
        return ""
    return f"{canonical(tag)} = {meta['label']}（{meta['desc']}）"
