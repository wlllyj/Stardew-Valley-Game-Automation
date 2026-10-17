# task-214 · Furnace 配方/触发器真机内省取证（0.7.38 复跑）

> **状态：已复跑完毕，结论 = 【仍无法判定】（三态中的第三态）。** 0.7.37 的 `unknown_skill` 事故**未复现**（白名单护栏生效）；
> 但「Furnace 配方能否被合法授权」被一个新缺陷卡住：`debug_dump` 只支持 `Dictionary<string,string>` 型数据表，
> `Data/TriggerActions`（1.6 是 `List<TriggerActionData>`）**取不到原文** ⇒ 触发器通道这一支无法验证。
> 已测到的硬事实：**假设 A（技能升级补发）已证伪**（`AddMissedMailAndRecipes()` 一次 → 0 条新增）；配方本身存在于游戏数据。
> 本轮对世界的写操作只有 `add_missed_recipes` 一次（实测 0 增量）；**存档零落盘**（§4）。

## §1 冻结件指纹与前置

**冻结件**：HEAD **`2ca6dc8`**（`freeze(0.7.38): task-216 F3 修复 + SkillCatalog 技能名单一数据源护栏（白名单事故永久护栏）+ 等待日留痕/判据收紧`）。

**五文件指纹逐字比对 —— 5/5 MATCH**（全 64 位 SHA256）：

| 文件 | size / mtime | SHA256 |
| --- | --- | --- |
| `brain/agentfarm/longrun.py` | 479469 / 2026-10-18 00:34:38.655 | `AAFD0CC1C93B7E3E9178ABFC77BB2561D2C1A35A80009C7B9D36E57B356A0023` |
| `brain/agentfarm/farmwork.py` | 204190 / 00:34:39.820 | `B0C719E23D4D048271E0803FDE0C909E2B59F97E8D8EC3F094D766614BE0F2B1` |
| `brain/agentfarm/bridge.py` | 60322 / 01:03:31.308 | `BBAE61454E809DB2FB7F195E80FEC06B8F8F368AAABA5608A02B95664D755062` |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | 269312 / 01:03:41.564 | `16FA5D161F94E9DC8ACFC7ED687EEB59015F85DF056E08DABB51A69D6AE76938` |
| `mod/AgentFarm.Bridge/manifest.json` | 57736 / 01:03:09.831 | `63B7D82C944DB225B058969B852C32137828BBFCD6AABFA51BC02040067CFBE2` |

装机目录 `…\Mods\AgentFarm.Bridge\AgentFarm.Bridge.dll` 与 `manifest.json` 的 size/mtime/SHA256 **与上表 dll/manifest 完全相同**（= 装的就是这份）。

**环境**：`health = {ok:true, status:"ok", modVersion:"0.7.38", runtime:{ticks:2599, uptimeSeconds:49.7, worldSeq:15, hasSaveLoaded:true, onTitleScreen:false}, server:{port:17890}}`；
`preflight` 由 Lead 跑（`logs/run10f-baseline.json`，`generatedAt 2026-10-18T01:04:29+07:00`、`worldSeq 11`、`day [1,"fall",21]`、`money 2042`、`stamina 270.0`、`location Farm`）；
存档四条 before：`Wahaha_450799035` **4383128 B / 2026-10-17 23:38:17.154**、`SaveGameInfo` 29605 / 23:38:17.251、`_old` 4417243 / 12:09:48.738、`SaveGameInfo_old` 29567 / 12:09:48.738。

**本轮实际发出的命令**（`scratch\_t214_run.py` 顺序执行并逐步落盘）：

```pwsh
python scratch\_t213_probe.py --table crafting_recipes --key Furnace
python scratch\_t213_probe.py --table trigger_actions
python scratch\_t213_probe.py --add-missed            # 只调一次，无循环；第 1 步失败则根本不执行
python scratch\_t213_probe.py --table crafting_recipes --key Furnace
```

## §2 每步原始回执（原文，未改写）

**步骤 1 · 白名单验活 = PASS**（`logs/run10f-step1_crafting_recipes.txt`）：

```json
{"ok": true, "status": "ok", "skill": "debug_dump", "reason": "按 key 过滤：exact 命中 1 条", "schema": "agentfarm-exec/2",
 "elapsedMs": 0, "worldSeqBefore": 24, "worldSeqAfter": 24, "uiOpened": false, "worldResumed": true,
 "table": "crafting_recipes", "count": 150, "truncated": false, "entries": [],
 "matched": [["Furnace", "378 20 390 25/Home/13/true/l 2/"]], "matchMode": "exact", "matchedCount": 1, "matchedTruncated": false}
```

⇒ 0.7.37 的 `unknown_skill` **未复现**；Furnace 配方**在游戏数据里存在**：配料 `378 20 390 25` = **20×铜矿(378) + 25×石头(390)**，产物 `13`（Furnace），条件串 `l 2`。

