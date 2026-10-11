# -*- coding: utf-8 -*-
r"""把 Mod 版本推到指定值，并把一段中文说明插到 manifest.json 的 Description 开头。

为什么要用脚本：manifest.json 的 Description 是**极长单行**中文，用 PowerShell 字符串读写会毁编码
（项目踩过两次），用编辑工具做"整行替换"又太长易错。这个脚本只做定点插入，写完立刻可审查 diff。

用法：
    python tools\_bump-mod-version.py 0.7.20
    python tools\_bump-mod-version.py 0.7.20 --note-file tools\_note-0720.txt

不带 --note-file 时只改 Version（Description 不动）。
规格化输出：`json.dumps(..., ensure_ascii=False, indent=2)` + 末尾换行（与仓库现状一致）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = REPO / "mod" / "AgentFarm.Bridge" / "manifest.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="新版本号，如 0.7.20")
    ap.add_argument("--note-file", default=None, help="UTF-8 文本文件：要插到 Description 开头的说明")
    ap.add_argument("--manifest", default=str(MANIFEST), help="manifest.json 路径（默认仓库里的那一个）")
    args = ap.parse_args()

    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        print(f"版本号格式不对：{args.version!r}（要 x.y.z）")
        return 2

    path = pathlib.Path(args.manifest)
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    old_version = data.get("Version")
    data["Version"] = args.version

    if args.note_file:
        note = pathlib.Path(args.note_file).read_text(encoding="utf-8").strip()
        desc = data.get("Description") or ""
        marker = f"v{args.version}"
        if not note.startswith(marker):
            print(f"说明文件应以 {marker} 开头，实际开头是：{note[:40]!r}")
            return 2
        if desc.startswith(marker):
            print(f"Description 已以 {marker} 开头，跳过插入（只更新 Version）")
        else:
            data["Description"] = note + " " + desc

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: Version {old_version} -> {data['Version']}"
          + ("；Description 头部已插入新说明" if args.note_file else "（Description 未改）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
