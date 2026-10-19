# -*- coding: utf-8 -*-
"""A9-start 备份完整性独立校验（只读）。

逐件对 logs/ab-backup/A9-start/ 的四件算 size/mtime/SHA256，与 manifest.json 内记录比对。
不写任何东西（除 stdout）。
"""
from __future__ import annotations

import hashlib
import json
import os
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BDIR = os.path.join(ROOT, "logs", "ab-backup", "A9-start")
MANIFEST = os.path.join(BDIR, "manifest.json")
FILES = ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        man = json.load(fh)
    print("=== manifest.json 头部 ===")
    for k in ("arm", "kind", "created_at", "save_dir", "backup_dir", "game_running_at_backup"):
        print(f"  {k}: {man.get(k)}")
    mst = os.stat(MANIFEST)
    print(f"  manifest.json 自身: size={mst.st_size} mtime={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mst.st_mtime))} sha256={sha256_file(MANIFEST)}")

    print("\n=== 逐件比对（备份实际 vs manifest 记录）===")
    allok = True
    for name in FILES:
        p = os.path.join(BDIR, name)
        rec = man.get("files", {}).get(name)
        if not os.path.exists(p):
            print(f"  {name:24} MISSING on disk  rec={rec}")
            allok = False
            continue
        st = os.stat(p)
        act = {"size": st.st_size,
               "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
               "mtime_epoch": round(st.st_mtime, 6),
               "sha256": sha256_file(p)}
        if rec is None:
            print(f"  {name:24} rec=MISSING in manifest; actual size={act['size']} sha={act['sha256'][:16]}…")
            allok = False
            continue
        size_ok = rec.get("size") == act["size"]
        sha_ok = rec.get("sha256") == act["sha256"]
        mt_ok = (rec.get("mtime") == act["mtime"]) and (abs(float(rec.get("mtime_epoch", 0)) - act["mtime_epoch"]) < 0.01)
        verdict = "OK" if (size_ok and sha_ok and mt_ok) else "MISMATCH"
        if verdict != "OK":
            allok = False
        print(f"  {name:24} {act['size']:>10} B  {act['mtime']}  {act['sha256'][:16]}…  "
              f"size={'OK' if size_ok else 'X'} mtime={'OK' if mt_ok else 'X'} sha256={'OK' if sha_ok else 'X'}  => {verdict}")
    print(f"\nVERDICT: {'ALL-4 OK（四件 size/mtime/SHA256 均与 manifest 一致）' if allok else 'INCONSISTENT（见上）'}")
    return 0 if allok else 3


if __name__ == "__main__":
    raise SystemExit(main())