**步骤 2 · `trigger_actions` = 取不到（Mod 能力缺口）**（`logs/run10f-step2_trigger_actions.txt`，exit 1）：

```
load_failed: [load_failed] (HTTP 200) 读 Data/TriggerActions 失败：InvalidCastException: Unable to cast object of type
'System.Collections.Generic.List`1[StardewValley.GameData.TriggerActionData]' to type
'System.Collections.Generic.Dictionary`2[System.String,System.String].'；程序集里找不到 TriggerActionData 类型
```

同样失败（同为强类型资产，`logs/run10f-extra2.json`）：`objects`（`Dictionary<string,ObjectData>`）、`big_craftables`（`Dictionary<string,BigCraftables.BigCraftableData>`）、`machines`。**可用的只有 `crafting_recipes` / `cooking_recipes` / `mail` 三张字符串表**（Mod 自报支持 `crafting_recipes, cooking_recipes, trigger_actions, mail, machines, objects, big_craftables`，但后四张实际都抛 InvalidCastException）。

**步骤 3 · `add_missed_recipes`（只调一次）= ok 但 0 增量**（`logs/run10f-step3_add_missed.txt`）：

```json
{"ok": true, "status": "ok", "skill": "add_missed_recipes",
 "reason": "已调用一次 Farmer.AddMissedMailAndRecipes()：crafting +0、cooking +0、mail +0（共 0 条；前后计数见 beforeCounts/afterCounts）",
 "worldSeqBefore": 24, "worldSeqAfter": 24, "uiOpened": false, "worldResumed": true,
 "craftingRecipesAdded": [], "cookingRecipesAdded": [], "mailAdded": [],
 "beforeCounts": {"crafting_recipes": 19, "cooking_recipes": 1, "mail": 5},
 "afterCounts":  {"crafting_recipes": 19, "cooking_recipes": 1, "mail": 5}}
