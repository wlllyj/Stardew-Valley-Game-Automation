# -*- coding: utf-8 -*-
"""task-226 收尾取证：SMAPI 时点冻结（六串计数）+ 存档 XML `<craftingRecipes>` 前后对比（Furnace）。

before = `Wahaha_450799035_old`（fall 22 06:00 那份，事件前）
after  = `Wahaha_450799035`（fall 23 06:00 那份，事件后 + 睡一夜落盘）
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
SMAPI_SRC = Path(os.environ["APPDATA"]) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
SMAPI_DST = REPO / "logs" / "t226-smapi-window.txt"
REAL = re.compile(r"^\[(\d{2}:\d{2}:\d{2}) [A-Z]+ [^\]]+\]")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_smapi() -> dict:
    shutil.copyfile(SMAPI_SRC, SMAPI_DST)
    s_src, s_dst = sha(SMAPI_SRC), sha(SMAPI_DST)
    out = {
        "src": {"path": str(SMAPI_SRC), "size": SMAPI_SRC.stat().st_size,
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(SMAPI_SRC.stat().st_mtime))},
        "dst": {"path": str(SMAPI_DST), "size": SMAPI_DST.stat().st_size,
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(SMAPI_DST.stat().st_mtime))},
        "sha256_src": s_src, "sha256_dst": s_dst,
        "byte_identical": s_src == s_dst,
    }
    return out


def chains(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = {"lines": len(lines), "total": {}}
    for k in ("Synchronizing 'NewDay' task", "Context: before save.", "SaveGame.Save() called.",
              "Synchronizing 'Save' task", "completed without exceptions", "after save, starting"):
        hits = []
        for i, ln in enumerate(lines, 1):
            m = REAL.match(ln)
            if not m or " by AgentFarm " in ln or "| v0." in ln:
                continue
            if k in ln:
                hits.append({"line": i, "t": m.group(1), "text": ln[:150]})
        out["total"][k] = hits
    return out


def recipes(save_path: Path) -> dict:
    text = save_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<craftingRecipes>(.*?)</craftingRecipes>", text, re.S)
    if not m:
        return {"error": "no <craftingRecipes> block"}
    block = m.group(1)
    items = re.findall(r"<string>(.*?)</string>", block)
    offset = text[:m.start()].count("\n") + 1
    raw_lines = []
    for i, ln in enumerate(text.splitlines(), 1):
        if i < offset or i > offset + block.count("\n") + 2:
            continue
        if "string" in ln and ("Furnace" in ln or len(raw_lines) < 3):
            raw_lines.append({"line": i, "text": ln.strip()})
    st = save_path.stat()
    return {"path": str(save_path), "size": st.st_size,
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            "count": len(items), "items": items, "has_furnace": "Furnace" in items,
            "furnace_index_line": offset, "sample_lines": raw_lines}


def mail_bits(save_path: Path) -> dict:
    text = save_path.read_text(encoding="utf-8", errors="replace")
    out = {}
    m = re.search(r"<copperFound[^>]*/?>", text)
    out["copperFound_tag"] = m.group(0) if m else None
    out["mail_lines_with_copper"] = [{"line": i, "text": ln.strip()[:160]}
                                    for i, ln in enumerate(text.splitlines(), 1)
                                    if "copper" in ln.lower()][:12]
    for key in ("<mailReceived>", "<mailbox>", "<mailForTomorrow>"):
        m2 = re.search(re.escape(key) + r"(.*?)</" + key[1:], text, re.S)
        out[key] = bool(m2)
    st = save_path.stat()
    out["size"] = st.st_size
    return out


def main() -> int:
    res: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    res["smapi_frozen"] = freeze_smapi()
    res["chains"] = chains(SMAPI_DST)
    before = SAVE_DIR / "Wahaha_450799035_old"
    after = SAVE_DIR / "Wahaha_450799035"
    res["recipes_before"] = recipes(before)
    res["recipes_after"] = recipes(after)
    res["mail_after"] = mail_bits(after)
    res["save_four"] = {}
    for name in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
        p = SAVE_DIR / name
        st = p.stat()
        res["save_four"][name] = {"size": st.st_size,
                                  "at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
                                        + f".{int(st.st_mtime * 1000) % 1000:03d}"}
    print("=== SMAPI 冻结 ===")
    f = res["smapi_frozen"]
    print(f"  src {f['src']['size']} B / {f['src']['mtime']}  sha256={f['sha256_src']}")
    print(f"  dst {f['dst']['size']} B / {f['dst']['mtime']}  sha256={f['sha256_dst']}")
    print(f"  BYTE_IDENTICAL={f['byte_identical']}  总行数={res['chains']['lines']}")
    print("\n=== 六串（全文累计，含行号与时刻）===")
    for k, hits in res["chains"]["total"].items():
        print(f"  {k}: {len(hits)} 次 -> " + ", ".join(f"L{h['line']}@{h['t']}" for h in hits))
    print("\n=== 配方前后对比 ===")
    for tag in ("recipes_before", "recipes_after"):
        r = res[tag]
        print(f"  {tag}: {r['count']} 条 / has_Furnace={r['has_furnace']} / {r['size']} B / {r['mtime']}")
    print(f"  before 列表: {res['recipes_before']['items']}")
    print(f"  after  列表: {res['recipes_after']['items']}")
    print(f"  after 里 Furnace 的 XML 块起始行号: {res['recipes_after']['furnace_index_line']}")
    print("  after 抽样行:")
    for s in res["recipes_after"]["sample_lines"]:
        print(f"    L{s['line']}: {s['text']}")
    print("\n=== copperFound 相关 ===")
    print(f"  tag: {res['mail_after']['copperFound_tag']}")
    for l in res["mail_after"]["mail_lines_with_copper"]:
        print(f"    L{l['line']}: {l['text']}")
    (REPO / "scratch" / "t226-receipts.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写 scratch/t226-receipts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
