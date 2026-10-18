# -*- coding: utf-8 -*-
"""A7/B7「同起点协议」的存档备份 / 恢复 / 核对助手（task-113 rev17 起协议，Lead m04395 指派）。

同起点协议要点：A7 起跑前把存档目录**整份四件**备份成一个" referencia"；A7 跑完、优雅退游戏后把四件
**逐字节还原**，核对 SHA256 与备份完全一致，再起 B7。唯一允许的差异是教训库（B 带 A 的 lessons）。

本工具只做三件事，**不碰世界、不 load_save、不调桥**：
  backup  —— 存档目录四件 → `logs/ab-backup/<arm>-start/`，逐件记 size/mtime/SHA256 写 `manifest.json`
  restore —— 把备份四件拷回存档目录，拷完逐件核对 SHA256（不一致 ⇒ 非零退出并打印差在哪）
  verify  —— 只核对不写（当前存档目录 vs manifest）

三道安全闸：
  1) 游戏在跑（`%APPDATA%\\StardewValley\\AgentFarm\\bridge.json` 存在）时**默认拒绝** backup/restore
     （跑中途存档会变、备份会失真；要强行加 `--force`）；
  2) `backup` 默认**拒绝覆盖**已存在的备份目录（参考副本不能被第二次备份冲掉；要覆盖加 `--force`）；
  3) `restore` 先校验备份自身完整（四件齐全 + SHA256 == manifest）才开始拷，拷完再校验一遍。

退出码：0 成功 / 2 输入缺失或用法错 / 3 核对不一致 / 4 被安全闸拦下（游戏在跑/备份已存在）
用法：
  python scratch\\arm-start-helper.py backup  --arm A7
  python scratch\\arm-start-helper.py verify  --arm A7
  python scratch\\arm-start-helper.py restore --arm A7
  python scratch\\arm-start-helper.py --selftest          # 全程用临时目录，不碰真存档
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
SAVE_DIR = os.path.join(APPDATA, "StardewValley", "Saves", "Wahaha_450799035")
BRIDGE_JSON = os.path.join(APPDATA, "StardewValley", "AgentFarm", "bridge.json")
BACKUP_ROOT = os.path.join(ROOT, "logs", "ab-backup")
FILES = ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def stat_one(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    st = os.stat(path)
    return {"size": st.st_size,
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            "mtime_epoch": round(st.st_mtime, 6),
            "sha256": sha256_file(path)}


def snapshot(save_dir: str) -> dict:
    out: dict = {}
    for name in FILES:
        out[name] = stat_one(os.path.join(save_dir, name))
    return out


def game_running() -> bool:
    return os.path.exists(BRIDGE_JSON)


def fmt_table(label: str, snap: dict, ref: dict | None = None) -> tuple[bool, list[str]]:
    ok = True
    lines = [label]
    for name in FILES:
        cur = snap.get(name)
        if cur is None:
            lines.append(f"  {name:22} MISSING")
            ok = False
            continue
        line = f"  {name:22} {cur['size']:>10} B  {cur['mtime']}  {cur['sha256'][:16]}…"
        if ref is not None:
            r = ref.get(name)
            if r is None:
                line += "  ← 备份里没有"
                ok = False
            elif r["sha256"] != cur["sha256"] or r["size"] != cur["size"]:
                line += f"  ← MISMATCH（备份 {r['size']} B {r['sha256'][:16]}…）"
                ok = False
            else:
                line += "  OK"
        lines.append(line)
    return ok, lines


def cmd_backup(args) -> int:
    if game_running() and not args.force:
        print(f"!! 游戏在跑（{BRIDGE_JSON} 存在）⇒ 拒绝备份（跑中途存档会变）。确认要备就加 --force。")
        return 4
    if not os.path.isdir(args.save_dir):
        print(f"!! 存档目录不存在：{args.save_dir}")
        return 2
    dest = os.path.join(args.backup_root, f"{args.arm}-start")
    if os.path.exists(os.path.join(dest, "manifest.json")) and not args.force:
        print(f"!! 备份已存在（{dest}）⇒ 拒绝覆盖（参考副本不能被冲掉）。要覆盖加 --force。")
        return 4
    os.makedirs(dest, exist_ok=True)
    snap = snapshot(args.save_dir)
    ok, lines = fmt_table("=== 备份源（存档目录）===", snap)
    print("\n".join(lines))
    for name in FILES:
        src = os.path.join(args.save_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, name))
    # 拷完用副本自己的字节重算，确认拷过去的是同一份
    manifest = {"arm": args.arm, "kind": "ab-start", "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "save_dir": args.save_dir, "backup_dir": dest, "game_running_at_backup": game_running(),
                "files": {}}
    bad = []
    for name in FILES:
        b = os.path.join(dest, name)
        if not os.path.exists(b):
            manifest["files"][name] = None
            continue
        got = stat_one(b)
        manifest["files"][name] = got
        src_snap = snap.get(name)
        if src_snap is None or got is None or got["sha256"] != src_snap["sha256"]:
            bad.append(name)
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print(f"\n备份已写：{dest}（manifest.json 已记四件 size/mtime/SHA256）")
    if bad:
        print(f"!! 备份后校验不一致：{bad}")
        return 3
    missing = [n for n in FILES if manifest["files"].get(n) is None]
    if missing:
        print(f"⚠ 存档里本就没有这几件（如实记录，不算错）：{missing}")
    return 0


def _load_manifest(args) -> tuple[dict | None, int]:
    dest = os.path.join(args.backup_root, f"{args.arm}-start")
    mp = os.path.join(dest, "manifest.json")
    if not os.path.exists(mp):
        print(f"!! 备份 manifest 不存在：{mp}")
        return None, 2
    with open(mp, "r", encoding="utf-8") as fh:
        return json.load(fh), 0


def cmd_verify(args) -> int:
    manifest, rc = _load_manifest(args)
    if manifest is None:
        return rc
    if not os.path.isdir(args.save_dir):
        print(f"!! 存档目录不存在：{args.save_dir}")
        return 2
    # 备份自身的完整性
    bdir = os.path.join(args.backup_root, f"{args.arm}-start")
    ok_b, lines_b = fmt_table(f"=== 备份（{bdir}）自身完整性 ===",
                              {n: stat_one(os.path.join(bdir, n)) for n in FILES},
                              manifest["files"])
    print("\n".join(lines_b))
    if not ok_b:
        print("!! 备份自身不完整/与 manifest 不符 ⇒ 这份备份不可用来还原")
        return 3
    snap = snapshot(args.save_dir)
    ok, lines = fmt_table("=== 当前存档 vs 备份（同起点核对）===", snap, manifest["files"])
    print("\n".join(lines))
    same = ok and all(snap[n] is not None for n in FILES)
    print(f"\nVERDICT: {'SAME（四件逐字节一致 ⇒ 同起点成立）' if same else 'DIFFER（存在不一致，见上）'}")
    return 0 if same else 3


def cmd_restore(args) -> int:
    if game_running() and not args.force:
        print(f"!! 游戏在跑（{BRIDGE_JSON} 存在）⇒ 拒绝还原（必须先优雅退游戏）。确认要还原加 --force。")
        return 4
    manifest, rc = _load_manifest(args)
    if manifest is None:
        return rc
    backup_dir = os.path.join(args.backup_root, f"{args.arm}-start")
    # 1) 先校验备份自身
    ok_b, lines_b = fmt_table(f"=== 还原前：备份（{backup_dir}）完整性 ===",
                              {n: stat_one(os.path.join(backup_dir, n)) for n in FILES},
                              manifest["files"])
    print("\n".join(lines_b))
    if not ok_b:
        print("!! 备份自身不完整 ⇒ 停止还原（不拿坏备份覆盖存档）")
        return 3
    if not os.path.isdir(args.save_dir):
        print(f"!! 存档目录不存在：{args.save_dir}")
        return 2
    before = snapshot(args.save_dir)
    print("=== 还原前：当前存档（会被覆盖）===")
    for name in FILES:
        v = before.get(name)
        print(f"  {name:22} " + (f"{v['size']:>10} B  {v['mtime']}  {v['sha256'][:16]}…" if v else "MISSING"))
    for name in FILES:
        src = os.path.join(backup_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(args.save_dir, name))
    after = snapshot(args.save_dir)
    ok_a, lines_a = fmt_table("=== 还原后：当前存档 vs 备份 ===", after, manifest["files"])
    print("\n".join(lines_a))
    print(f"\nVERDICT: {'RESTORED（还原后逐字节 == 备份 ⇒ 同起点恢复）' if ok_a else 'FAILED（还原后仍不一致）'}")
    return 0 if ok_a else 3


def selftest() -> int:
    """全程在临时目录里跑，不碰真存档、不碰真备份目录。"""
    ok = True
    with tempfile.TemporaryDirectory(prefix="arm-start-selftest-") as tmp:
        src = os.path.join(tmp, "saves", "Wahaha_450799035")
        broot = os.path.join(tmp, "ab-backup")
        os.makedirs(src)
        for i, name in enumerate(FILES):
            with open(os.path.join(src, name), "wb") as fh:
                fh.write(f"dummy-{name}-{i}\n".encode("utf-8"))
        ns = argparse.Namespace(arm="_selftest", save_dir=src, backup_root=broot, force=False)
        bdir = os.path.join(broot, "_selftest-start")

        print("[selftest 1] backup 应 rc=0 且 manifest 四件齐全")
        rc = cmd_backup(ns)
        if rc != 0:
            print(f"!! backup rc={rc}"); ok = False
        mp = os.path.join(bdir, "manifest.json")
        if not os.path.exists(mp):
            print("!! manifest 未生成"); ok = False
        else:
            man = json.load(open(mp, encoding="utf-8"))
            if len([n for n in FILES if man["files"].get(n)]) != 4:
                print("!! manifest 四件不全"); ok = False

        print("\n[selftest 2] 重复 backup 应被安全闸拦下 rc=4")
        rc = cmd_backup(ns)
        if rc != 4:
            print(f"!! 重复 backup rc={rc}（应 4）"); ok = False

        print("\n[selftest 3] verify 应 rc=0（SAME）")
        rc = cmd_verify(ns)
        if rc != 0:
            print(f"!! verify rc={rc}（应 0）"); ok = False

        print("\n[selftest 4] 篡改存档一件 ⇒ verify 应 rc=3（DIFFER）")
        with open(os.path.join(src, "SaveGameInfo"), "ab") as fh:
            fh.write(b"tampered\n")
        rc = cmd_verify(ns)
        if rc != 3:
            print(f"!! 篡改后 verify rc={rc}（应 3）"); ok = False

        print("\n[selftest 5] restore 应 rc=0 且把篡改还原")
        rc = cmd_restore(ns)
        if rc != 0:
            print(f"!! restore rc={rc}（应 0）"); ok = False
        rc = cmd_verify(ns)
        if rc != 0:
            print(f"!! restore 后 verify rc={rc}（应 0）"); ok = False

        print("\n[selftest 6] 缺 manifest 的 restore 应 rc=2")
        ns2 = argparse.Namespace(arm="_nonexistent", save_dir=src, backup_root=broot, force=False)
        rc = cmd_restore(ns2)
        if rc != 2:
            print(f"!! 缺 manifest restore rc={rc}（应 2）"); ok = False

    print(f"\nSELFTEST {'PASS' if ok else 'FAIL'}（6 用例；临时目录已清理，未碰真存档）")
    return 0 if ok else 13


def main() -> int:
    ap = argparse.ArgumentParser(description="A7/B7 同起点协议：存档四件备份/恢复/核对")
    ap.add_argument("action", nargs="?", choices=["backup", "restore", "verify"],
                    help="backup | restore | verify")
    ap.add_argument("--arm", default="A7", help="臂名（默认 A7 ⇒ logs/ab-backup/A7-start）")
    ap.add_argument("--save-dir", default=SAVE_DIR, help=f"存档目录（默认 {SAVE_DIR}）")
    ap.add_argument("--backup-root", default=BACKUP_ROOT, help=f"备份根目录（默认 {BACKUP_ROOT}）")
    ap.add_argument("--force", action="store_true", help="绕过安全闸（游戏在跑 / 备份已存在）")
    ap.add_argument("--selftest", action="store_true", help="自测（临时目录，不碰真存档）")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.action:
        print("需要 backup / restore / verify 之一（或 --selftest）", file=sys.stderr)
        return 2
    return {"backup": cmd_backup, "restore": cmd_restore, "verify": cmd_verify}[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
