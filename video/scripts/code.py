"""Writes src/code.json: this film's own source, for its last shot."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FILES = ("Film3D.tsx", "three/Speaky3D.tsx", "three/World.tsx", "three/Key3D.tsx", "three/Galaxy.tsx")
lines = []
for name in FILES:
    for line in (HERE / "src" / name).read_text(encoding="utf-8").splitlines():
        if line.strip() and len(line) < 95:
            lines.append(line.rstrip())
(HERE / "src" / "code.json").write_text(json.dumps(lines[:260], ensure_ascii=False), encoding="utf-8")
print(len(lines), "lines")
