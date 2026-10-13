import json, io
p = r"scratch\obs-farmhouse-spring11.json"
d = json.load(io.open(p, encoding="utf-8"))
print("TOP:", list(d.keys()))
loc = d.get("location", {})
print("LOC KEYS:", list(loc.keys()))
for k, v in loc.items():
    if isinstance(v, (list, dict)):
        print(" ", k, type(v).__name__, len(v))
    else:
        print(" ", k, "=", repr(v)[:120])
pl = d.get("player", {})
print("PLAYER:", json.dumps(pl, ensure_ascii=False)[:400])
