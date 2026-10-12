import json, sys

path = sys.argv[1]
ids = set(sys.argv[2].split(","))
s = open(path, encoding="utf-8", errors="replace").read()
i = s.find('{"tasks"')
d = json.loads(s[i:s.rfind("}") + 1])
for t in d["tasks"]:
    if t["id"] in ids:
        print("=" * 70)
        print(t["id"], t["status"], "owner=", t.get("ownerName"), "ready=", t["ready"], "blocked=", t["blockedBy"])
        print("subj:", t["subject"])
        print("scopes:", t["writeScopes"])
        print(t["description"][:2200])
