"""Writes src/code.json: this film's own source, for its last shot."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
lines = []
for name in ("ui.tsx", "scenes.tsx"):
    for line in (HERE / "src" / name).read_text(encoding="utf-8").splitlines():
        if line.strip() and len(line) < 95:
            lines.append(line.rstrip())
(HERE / "src" / "code.json").write_text(json.dumps(lines[:260], ensure_ascii=False), encoding="utf-8")
print(len(lines), "lines")
