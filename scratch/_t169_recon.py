"""task-169 只读 recon：把 run A 账本里与 harvest 有关的记录、以及带坐标的失败记录拉平。

用法：python scratch\\_t169_recon.py [journal]
默认 logs\\longrun-runA-0732.jsonl
输出 UTF-8 到 stdout（本脚本自己写文件时也用 UTF-8）。
"""
import collections
import io
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else r"logs\longrun-runA-0732.jsonl"
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    print("== 行数", len(rows))
    print("== 事件计数", json.dumps(dict(collections.Counter(r.get("event") for r in rows)),
                                ensure_ascii=False, sort_keys=True))

    print("\n== 含 harvest 字样的行（除 outcome 外）")
    for i, r in enumerate(rows, 1):
        ev = r.get("event")
        if ev == "outcome":
            continue
        s = json.dumps(r, ensure_ascii=False)
        if "harvest" in s:
            print(i, s[:700])

    print("\n== outcome(kind=harvest) 计数/分布")
    outs = [(i, r) for i, r in enumerate(rows, 1)
            if r.get("event") == "outcome" and r.get("kind") == "harvest"]
    print("共", len(outs), "条")
    print("terminal:", collections.Counter(r.get("terminal") for _, r in outs))
    print("postcondition_met:", collections.Counter(r.get("postcondition_met") for _, r in outs))
    print("提前停:", collections.Counter(
        (r.get("reason") or "").split("提前停：")[-1][:40] for _, r in outs))
    print("detail 非空:", sum(1 for _, r in outs if r.get("detail")))
    for i, r in outs[:5]:
        print(" ", i, json.dumps(r, ensure_ascii=False)[:400])

    print("\n== day_end 列表（day / ended_by / verified / failed_steps / stages 里的 harvest）")
    for i, r in enumerate(rows, 1):
        if r.get("event") != "day_end":
            continue
        stages = r.get("stages") or []
        hv = [s for s in stages if "harvest" in json.dumps(s, ensure_ascii=False)]
        print(i, "day=", r.get("day"), "ended_by=", r.get("ended_by"),
              "verified=", r.get("verified"), "failed=", r.get("failed_steps"),
              "ok=", r.get("ok_steps"), "skipped=", r.get("skipped_steps"))
        for s in hv:
            print("    stage:", json.dumps(s, ensure_ascii=False)[:400])
        for k in ("assigned_undone", "stamina_budget", "plot_pending"):
            if k in r:
                print("   ", k, "=", json.dumps(r[k], ensure_ascii=False)[:300])

    print("\n== 带 tile 的失败类事件（前 60 条）")
    n = 0
    for i, r in enumerate(rows, 1):
        if r.get("event") in ("blocked", "unreachable", "tool_refused", "tile_step", "sow_step", "till_step"):
            print(i, json.dumps(r, ensure_ascii=False)[:400])
            n += 1
            if n >= 60:
                break
    print("共打印", n, "条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
