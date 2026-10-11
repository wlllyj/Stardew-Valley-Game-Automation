# -*- coding: utf-8 -*-
"""只读：打印 run2 开局快照的结构（各层 key、类型、长度），找到 tiles 在哪一层。"""
import json
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"logs\run2-observe-start.json"
with open(P, "r", encoding="utf-8") as f:
    d = json.load(f)


def walk(o, path="", depth=0, maxd=3):
    pad = "  " * depth
    if isinstance(o, dict):
        print("%s%s {%d keys}" % (pad, path or "$", len(o)))
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                walk(v, "%s.%s" % (path, k), depth + 1, maxd)
            else:
                s = repr(v)
                print("%s  %s = %s" % (pad, k, s[:120]))
    elif isinstance(o, list):
        print("%s%s [%d items]" % (pad, path, len(o)))
        if o and depth < maxd:
            walk(o[0], path + "[0]", depth + 1, maxd)


walk(d)
