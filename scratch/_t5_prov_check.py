# -*- coding: utf-8 -*-
"""T5.3 three-way provenance: repo source / build output / installed."""
import hashlib
import json
import pathlib

repo = pathlib.Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
inst = pathlib.Path(r"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Mods\AgentFarm.Bridge")


def sha(p):
    b = p.read_bytes()
    return len(b), hashlib.sha256(b).hexdigest().upper()


def ver(p):
    if not p.exists():
        return "(missing)"
    try:
        return json.loads(p.read_bytes().decode("utf-8-sig")).get("Version")
    except Exception as exc:  # noqa: BLE001
        return f"(err {exc})"


for tag, d in [
    ("REPO_source ", repo / "mod" / "AgentFarm.Bridge"),
    ("BUILD_release", repo / "mod" / "AgentFarm.Bridge" / "bin" / "Release"),
    ("INSTALLED   ", inst),
]:
    m = d / "manifest.json"
    dll = d / "AgentFarm.Bridge.dll"
    if m.exists():
        n, h = sha(m)
        print(tag, "manifest", n, h, "Version=", ver(m))
    else:
        print(tag, "manifest MISSING", m)
    if dll.exists():
        n, h = sha(dll)
        import datetime
        mt = datetime.datetime.fromtimestamp(dll.stat().st_mtime).isoformat(timespec="seconds")
        print(tag, "dll     ", n, h, "mtime=", mt)
    else:
        print(tag, "dll MISSING", dll)

# frozen tree blob hashes
import subprocess
for ref in ["e2b69d9", "a03a564"]:
    out = subprocess.run(["git", "-C", str(repo), "archive", ref, "mod/AgentFarm.Bridge/manifest.json",
                          "brain/agentfarm/bridge.py", "brain/agentfarm/longrun.py", "tools/analyze-longrun.py",
                          "tools/verify-run3.py", "tools/deploy-mod.py"],
                         capture_output=True)
    print("FROZEN", ref, "archive_bytes=", len(out.stdout), "rc=", out.returncode)
for ref in ["e2b69d9", "a03a564"]:
    for f in ["mod/AgentFarm.Bridge/manifest.json", "brain/agentfarm/longrun.py", "brain/agentfarm/bridge.py",
              "tools/analyze-longrun.py", "tools/verify-run3.py", "tools/deploy-mod.py"]:
        b = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{f}"], capture_output=True).stdout
        print("BLOB", ref, f, len(b), hashlib.sha256(b).hexdigest().upper())
