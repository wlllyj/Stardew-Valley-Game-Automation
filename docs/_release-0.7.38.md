# 0.7.38 发布计划 · 0.7.37 白名单事故 + F3 取回死锁的补救批次

> 状态：**已冻结并装机**（2026-10-18 01:03，HEAD `2ca6dc8`）。触发：0.7.37 装到真机后暴露的两个真机缺陷 ——
> ①**白名单事故**：装机版 `Skills.KnownSkills` 漏登记 7 个新技能（`debug_dump`/`add_missed_recipes`/`upgrade_tool`/`pickup_tool`/`craft_item`/`place_object`/`machine`），`BridgeHost` 在进主线程之前就回 `unknown_skill` ⇒ task-214 内省取证 BLOCKED、`upgrade_tool` 真机 100% 不可用；
> ②**F3 取回死锁**（task-206 FAIL）：水壶在铁匠铺在途 `daysLeft=0` + 窗口内 1 格未浇活苗 ⇒ `_tool_upgrade_plan()` 给出 `pickup`，但 `_tool_upgrade_due()` 的「紧急农活」闸门被那格干苗挡死，而干苗又因壶不在手上浇不了 ⇒ 自死锁。
>
> 本批**不含** task-210（机器链）、task-218（树）、task-219（意图对账）、task-221（余力多清）——它们排 0.7.39 及以后。

## 1. 本批卡片

| 卡 | 侧 | 内容 | 状态 |
|---|---|---|---|
| **task-216** | Mod + brain（dev-coder） | ①F3：`_tool_upgrade_due` 的紧急农活闸门**只拦 `upgrade`**、`pickup` 一律放行；②等待日留痕：`due=False` 时也必须记 `tool_upgrade_skipped{reason:"wait"\|"need_slot"}`；③GAP-2：C# 自检补 `ToolUpgradeRules.Select` 的「同 kind + tier==tierBefore+1」与「多命中拒绝」；④GAP-1：补 `scratch/_t205_mutate.py`；⑤NUT：B1e（只扣钱等级 0→0 不得判 ok）/B2b（取回后背包没工具不得判 ok）；⑥**白名单事故永久护栏** = 新增 `SkillCatalog.cs` 单一数据源 + 7 条 C# 自检（Catalog 与 `Skills.Create` 的 case **双向相等**、`IsLongTaskSkill` 从目录派生） | ✅ `fd1b88d` |

## 2. 冻结九步（每批照走，Lead 独占）

1. `tools/_note-*.txt`（首串必须是 `vX.Y.Z`，列出本版内容）
2. `python tools/_bump-mod-version.py X.Y.Z --note-file tools/_note-XXXX.txt`（改 manifest）
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "X.Y.Z"`（注释补本版条目、历史保留）
4. `dotnet build mod/AgentFarm.Bridge/AgentFarm.Bridge.csproj -c Release --nologo --no-incremental`（必须 0 警 0 错）
5. **冻结提交**（`git add -A` 后提交；工作树必须干净）
6. `python tools/check-release.py --expect X.Y.Z`（六项全绿）
7. `python tools/deploy-mod.py --no-quit`（装机 + 自动读档）
8. `python -m agentfarm goto Farm`（注意要 `PYTHONPATH=<repo>\brain`）
9. `python tools/preflight.py --expect X.Y.Z --save-baseline logs/runXXX-baseline.json` ⇒ ✅ 才起跑

## 3. 本批判据

- **白名单护栏必须可证伪**：C# 自检里「漏登记一个技能名」或「登记了没实现」必须各自让自检红（不是看源码文本，而是真的跑 `Skills.Create` 的分发表）。
- **F3 必须可复现**：构造「壶在途 `daysLeft=0` + 窗口内 1 格干苗」⇒ `_tool_upgrade_due(plan=pickup)` 必须 True；主循环级用例（不是直调函数）也要有。
- **真机烟雾（新增纪律）**：每批冻结装机后，**任取一个新技能发一次只读请求**（如 `debug_dump`），回执必须**不是** `unknown_skill`；否则整批视为未装机成功。

## 4. 已知限制 / 风险

- 0.7.37 已在真机装过且含 F3 死锁 ⇒ **A″/B″ 不得在 0.7.37 上跑**，必须等 0.7.38 + deputy 的 delta 验收结论。
- 游戏无人值守会 2:00 强制昏睡并扣 10% 金币（本会话已发生 3 次：−279 / −251 / −226g）⇒ 任何真机动作结束后必须立刻 `tools/stop-game.py`。
- 升级链的**材料**仍缺（铜锭/铜矿/煤全 0、无熔炉、`craftingRecipes` 无 Furnace 配方）⇒ 0.7.38 只解决"技能能被分发"，不代表能立刻做铜斧；配方问题交 task-214 真机内省。

## 5. 执行记录（2026-10-18 01:00–01:05）

### 5.1 冻结
- `tools/_note-0738.txt`（首串 `v0.7.38`，6 条）⇒ `_bump-mod-version.py 0.7.38`（manifest `0.7.37 → 0.7.38`，Description 头已换）
- `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.38"`（注释补 v0.7.38 三条 + `--- 历史 ---` 段保留 v0.7.37 原文）
- `dotnet build --no-incremental`：**0 警 0 错**；dll **269312 B** / manifest **57736 B**
- 冻结提交 **`2ca6dc8`**；`check-release --expect 0.7.38` **六项全绿**（`Ran 1055 tests`、树干净）

