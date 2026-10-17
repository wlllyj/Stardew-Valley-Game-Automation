# -*- coding: utf-8 -*-
"""取 _t238 的精确变异锚点（只读）。"""
from pathlib import Path

t = Path("scratch/_t238")
src = (t / "brain/agentfarm/longrun.py").read_text(encoding="utf-8")
i = src.find('if action == "pickup":')
print("PICKUP repr:", repr(src[i:i + 90]))
j = src.find("if not self._tool_upgrade_due(obs):")
print("DUE repr:", repr(src[j:j + 120]))
u = src.find("self._urgent_farm_work(obs, self._tool_suspended_stages(obs))")
print("URGENT repr:", repr(src[u - 40:u + 70]))
r = (t / "mod/AgentFarm.Bridge/ToolUpgradeRules.cs").read_text(encoding="utf-8")
print("tier count:", r.count("Tier == tierBefore + 1"))
k = r.find("Tier == tierBefore + 1")
print("TIER repr:", repr(r[k - 70:k + 70]))
