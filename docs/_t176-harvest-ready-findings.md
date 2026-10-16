# task-176 取证：`harvestMethod` 来源、`ready` 来源标记、`acted` 诚实化

> 背景：task-173 在 **0.7.33** 上对固定样本 `(60,29)` 做定点 harvest = **FAIL**。
> Mod 回执 `{acted:true, ok:true, status:"ok"}`，但 `worldSeq 51→51`、作物还在、背包 +0、
> 存档逐字节未变。本文记录三处 Mod 硬缺陷的**来源已求证**结论（api-probe 实证），
> 供 task-177 真机复测与后续"来源追溯"使用。

探针命令（输出为 UTF-16LE，需 `Out-File -Encoding utf8` 转存后阅读）：

```
tools\il-probe\bin\Release\Probe26.exe "D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley" "StardewValley.Crop|GetHarvestMethod"
tools\il-probe\bin\Release\Probe26.exe "<游戏目录>" "StardewValley.TerrainFeatures.HoeDirt|readyForHarvest"
tools\il-probe\bin\Release\Probe26.exe "<游戏目录>" "FIND|GetHarvestMethod"
tools\il-probe\bin\Release\Probe26.exe "<游戏目录>" "FIND|HarvestMethod"
```

原始输出：`scratch\_t176_gethm.txt`、`scratch\_t176_ready.txt`、`scratch\_t176_find_gethm.txt`、
`scratch\_t176_find_ready.txt`（另见 Lead 侧同题复核 `scratch\_lead_{ghm,cropdata,findhm,readyforharvest}.txt`）。

---

## 1. 缺陷①：`harvestMethod` **整键缺失**（0.7.33 的实机缺陷；缺键 ≠ null）

真机样本 JSON（`scratch/run10-tile6029-before.json`，0.7.33 观测）：

| 格 | crop | ripe | ready | fullyGrown | currentPhase | phaseDays | dayOfCurrentPhase | dead | forageCrop | watered | `harvestMethod` | `readySource` |
| -- | ---- | ---- | ----- | ---------- | ------------ | --------- | ----------------- | ---- | ---------- | ------- | --------------- | ------------- |
| (60,29) | 270 | true | true | true | 5 | 6 | -9 | false | false | true | **缺键** | **缺键** |
| 邻格 | 262 | false | true | false | 4 | 5 | 7 | — | — | — | **缺键** | **缺键** |

`mod\AgentFarm.Bridge\Contracts.cs:30` 的全局序列化设置是
`DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull` ⇒ 值为 `null` 的字段被**省略**。
旧实现偏偏读不到工法（见下）⇒ 恒 `null` ⇒ **键连出现都不出现**，观测层完全看不出"判不了"与
"值就是 null"的区别，任务卡里的缺陷因此被掩盖了一整个版本。

### 正解：`Crop.GetHarvestMethod()` 是 **public 无参方法**

`StardewValley.Crop|GetHarvestMethod` 的完整 IL（`scratch\_t176_gethm.txt`）：

```
IL_0000: ldarg.0
IL_0001: call           StardewValley.GameData.Crops.CropData GetData()
IL_0006: dup
IL_0007: brtrue.s       -> IL_000C
IL_0009: pop
IL_000A: ldc.i4.0                          // 0 = HarvestMethod.Grab（默认）
IL_000B: ret
IL_000C: ldfld          StardewValley.GameData.Crops.HarvestMethod HarvestMethod
IL_0011: ret
```

* `FIND|GetHarvestMethod` 只命中两处调用方：`HoeDirt.performUseAction` 与
  `HoeDirt.performToolAction`（`scratch\_t176_find_gethm.txt`）—— 正是 `docs\_il-harvest-path.md`
  里"grab 分支 vs scythe 分支"的分岔点。
* `StardewValley.Crop.HarvestMethod` 这个**字段/属性在 1.6.15 根本不存在**
  （Lead 侧直接查询：`(未找到 StardewValley.Crop.HarvestMethod)`）—— 这才是旧实现
  `ReadMember(crop, "HarvestMethod")` 恒 `null` 的原因，**不是**可见性问题。