### 5.2 装机与基线
- `deploy-mod --no-quit`：`0.7.37 → 0.7.38`（dll 269312 / manifest 57736），桥 `modVersion=0.7.38 port=17890`，自动读档 `Wahaha_450799035` → FarmHouse (9,9)
- `goto Farm` ok（`hop1 FarmHouse→Farm source=[3,12] landing=[64,15]` **7618ms**）
- `preflight --expect 0.7.38 --save-baseline logs/run10f-baseline.json` = ✅ 可以起跑
  - 第1年 **秋 21 日 06:10 debris** / Farm(64,15) / 体力 **270/270** / 钱 **2042g** / 农场[草 512 / 石 106 / 枝 75 / 树 752 / 耕地 102 / 作物 34] / `waterLeft 25` / `tillableCount 135` / `tileCount 400 truncated` / 无模态 / `worldAdvancing true`

### 5.3 0.7.38 五文件指纹（A″/B″ 逐字比对用）
| 文件 | SHA256 |
|---|---|
| `brain/agentfarm/longrun.py` | `AAFD0CC1C93B7E3E9178ABFC77BB2561D2C1A35A80009C7B9D36E57B356A0023` |
| `brain/agentfarm/farmwork.py` | `B0C719E23D4D048271E0803FDE0C909E2B59F97E8D8EC3F094D766614BE0F2B1` |
| `brain/agentfarm/bridge.py` | `BBAE61454E809DB2FB7F195E80FEC06B8F8F368AAABA5608A02B95664D755062` |
| `mod/.../AgentFarm.Bridge.dll` | `16FA5D161F94E9DC8ACFC7ED687EEB59015F85DF056E08DABB51A69D6AE76938` |
| `mod/AgentFarm.Bridge/manifest.json` | `63B7D82C944DB225B058969B852C32137828BBFCD6AABFA51BC02040067CFBE2` |

### 5.4 待执行（真机烟雾 + 内省）
- machine-runner：task-214 复跑 —— 第一发 `debug_dump table=crafting_recipes key=Furnace` 必须**不**回 `unknown_skill`；随后 `trigger_actions` → `add_missed_recipes` 一次 → 复核；交付 `docs/_run10-furnace-probe.md`。
- deputy-lead：0.7.38 delta 验收（F3 delta / 通道⑤留痕 / GAP-2 断言 / GAP-1 脚本 / 冻结树 probe+mutate）⇒ 一句话判「可/不可放行 A″/B″」。

## 6. 下一步（0.7.38 之后）

1. **task-218**（树纳入清障 + 护栏 A/B）→ **task-219**（意图-执行对账，`User said (m18972)`）→ **task-210**（机器链：熔炉→铜锭，进 0.7.39）。
2. **task-151 rev5**（指定作业区清空 `zone_cleared` + 连续 2 天复核）与 **task-221 rev2**（余力多清）排在 218/219 之后（目标 1 新口径，`User said (m19037)`）。
3. 全部就绪后：0.7.39 冻结 → A″/B″ 两臂各 5 天 → 双工具判决 + L0–L5 演进对照。
