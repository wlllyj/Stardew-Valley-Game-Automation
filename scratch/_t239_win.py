"""只读取证：打印 0.7.40 rescued SMAPI 窗口的六串行号与尾部，用于造红/绿夹具。

用法：python scratch/_t239_win.py [路径]
只读，不写任何文件（造夹具由 _t239_probe.py 的 fixtures() 做）。
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "logs/smoke-0740-smapi-window-rescued.txt"

KEYS = {
    "newday": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save.",
    "save_called": "SaveGame.Save() called",
    "save_task": "Synchronizing 'Save' task",
    "save_done": "SaveGame.Save() completed",
    "after_save": "Context: after save",
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    lines = open(PATH, encoding="utf-8", errors="replace").read().splitlines()
    print(f"path={PATH} lines={len(lines)}")
    idx = {k: [] for k in KEYS}
    for i, ln in enumerate(lines, 1):
        for k, s in KEYS.items():
            if s in ln:
                idx[k].append(i)
    for k in KEYS:
        print(f"{k:<12} n={len(idx[k])} lines={idx[k]}")
    for i, ln in enumerate(lines, 1):
        if "Synchronizing 'NewDay' task" in ln:
            print(f"--- NewDay @{i}")
            for j in range(max(1, i - 1), min(len(lines), i + 6) + 1):
                print(f"{j}: {lines[j-1][:160]}")
    print("=== last 26 lines ===")
    for j in range(max(1, len(lines) - 25), len(lines) + 1):
        print(f"{j}: {lines[j-1][:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
