#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性排查：用 Mod 实际写出的字段名造一份 bridge.json，看脑侧 load_bridge_info() 能否读出 pid。

用途：核实 machine-runner 的"load_bridge_info() 读出 pid=None"这条报告是否成立。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brain"))

from agentfarm.bridge import SCHEMA_BRIDGE, load_bridge_info  # noqa: E402

# 字段名照 mod\AgentFarm.Bridge\BridgeHost.cs 的 BridgeDiscovery（CamelCase + 属性上的 JsonPropertyName）
payload = {
    "schema": SCHEMA_BRIDGE,
    "port": 17890,
    "token": "deadbeef",
    "pid": 24444,
    "modVersion": "0.7.21",
    "gameVersion": "1.6.15",
    "smapiVersion": "4.5.2",
    "startedAt": "2026-10-11T22:07:17+08:00",
}

with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "bridge.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    info = load_bridge_info(path)
    print("pid       =", repr(info.pid))
    print("port      =", info.port)
    print("modVersion=", info.mod_version)
    print("schema    =", info.schema)
    ok = info.pid == 24444
    print("结论：", "脑侧能正确读出 pid" if ok else "脑侧确实读不出 pid（报告成立）")

# 另一种可能：Mod 那边属性名大小写不同（例如 "Pid"）
with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "bridge.json")
    alt = dict(payload)
    alt.pop("pid")
    alt["Pid"] = 24444
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(alt, fh)
    info = load_bridge_info(path)
    print("若字段名是 'Pid' → pid =", repr(info.pid))
