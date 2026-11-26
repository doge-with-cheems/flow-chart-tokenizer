"""Negative tests for the precision gates. Run: python tests/test_precision.py"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "references" / "example-logic.md"
TMP = ROOT / "tests" / "_tmp_precision"
TMP.mkdir(exist_ok=True)
CHECK = ROOT / "scripts" / "logic_check.py"


def run(name: str, text: str, *extra: str) -> tuple[int, str]:
    path = TMP / name
    path.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(CHECK), str(path), *extra],
        capture_output=True, text=True, encoding="utf-8",
    )
    return result.returncode, result.stdout


base = BASE.read_text(encoding="utf-8")

# 1. Missing §0.1 in strict mode -> FAIL
text = base.replace("### 0.1 需求确认", "### 0.1 已删除")
rc, out = run("missing-intake.logic.md", text)
assert rc == 1 and "需求确认" in out, out

# 2. Pending REQ but a step is already checked -> FAIL
text = base.replace("| 已确认 | 用户 2026-11-26 |", "| 待确认 | 用户 2026-11-26 |", 1)
text = text.replace("- [ ] S1 ·", "- [x] S1 ·", 1)
rc, out = run("pending-req.logic.md", text)
assert rc == 1 and "未确认但已有步骤勾选" in out, out

# 3. Change in progress but affected step still [x] -> FAIL
text = base.replace("| 已关闭 | §0.2 非目标 |", "| 进行中 | — |", 1)
text = text.replace("- [ ] S9 ·", "- [x] S9 ·", 1)
rc, out = run("change-conflict.logic.md", text)
assert rc == 1 and "变更/状态冲突" in out, out

# 4. Node table missing a row -> FAIL
text = base.replace("| N12 |", "| N12-removed |", 1)
rc, out = run("node-table.logic.md", text)
assert rc == 1 and "节点表" in out, out

# 5. End step with next -> FAIL
text = base.replace(
    "- 结果: 任务完成，进程继续驻留",
    "- 结果: 任务完成，进程继续驻留\n- 下一步: S10",
    1,
)
rc, out = run("end-next.logic.md", text)
assert rc == 1 and "结束步骤" in out, out

# 6. --mermaid must bubble up FAIL
rc, out = run("mermaid-fail.logic.md", base.replace("### 0.1 需求确认", "### 0.1 已删除"), "--mermaid")
assert rc == 1, out

# 7. Clean baseline still passes
rc, out = run("baseline.logic.md", base)
assert rc == 0 and "FAIL 0" in out, out

for item in TMP.iterdir():
    item.unlink()
TMP.rmdir()
print("PRECISION TESTS OK")
