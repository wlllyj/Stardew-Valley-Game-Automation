"""跑 il-probe（Probe26.exe）并把 IL 落成 UTF-8 文本。

用法: python scratch\\_probe_il.py <输出文件> "Type|Method" ["Type|Method" ...]
只读：不碰游戏、桥、brain、mod。
"""
import os
import subprocess
import sys

GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"
PROBE = os.path.join("tools", "il-probe", "bin", "Release", "Probe26.exe")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out = sys.argv[1]
    targets = sys.argv[2:]
    proc = subprocess.run([PROBE, GAME] + targets, capture_output=True)
    raw = proc.stdout
    text = None
    for enc in ("utf-8", "utf-16-le"):
        try:
            cand = raw.decode(enc)
        except Exception:
            continue
        if "IL_" in cand:
            text = cand
            break
    if text is None:
        text = raw.decode("utf-8", "replace")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("stdout_bytes=%d lines=%d rc=%d" % (len(raw), text.count("\n"), proc.returncode))
    if proc.stderr:
        print("stderr:", proc.stderr.decode("utf-8", "replace")[:300])
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