* 修法：直接调 `crop.GetHarvestMethod()`，把枚举映射成字符串（`0`→`"Grab"`、`1`→`"Scythe"`、
  未知值照实写数字），并把 `harvestMethod` 标成**无条件输出**（`JsonIgnoreCondition.Never`）。

## 2. 缺陷②：`ready` 的字段判据**不是** fail-open（原诊断更正）

`HoeDirt.readyForHarvest()` 的完整 IL（`scratch\_t176_ready.txt`）：

```
crop == null                                        ⇒ false
crop.fullyGrown.Value && crop.dayOfCurrentPhase > 0 ⇒ false     // 复收冷却
crop.currentPhase.Value < crop.phaseDays.Count - 1  ⇒ false     // 阶段没走完
crop.dead.Value                                     ⇒ false     // 枯死
!crop.forageCrop.Value                              ⇒ true
否则                                                 ⇒ whichForageCrop != "2"   // 采集形态 2
```

这与 `CropMeta.Ready()` 的字段判据**逐条等价**。也就是说：`(60,28)` 那种
"`fullyGrown=false` 却 `ready=true`"是**游戏自己的答案**（末阶段 + `dayOfCurrentPhase` 非正 +
未枯死），`readyCrops == crops == 102` 很可能就是游戏口径的真相 —— **不是** bug。
若把"反射不可用 + 字段齐全"判成 `null`，反而会把整片可收作物变成不可收（fail-closed 过头）。

因此必修②的落点是**来源标记**，而不是收紧判据：

| `readySource` | 含义 | 允许条件 |
| ------------- | ---- | -------- |
| `"game"` | 真的反射调用了 `HoeDirt.readyForHarvest()` | 反射成功 |
| `"fields"` | 退回字段判据 | **全部**判据字段可读（与上面 IL 逐条等价） |
| `null` | 判不了 | 任一判据字段读不到 ⇒ `ready` 也是 `null` |

`readySource` 同样**无条件输出**（null 也出键）。

## 3. 缺陷③：`acted` 不许自述成功

旧实现 `Ok = err == null && acted`，其中 `acted` 直接取 `checkAction(...)` 的返回值
（"这一格被认领了"），于是"游戏认领了但没做事"（镰刀类作物被误当 Grab 走 `interact`）
也会报 `ok:true, acted:true` —— 与真机观测（`worldSeq` 不动、作物还在、背包 +0、存档未变）
完全吻合。

修法：`interact` 在调用前后各取一次目标格的**可观测签名**
（地面物体 `QualifiedItemId`+`Stack`、地形特征类型、`HoeDirt` 浇水态与作物
`indexOfHarvest`/`currentPhase`/`fullyGrown`/`dead`、`Action`/`TouchAction` 属性、门）：

* 只有**签名真的变了**才 `acted=true`、`status="ok"`；
* `worldSeq` 前进但目标格没变 ⇒ 仍然 `acted=false`；
* 快照拿不到（判不准）⇒ `acted=false` + `status="no_action"`（宁可让人来核，也不自述成功）。

## 4. 与脑侧的接口（不变）

* `harvest_tool(tv)`：`harvestMethod` 为 `"Scythe"` ⇒ 返回 `"scythe"`（走 `use_tool` 工具路径）；
  **缺键 / null ⇒ `None`**（判不了工法，**不许**默认 `Grab`；只能试 `interact`，并以观测差分定成败）。
* `tile_ready(tv)`：只认 `ready is True`（fail-closed）。
* `harvest()`：回执 `acted is False` 或 `ok is False` ⇒ `code="failed"` 并如实写进 reason。

## 5. task-177 真机复测判据（预告）

同一样本 `(60,29)`，0.7.34 上定点 harvest：

1. `tiles[]` 里 **`harvestMethod` / `readySource` 键必须存在**（值可以为 `null`）；
2. `(60,29)` 若 `harvestMethod == "Scythe"` ⇒ 脑侧必须走 `use_tool(tool="scythe")`，
   且真机应看到 **`farm.ripeCrops`/`readyCrops` 下降 + 背包 +1 + `worldSeq` 前进**；
3. 若游戏仍不给收 ⇒ 回执必须是 `status="no_action"` / `acted=false`，**不许**再出现
   "回执 ok 但世界逐字节未变"。
