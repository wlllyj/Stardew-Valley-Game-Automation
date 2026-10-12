import json, sys

path = sys.argv[1]
s = open(path, encoding="utf-8", errors="replace").read()
i = s.find('{"tasks"')
d = json.loads(s[i:s.rfind("}") + 1])
for t in d["tasks"]:
    print("%-8s %-11s owner=%-13s ready=%-5s blocked=%s" % (
        t["id"], t["status"], t.get("ownerName"), t["ready"], t["blockedBy"]))
