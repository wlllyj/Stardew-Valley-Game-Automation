# -*- coding: utf-8 -*-
"""把 il-probe（tools\\il-probe\\bin\\Release\\Probe26.exe）的 stdout 存成 **UTF-8** 文件。

【为什么需要它】直接用 PowerShell 重定向（`>` / `Out-File`）会写出 UTF-16LE（首字节 FF FE），
于是 `read`/`grep` 会把转储当二进制 —— 项目里踩过（见 docs/_il-farmer-halt.md 的说明）。
在 Python 里 `subprocess` 抓字节再显式写 UTF-8，可以一次绕开 BOM/编码问题。

用法：
    python scratch/run_il_probe.py <输出文件> "Type|Method" ["Type|Method" ...]
"""
import pathlib
import subprocess
import sys

GAME_DIR = r"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"
EXE = pathlib.Path(r"D:\Deepseek Harness Workspace\星露谷游戏自动化\tools\il-probe\bin\Release\Probe26.exe")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out = pathlib.Path(sys.argv[1])
    targets = sys.argv[2:]
    proc = subprocess.run([str(EXE), GAME_DIR, *targets],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = proc.stdout
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
        enc = "utf-16"
    else:
        try:
            text = raw.decode("utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            text = raw.decode("utf-16", errors="replace")
            enc = "utf-16(replace)"
    out.write_text(text, encoding="utf-8")
    print(f"{out}  chars={len(text)}  child_encoding={enc}  first_bytes={raw[:4]!r}  exit={proc.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
