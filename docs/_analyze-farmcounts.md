# `farm` 聚合口径定案（task-10 B）

> 取证分析师 log-analyst，2026-10-11。只读取证；每条结论带 `文件:行号` 或 IL 定位。
> 回答 machine-runner 报的计量疑点：「同一天无跨日，`farm.crops` 读出 31（起点，人在 FarmHouse）→ 8（在 Farm）→ 21 → 32（终点，人在 FarmHouse）」，
> 以及「`unwateredCrops` 31→0→32，连做 3 次 observe 完全一致」。

---

## 0. 一句话结论

那不是抖动，也**不是同一个计数器在跳**：`31→8→21→32` 是**两套不同仪器**混在一列里——`farm.*` 是「整个 Farm 的全场扫描」
（`Game1.getFarm()`，与玩家在哪无关），journal/`final` 里的 `crops`/`unwatered_crops` 是「当前地点 `location.tiles[]`（≤400 格窗口）」。
更要紧的是第二条：**`farm.unwateredCrops` 不是「今天还干着的格子数」**，它是 `CropData.NeedsWatering` 这个**数据表静态属性**
（IL 已定案），所以它整天都在 31→32 之间，**根本不能用来验收浇水**；而 `checks.crops_watered` 读的窗口口径
在 FarmHouse 里恒真（0 格作物 ⇒ 空真通过），run2 就是这么给出 `crops_watered=true` 的。

---

## 1. 两套仪器对照表

| | A. `farm.*`（全场扫描） | B. `location.tiles[]`（当前地点窗口） |
|---|---|---|
| 数据来源 | `mod/AgentFarm.Bridge/FarmScan.cs` 的 `FarmScanCache`：`farm = Game1.getFarm()`（`:110-111`），分帧跑完整轮后发布（`:197-209`） | `mod/AgentFarm.Bridge/WorldSnapshot.cs:388` 起：把当前 `Game1.currentLocation` 的 `objects` + `terrainFeatures` **按离玩家距离排序**后取最近 `MaxTiles = 400` 格（`:473-476`） |
| 与玩家位置的关系 | **无关**（永远是 Farm） | **强相关**（只给玩家身边 ≤400 格） |
| 上限/截断 | 无（整场跑完） | 有：超出 400 格 → `location.tilesTruncated = true`（`WorldSnapshot.cs:352`、`Contracts.cs:286`） |
| 谁在用它 | `WorldSnapshot.cs:766-785 ReadFarm()` → `snap.Farm`（`:180`）；`Contracts.cs:445-471 FarmView` | `WorldSnapshot.cs` 的 `tiles` 数组；脑侧 `FarmWorker.tiles_of(obs)` |
| 脑里的消费点 | `brain/agentfarm/planner.py:522-530`（**仅当 `tiles[]` 为空时**退回 `farm.*`） | `planner.py:497-521`（逐格真值，优先）、`longrun.py:382-403 _essence()`（journal 的 `crops`/`unwatered_crops`/`tillable`） |

---

## 2. 数字逐条对账（run2，spring 10）

| 读数 | 时刻/位置 | A. `farm.*` | B. 窗口（journal/`final`） |
|---|---|---|---|
| `logs/run2-observe-start.json` | 22:08:07，FarmHouse[9,9]，`worldSeq=5 scanSeq=5 complete=true` | hoeDirt **35**、crops **31**、unwatered **31**、weeds 480、stones 249、twigs 119、trees 211、grass 595 | `location.tiles[]` = FarmHouse（家具 1 格）⇒ **crops 0**（`mission` 见 §3） |
| journal `day_start`（`longrun-3day-llm-run2.jsonl` L2，t=7.96，location=**Farm**） | 走到农场后 | — | crops **31**、unwatered **31** |
| journal `review`（L39 t=183.31、L45 t=199.75） | 在 Farm 作业中 | — | crops **8**、unwatered **0** |
| `logs/run2-day-end-88.json`（`final`，t=450.97） | 12:00，location=**Farm**，tile[55,16] | — | crops **21**、unwatered_crops **0**、tillable **200** |
| `logs/run2-day-end-91.json`（`final`，t=631.16） | 16:10，location=**FarmHouse**，tile[8,8] | — | crops **0**、unwatered_crops **0**、tillable **0** |
| `logs/run2-observe-end.json` | 22:19:11，FarmHouse[8,8]，`worldSeq=381 scanSeq=381 complete=true` | hoeDirt **92**、crops **32**、unwatered **32**、weeds 462、stones 242、twigs 117、trees 211、grass 595 | — |

