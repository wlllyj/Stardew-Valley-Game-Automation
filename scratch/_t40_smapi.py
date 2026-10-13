"""task-40 B 补充：SMAPI 日志现场（判断 run3 证据是否已被 run4 覆盖）。只读。"""
import pathlib
import re

ERR = pathlib.Path(r"C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs")
print(f"ErrorLogs exists={ERR.exists()}")
if ERR.exists():
    for p in sorted(ERR.iterdir(), key=lambda x: x.stat().st_mtime):
        st = p.stat()
        print(f"  {p.name}: size={st.st_size} mtime={st.st_mtime}")

pat = re.compile(r"Synchronizing 'NewDay'|SaveGame\.Save\(\) completed|Context: after save|Starting SMAPI|SMAPI 4|Game Started|Disconnected|ClosedGame")
for p in sorted(ERR.glob("*"), key=lambda x: x.stat().st_mtime):
    if not p.is_file():
        continue
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"\n=== {p.name} 行数={len(lines)} ===")
    for i in (0, 1, 2, len(lines) - 2, len(lines) - 1):
        if 0 <= i < len(lines):
            print(f"  L{i+1}: {lines[i][:150]}")
    hits = [(i + 1, s) for i, s in enumerate(lines) if pat.search(s)]
    print(f"  关键行命中 {len(hits)}：")
    for n, s in hits[:30]:
        print(f"    L{n}: {s.strip()[:130]}")

# 仓库里有没有 run3 的 SMAPI 拷贝
repo = pathlib.Path(__file__).resolve().parents[1]
print("\n仓库 logs 目录里的 SMAPI 相关文件：")
for p in sorted((repo / "logs").glob("*smapi*"), key=lambda x: x.name.lower()):
    print(f"  {p.name}: size={p.stat().st_size}")
for p in sorted((repo / "logs").glob("*SMAPI*"), key=lambda x: x.name.lower()):
    print(f"  {p.name}: size={p.stat().st_size}")