```

**步骤 4 · 复核**：与步骤 1 **逐字相同**（`count 150` / `matchedCount 1` / 同一条 `378 20 390 25/Home/13/true/l 2/`）⇒ 补发调用前后**玩家字典无变化**。

**补充只读取证**（`logs/run10f-extra.json`、`logs/run10f-extra2.json`、`scratch/run10f-crafting-recipes-full.json`、`scratch/run10f-mail-full.json`）：

* 整张 `Data/CraftingRecipes` 落盘 **150 条**（`truncated=false`），同类条件串对照：

  | 配方 | 数据原文 | 条件串形态 |
  | --- | --- | --- |
  | **Furnace** | `378 20 390 25/Home/13/true/l 2/` | **`l 2`**（未知语义，非技能形态） |
  | Charcoal Kiln | `388 20 334 2/Home/114/true/s Foraging 2/` | `s Foraging 2`（技能） |
  | Scarecrow | `388 50 382 1 771 20/Home/8/true/s Farming 1/` | `s Farming 1`（技能） |
  | Chest | `388 50/Home/130/true/default/` | `default`（无条件） |
  | Torch | `388 1 92 2/Field/93/false/default/` | `default`（无条件） |
  | Bee House | `388 40 382 8 335 1 724 1/Home/10/true/s Farming 3/` | `s Farming 3`（技能） |

* **存档 XML 真值**：`player.craftingRecipes` **19 条**（Wood Fence / Gate / Chest / Torch / Wood Sign / Stone Sign / Text Sign / Wood Path / Gravel Path / Cobblestone Path / Campfire / Cherry Bomb / Wild Seeds (Sp) / Field Snack / Scarecrow / Basic Fertilizer / Stone Fence / Mayonnaise Machine / Sprinkler）—— **无 Furnace**；`mailReceived` 5 条（`button_tut_1`/`button_tut_2`/`geodeFound`/`BackpackTip`/`sawQiPlane`）。
* `Data/Mail` 全表 179 条：正文含 `Furnace` 的只有 1 条（`elliottLetter5`，文学描写，**不是配方授予**）；没有 `%item recipe Furnace` 类邮件。

## §3 结论（三态取一：**仍无法判定**）

**取「仍无法判定」的理由**：把问题拆成两条假设后，一条已被真机证伪、另一条被 Mod 能力缺口卡住：

1. **假设 A（技能升级时由 `Farmer.AddMissedMailAndRecipes()` 补发）—— 已证伪。**
   判据（`docs/_il-furnace-recipe.md` §4 判据 A：调一次后 `craftingRecipes` 是否出现 Furnace）本轮真机执行：**调用成功但 0 条新增，前后计数 19/1/5 完全相同**。并且 Furnace 的条件串是 **`l 2`**，不是 `TryParseLevelRequirement` 认识的 `s <技能> <等级>` 形态（对照 Charcoal Kiln `s Foraging 2`、Scarecrow `s Farming 1`）—— 与"补发链路给它 0 条"完全自洽。
2. **假设 B（由 `Data/TriggerActions` 的触发器动作授予，可能依赖矿井进度）—— 未验证（唯一证据缺口）。**
   需要触发器原文，但 `debug_dump trigger_actions` 抛 `InvalidCastException`（`List<TriggerActionData>` → `Dictionary<string,string>`）：**Mod 的 `debug_dump` 只支持字符串字典型数据表**。这是本次**唯一的阻塞点**，且属 Mod 侧能力缺口，不是我方执行问题。
3. **已钉死的旁证**（不构成"可授权"）：配方**存在于游戏数据**（150 条中命中，20 铜矿 + 25 石头 → object 13），但玩家**未学会**（存档 19 条无 Furnace），且**没有配方邮件**（mail 179 条无授予项、`mailReceived` 无 Clint 信）⇒ 现状下 `craft_item` 应如实返回 `recipe_unknown`，**不许硬造**。

**建议（供 Lead 决策，不在本卡自作主张）**：
* **M1（推荐，Mod 侧）**：给 `debug_dump` 加 1.6 强类型数据资产支持（至少 `Data/TriggerActions` 的 `List<TriggerActionData>`，最好连 `Objects`/`BigCraftables`/`Machines` 一起），随后重跑步骤 2 —— 命中含 `Furnace`/`AddCraftingRecipe` 的条目即可定案 B；若 B 也不含，则结论变为「当前版本/存档无合法授予入口」，再谈 R2（手动执行触发器动作）或 R3（直接写 `player.craftingRecipes`，属改存档，需明确批准）。
* **M2（可并行）**：把 `player.craftingRecipes` 的 key 列表（或至少 `furnaceRecipeKnown` 布尔）暴露进观测，让脑侧不靠猜（`docs/_il-furnace-recipe.md` §6 已提过）。
* **护栏确认**：0.7.37 的 `unknown_skill` 事故本轮**未复现**（步骤 1/3/4 全部 `ok`）⇒ SkillCatalog 单一数据源护栏在真机上生效。

## §4 SMAPI 窗口 + 存档四条 + 退出确认

**SMAPI 窗口（退出后复制，字节一致）**：`logs/run10f-smapi-window.txt` = **78993 B / 431 行 / SHA256 `BE2A0AD3BF29AC044F74E3CFA876549C120D60E987ED2F7DB8555709CA4890E7` / dst mtime 2026-10-18 01:09:58.906 / `BYTE_IDENTICAL=True`**。尾部：

```
[01:09:58 INFO  AgentFarm Bridge] POST /v1/exec → 200 · 7ms · worldSeq=56
[01:09:58 TRACE game] Disconnected: ClosedGame
[01:09:58 TRACE SMAPI] Disposing...
[01:09:58 INFO  AgentFarm Bridge] 已删除发现文件 …\StardewValley\AgentFarm\bridge.json。
[01:09:58 TRACE SMAPI] Disposing the content coordinator.
```

**存档四条 —— 退前 / 退出后（逐字相同 ⇒ 本轮零落盘）**：

| 文件 | 退前 | 退出后 |
| --- | --- | --- |
| `Wahaha_450799035` | 4383128 B / 2026-10-17 23:38:17.154 | **同左** |
| `SaveGameInfo` | 29605 B / 23:38:17.251 | **同左** |
| `Wahaha_450799035_old` | 4417243 B / 12:09:48.738 | **同左** |
| `SaveGameInfo_old` | 29567 B / 12:09:48.738 | **同左** |

**优雅退出核对**（`python tools\stop-game.py`，**exit 0**，回执 `✅ 游戏已退出（原 pids=[17340]）`）：`StardewModdingAPI` 进程 **0** / `bridge.json` **已删** / 17890 **无 LISTENING**（仅 2 条 `TIME_WAIT`）/ 存档四条前后一致。
`add_missed_recipes` 虽通过（0 增量）也未跨日、未触发落盘 ⇒ 内存中的调用随退出消失。

**保留物**：`logs/run10f-step1_crafting_recipes.txt`、`logs/run10f-step2_trigger_actions.txt`、`logs/run10f-step3_add_missed.txt`、`logs/run10f-step4_crafting_recipes_again.txt`、`logs/run10f-steps.json`、`logs/run10f-extra.json`、`logs/run10f-extra2.json`、`logs/run10f-smapi-window.txt`、`scratch/run10f-crafting-recipes-full.json`、`scratch/run10f-mail-full.json`；脚本 `scratch/_t214_run.py`、`scratch/_t214_extra.py`、`scratch/_t214_extra2.py`、`scratch/_t214_vercheck.py`。