**31→8→21→32 完全解释**：
* `31` = `farm.crops`（全场，观测起点；恰好也是那天农场窗口的第一读数——两个仪器同值属巧合）；
* `8` / `21` = **窗口**读数（`_essence` 数的 `location.tiles[]`），**8→21 的变化来自玩家站位变了**，
  不是作物数量变化：窗口是按「离玩家最近的 400 格」截取的（`WorldSnapshot.cs:473-476`），
  玩家身边非作物格越多，远处作物被挤出窗口的越多 ⇒ **窗口计数随站位波动，不能当总量**；
* `32` = `farm.crops`（全场，观测终点）。
* 全场真值 31→32 与当天账目吻合：`farm.hoeDirt` 35→92（+57 格开垦）、`crops` +1（当天播了 1 颗）。

**31→0→0→32 完全解释**：A 列 31→32 是 `farm.unwateredCrops`（数据表静态属性，§3），
B 列 31→0→0 是窗口口径下 `tiles[].watered` 的真值（当天把看得见的作物全浇了）。
两个数同名不同义，混在一列才会像「跳变」。

---

## 3. `farm.unwateredCrops` 到底是什么（IL 定案，本任务最关键的一条）

生产链：`FarmScan.cs:236` 对每个有作物的 `HoeDirt` 调 `dirt.needsWatering()` → 真则 `_acc.UnwateredCrops++`。

`StardewValley.TerrainFeatures.HoeDirt.needsWatering()`（`scratch/il-tools.txt:4215-4237`）逐指令为：

```csharp
if (crop == null) return false;
if (!readyForHarvest() || crop.RegrowsAfterHarvest())
{
    var data = crop.GetData();          // CropData
    if (data == null) return true;
    return data.NeedsWatering;          // ← 只读数据表！
}
return false;
```

⇒ **它完全不看 `state` / `isWatered()`**，只看「这作物按数据表需不需要浇水」以及「是否已成熟待收（且不复活）」。
所以它**不随当天浇水变化**——run2 里从 06:00 的 31 到 21:00 的 32（只多了当天播的 1 颗），就是这条的直接证据。

对照「浇水」的两个真值来源：

| 概念 | 真值 API | IL/源码 |
|---|---|---|
| 这一格今天浇过没有 | `HoeDirt.isWatered()` = `state.Value == 1` | `scratch/il-hoedirt.txt:2-8` |
| 每天早上会不会自己变干 | `HoeDirt.dayUpdate()`：`crop.newDay(state)`，室外非温室且有 `1 - GetFertilizerWaterRetentionChance()` 概率 ⇒ `state = 0` | `scratch/il-hoedirt.txt:11-82`（复位在 `:65-74`） |
| 观测里怎么读 | `tiles[].watered`（`WorldSnapshot.cs:449 t.Watered = hd.isWatered();`） | 逐格，**没有聚合字段** |

⇒ **`farm.*` 里不存在「今天还剩几格没浇」这个量**：想按天验收浇水，只有逐格 `tiles[].watered`。

---

## 4. `tilesTruncated` 对「上位计数」有没有影响？——**答：不影响 `farm.*`，只影响窗口**

* `tilesTruncated` 是 `location` 级字段：`WorldSnapshot.cs:352`（`truncated` 由 `:473-476` 按 `MaxTiles=400` 算出）、`Contracts.cs:286`。
  它只描述「`location.tiles[]` 被截断了」。
* `farm.*` 走的是**另一条链**（`FarmScanCache`，整场扫描 + 分帧预算 `BudgetPerTick = 300`、`FreshSeconds = 2.0`，`FarmScan.cs:28/:31`），
  与 `tiles[]` 的 400 上限没有任何关系 ⇒ **全场计数不受 `tilesTruncated` 影响**。
* 但 `farm.*` 有自己的两个坑，验收时必须一起读：
  1. **`complete == false` 时全是 0**（不是「0 个作物」）：`WorldSnapshot.cs:771-773`
     `if (published == null) return new FarmView { Loaded = true, Complete = false, ScanSeq = _worldSeq };`；
  2. **可能读到上一轮完整结果**（缓存）：`ReadFarm` 返回 `_farm.Current`（`WorldSnapshot.cs:766-785`），
     所以要对账就得同时记 `worldSeq` 与 `farm.scanSeq`（相等=新鲜）。
  实测三份 observe 都是 `complete=true` 且 `scanSeq == worldSeq`（5/5、381/381、12/12），可直接用。

---

## 5. 验收该怎么读（可判定规则）

