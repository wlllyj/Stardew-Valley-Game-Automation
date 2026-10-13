"""核对 --json 输出里 task-60 的机器可读字段（只读）。"""
import json

raw = open("scratch/_run5_json_after2.txt", "rb").read()
print("first bytes:", raw[:8])
if raw[:2] == b"\xff\xfe":
    txt = raw.decode("utf-16-le")
else:
    txt = raw.decode("utf-8-sig")
txt = txt.lstrip("\ufeff")
r = json.loads(txt)
days = r["days"]
print("days:", len(days))
hits = [d for d in days if d.get("no_work_with_dry")]
print("no_work_with_dry days:", len(hits))
for d in hits:
    print("  day=", d.get("day"), "justified=", d.get("day_justified"),
          "effective=", d.get("day_justified_effective"), "dry=", d.get("no_work_with_dry"),
          "ended=", str(d.get("ended_by")))
print("day keys sample:", sorted(days[0].keys()))
print("categories_total:", r.get("categories_total"))
print("manual_intervention total:", r.get("manual_intervention", {}).get("total"))
print("verified_days:", r.get("verified_days"), "/", r.get("days_requested"))
