import importlib.util, json, os
spec = importlib.util.spec_from_file_location("vr", "tools/verify-run3.py")
VR = importlib.util.module_from_spec(spec); spec.loader.exec_module(VR)
p = "scratch/_t159_j/tool_forged_green.jsonl"
rows = VR.load(p)
days = VR.build_days(rows)
ok, s = VR.report(days, target_days=1)
print("ok=", ok)
print("verdict=", s.get("verdict"), "strict=", s.get("strict_verdict"))
print("problems=", s.get("problems"))
print("infos=", (s.get("infos") or [])[:6])
for d in days:
    print("day", d.get("key"), "verified=", (d.get("end") or {}).get("verified"),
          "ended_by=", (d.get("end") or {}).get("ended_by"),
          "final_water=", (d.get("end") or {}).get("final_water"),
          "checks=", (d.get("end") or {}).get("checks"))
    print("  events:", sorted({r.get("event") for r in d.get("rows", [])}))
print("---- 真账本（未篡改）----")
rows2 = VR.load("scratch/_t159_j/b1_blocked.jsonl")
ok2, s2 = VR.report(VR.build_days(rows2), target_days=1)
print("ok=", ok2, "problems=", s2.get("problems"))
print("---- 同时篡改 finish.code=0 ----")
rows3 = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
for e in rows3:
    if e.get("event") == "finish":
        e["code"] = 0; e["verified_streak"] = 1; e["days"] = 1
f3 = "scratch/_t159_j/tool_forged_green_finish.jsonl"
open(f3, "w", encoding="utf-8").write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in rows3))
ok3, s3 = VR.report(VR.build_days(VR.load(f3)), target_days=1)
print("ok=", ok3, "verdict=", s3.get("verdict"), "problems=", s3.get("problems"), "infos=", len(s3.get("infos") or []))