* **R1** `farm.*` 只在 `farm.complete == true` 时可当读数；`complete=false` 一律视为「还没扫完」，不是 0。
* **R2** `farm.*` 是**Farm 全场**（`Game1.getFarm()`），**玩家在 FarmHouse 读它也有效**——这是设计，不是 bug；
  不要再把「人在 FarmHouse 但 farm.crops=31」当异常。
* **R3** 总量类指标只用 `farm.crops` / `farm.ripeCrops`（全场真值）。
  **禁止**把 `farm.unwateredCrops` 当「今天干着的格数」（§3）。
* **R4** **浇水验收必须逐格且必须限定室外农场**：
  1. 前提：`location.isOutdoorFarm == true`（`WorldSnapshot.cs:331-332`：`IsOutdoorFarm = (loc.Name == "Farm")`）；
  2. 判据：作业区内 `tiles[].watered == true` 的格数 == 计划浇水格数（前后差分），而不是 `unwatered_crops == 0`；
  3. 现状缺陷：`brain/agentfarm/longrun.py:1361` 的 `"crops_watered": int(rep.final.get("unwatered_crops") or 0) == 0`
     用的是窗口口径 ⇒ **站在 FarmHouse 时 0 格作物 ⇒ 恒真**。run2 实证：L89 `checks.crops_watered=true`
     而同一天 `final` 是 `location=FarmHouse, crops=0, unwatered_crops=0`（`run2-day-end-91.json`）。
     修法（二选一）：加 `location.isOutdoorFarm` 前提；或改成「作业区内 `tiles[].watered` 全真且至少 N 格」。
* **R5** 任何对账都要把「仪器 + 位置 + 新鲜度」一起记：`location.name`、`location.isOutdoorFarm`、`tilesTruncated`、
  `worldSeq`、`farm.scanSeq`、`farm.complete`。只写一个 `crops=` 的数字，下一轮必然又要重查（`docs/_run2-evidence.md` §3.6 那张表就是这么来的）。
* **R6**（建议给 dev，最小改动、一劳永逸）新增 `farm.dryCrops`：遍历 `farm.terrainFeatures`，
  数 `HoeDirt` 里 `crop != null && !hd.isWatered()` 的格数。这样「当天还剩几格没浇」才有**单字段真值**，
  与 `needsWatering`（数据表口径）彻底分开命名。

---

## 6. 未定项（U）

* **U1**：`farm.unwateredCrops` 在 `FarmScan` 之外是否还有别的写点（本文只钉了 `FarmScan.cs:236`；`grep` 全 mod 未见第二处，但未逐行读 `FarmScan.cs` 的 `StepCore` 全部 400 行）。
* **U2**：`farm.grass` 把 `Bush` 也算进去（`FarmScan.cs:246`）⇒ 不能当「可割草量」，逐格真值只有 `tiles[].kind=="grass"`。
* **U3**：`run2-day-end-88.json` 的 `checks` 内容本次未打印（脚本 keep 列表没包含），`ended_by` 亦未复核；
  但 `final`/`plots`/`notes` 已足够支持 §2 的结论，且 `notes` 里出现了「补水成功（waterLeft 0 → 40）」「记下 2 格『动了没用』的地」等关键行。
* **U4**：`farm.scanSeq` 与 `worldSeq` 的「新鲜」判据在极端帧率下是否可能错配（未做压力测试）。

---

## 7. 复核命令（只读）

```powershell
$env:PYTHONUTF8=1
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
# 1) 把 farm 块/位置/新鲜度从任意 observe 或 day_end json 里拉出来（本次用的脚本）
& $py scratch\_farm_dump.py logs\run2-observe-start.json logs\run2-observe-end.json `
     logs\run2-day-end-88.json logs\run2-day-end-91.json
# 2) 把 run2 journal 里所有 farm 读数拉成时间线
& $py scratch\_farm_trace.py
# 3) 语义证据（IL）
& $py scratch\_probe_il.py scratch\il-hoedirt.txt "StardewValley.TerrainFeatures.HoeDirt|isWatered" `
     "StardewValley.TerrainFeatures.HoeDirt|dayUpdate"
# 4) 生产链定位
Select-String -Path mod\AgentFarm.Bridge\FarmScan.cs -Pattern 'needsWatering|UnwateredCrops|getFarm\(\)|BudgetPerTick|FreshSeconds'
Select-String -Path mod\AgentFarm.Bridge\WorldSnapshot.cs -Pattern 'ReadFarm|TilesTruncated|MaxTiles|IsOutdoorFarm'
```

关联文档：`docs/_tool-matrix.md`（task-10 A）、`docs/_run2-evidence.md` §3.6（原始的 31→8→21→32 记录）、
`docs/_analyze-sleep-fail.md`（同一跑的 sleep 失败取证）。
