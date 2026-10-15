# task-88 只读核对：按天统计"红 / 历史问题 / 已结清"，并核对窗口切换不丢条数。
# 用法: python scratch\_t88_check.py <analyze --json 输出文件> [<原始账本>]
import json
import sys


def day_bounds(path):
    """按 day_start 切天：返回 [(label, start_line, stop_line)]。"""
    bounds = []
    with open(path, encoding="utf-8") as fp:
        for i, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("event") == "day_start":
                day = ev.get("day") or []
                label = (f"{day[0]}年 {day[1]} {day[2]}日"
                         if isinstance(day, list) and len(day) == 2 else str(day))
                bounds.append([label, i, None])
    for i, b in enumerate(bounds):
        if i + 1 < len(bounds):
            b[2] = bounds[i + 1][1] - 1
    return bounds


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "scratch/_t88_w3.json"
    ledger = sys.argv[2] if len(sys.argv) > 2 else "logs/longrun-3day-llm-run7.jsonl"
    with open(path, encoding="utf-8-sig") as fp:
        data = json.load(fp)
    red, hist, settled = data["red"], data["history_problems"], data["settled"]
    print(f"窗口={data['window']}")
    print(f"红 {red['total']} 条 | 历史问题 {hist['total']} 条 | 已结清 {settled['total']} 条")
    print(f"红 subject: {red['subjects']}")
    print(f"历史 subject: {hist['subjects']}")
    print(f"已结清 subject: {settled['subjects']}")
    for label, start, stop in day_bounds(ledger):
        stop = stop or 10 ** 9
        r = sum(1 for ln in red.get("lines", []) if start <= ln <= stop)
        h = sum(1 for it in hist.get("items", []) if start <= (it.get("line") or -1) <= stop)
        s = sum(1 for it in settled.get("items", []) if start <= (it.get("line") or -1) <= stop)
        print(f"  - {label} L{start}..{stop if stop != 10 ** 9 else 'EOF'}: "
              f"红行 {r} | 历史 {h} | 已结清 {s}")
    print("--- 建议 ---")
    for item in data.get("advice", []):
        print("  - " + str(item.get("text"))[:200])


if __name__ == "__main__":
    main()
