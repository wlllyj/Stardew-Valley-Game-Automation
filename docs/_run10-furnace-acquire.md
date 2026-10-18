# task-226 · 买 1 个铜矿能否触发 Clint 送 Furnace 蓝图（0.7.38 真机）

> **一句话结论：PASS —— 「买 1 个铜矿」就足以解锁 Furnace。**
> 事件 `Data/Events/Farm` 键 `992553/t 600 1130/n copperFound` 在 fall 22 10:00 进 Farm 时当场触发；
> 过场逐句走完后游戏弹出 **"Learned how to craft a 'Furnace'"**；睡一夜落盘后，存档 `<craftingRecipes>`
> 从 **19 条变 20 条**，新增的键正是 **`Furnace`**。
> 即：**从 Clint 买来的铜矿也算"真收到"**（`Stats.CopperFound=1` + `mailReceived` 出现 `copperFound`）——
> 这条与旧 wiki「必须自己挖矿」的说法**相反**，属真机实测结论。

---

## §1 前置与现场

| 项 | 值 |
|---|---|
| 游戏版本 | Stardew Valley 1.6.15 / SMAPI 4.5.2 / **AgentFarm Bridge 0.7.38**（`modVersion=0.7.38`，装机 dll **269312 B / 01:03:41.564**、manifest 57736 B / 01:03:09.831） |
| HEAD | `2dde12e`（`task-210: 机器链…`；本卡取证期间**未动代码**） |
| 游戏进程 | 本卡期间 PID **8520**（StartTime `2026/10/18 1:29:34`），退出前仍存活 |
| bring-up | 停机态起跑：`$env:ALSOFT_DRIVERS="null"; python -u tools\deploy-mod.py --no-quit` ⇒ exit 0；`load_save ok`（进入存档，地点 FarmHouse (9,9)） |
| preflight | `--expect 0.7.38 --save-baseline logs\t226-baseline.json` ⇒ **exit 1**，唯一 ❌ =「在户外农场」（因为读档即在床上 `isInBed=true`，本卡流程要求先在家睡，属预期）；其余版本/已读档/无模态三项 ✅ |

**存档四条（本卡起点，全部逐字节记录）**

| 文件 | size | mtime |
|---|---|---|
| `Wahaha_450799035` | 4383128 B | 2026-10-17 23:38:17.154 |
| `SaveGameInfo` | 29605 B | 2026-10-17 23:38:17.251 |
| `Wahaha_450799035_old` | 4417243 B | 2026-10-17 12:09:48.738 |
| `SaveGameInfo_old` | 29567 B | 2026-10-17 12:09:48.842 |

**起点 `<craftingRecipes>`：count=19、has_Furnace=False**（Campfire / Cobblestone Path / Gravel Path / Wood Path / Text Sign / Stone Sign / Wood Sign / Torch / Chest / Gate / Wood Fence / Cherry Bomb / Wild Seeds (Sp) / Field Snack / Scarecrow / Basic Fertilizer / Stone Fence / Mayonnaise Machine / Sprinkler）。
**起点 `<copperFound xsi:nil="true" />`、`mailReceived`/`mailbox`/`mailForTomorrow` 均无 `copperFound`。**

## §2 购买回执原文（只买 1 个，恰好 1 单）

**第一发失败（负例，如实保留）**：背包 12 行占满时 `BridgeError`：
> `no_inventory_space`：「背包既没有空格、也没有「Copper Ore」的同类堆叠可以并入（空格 0），为避免扣了钱却拿不到东西，本次不购买。请先腾出背包空间」

> 说明：**没有重试第二次**（重试会重复扣钱）。此时 `money 2042→2042`、`inv_diff={}`。

**腾一格（受制裁路径，出货箱）**：`FarmWorker.sell(slot=7, whitelist=["(O)Moss"])` ⇒ `ok=True code=ok`
> 「已出货槽位 7 的 (O)Moss（背包 2→0，出货箱 1 件）；钱要等下一次 NewDay…（当前 2042g）」
`inventory[]` 行数 **12→11**、`shippingBin.count 0→1`、`money` 不变。

**买到 1 个（`shop="Blacksmith"`）**：
> 「「Copper Ore」单价 75g，请求 1 个（库存 无限）；钱 2042→1967（支出 75g），背包里这件 0→1（净得 1）；
> 调用：`tryToPurchaseItem(Copper Ore, null, 1, 0, 0) → False`；收货：`addItemToInventoryBool(Copper Ore ×1, false) → true`…
> 结论：买到了 1 个「Copper Ore」，共花 75g」

观测差分：**money 2042→1967（−75）、`inv_diff={'(O)378': 1}`** ⇒ `PASS_BUY_ONE_ORE`。此后 `tod` 从 700 走到 810（时钟在走）。

## §3 跨日、晨间结算框与「进 Farm」时刻

1. **读档即在床上导致 sleep 失败（新状态坑）**：`verify-sleep-brain.py --times 1` ⇒ `sleep_no_question`
   > 「睡觉提问没弹出来，拒绝盲发应答…当前地点 FarmHouse 的 lastQuestionKey=(空)；诊断：isInBed=True, Game1.newDay=False, activeMenu=(无), dialogueUp=False, canMove=True, gameMode=3, timeOfDay=900」
   原因：脑侧 `sleep()` 看到"已经在床上"就跳过"踩触发格"这一步 ⇒ 提问永不弹出。空转后 `tod 900→1150`，存档与 `day` 均未变。
   起床尝试（`move_to`）全部失败：`(9,11)/(10,11)/(8,11)` ⇒ `unreachable`；`(10,10)/(11,12)` ⇒ `precondition_failed`。**没有 hack**。
2. **用地点 warp 出床（有效且无副作用）**：`ensure_location("Farm")` ok（FarmHouse→Farm [64,15]，`worldSeq 50→59`，**`isInBed` 变 false**）→ `ensure_location("FarmHouse")` ok（[3,11]，`worldSeq 60`）；期间 `eventUp=false`（同日进出不算"次日清晨"，**没有误触发事件**）。
3. **sleep 成功**：`ok=True code=ok`
   > 「已跨日：fall 21日 → fall 22日（体力 270→270）；已踩触发格 (10,9)：回执 ui_modal = **命中信号**」
   观测 `day [1,fall,21]→[1,fall,22]`、`tod 600`、`money 1967→1977`（+10 = 出货箱 Moss×2 次日结算）。
4. **晨间 `ShippingMenu` 卡住日切落盘链（task-47 机制复现）**：先只看到 `01:36:09 Synchronizing 'NewDay' task...`，**没有** `before save`；关掉结算框（`dismiss_modal` → 反射 `ShippingMenu.okClicked()`，等价玩家点 OK）后**同一秒补齐**：
   ```
   L550 01:36:09 TRACE SMAPI] Synchronizing 'NewDay' task...
   L606 01:43:17 TRACE SMAPI] Context: before save.
   L607 01:43:17 TRACE game] SaveGame.Save() called.
   L608 01:43:17 TRACE SMAPI] Synchronizing 'Save' task...
   L611 01:43:18 TRACE game] SaveGame.Save() completed without exceptions.
   L612 01:43:19 TRACE SMAPI] Context: after save, starting fall 22 Y1.
   ```
   存档：`Wahaha_450799035` **4383128 → 4409846 B / 01:43:18.119**、`SaveGameInfo` **29605 → 29731 B / 01:43:18.221**、`_old` 换成旧那对。
   > 小插曲：第 1 次 `dismiss_modal` 报 `BridgeError timeout: ShippingMenu 等了 5250ms 还没被游戏自己关掉（路径=ok_clicked）`，但它的 `okClicked()` 已经生效（就是这次触发保存链）；第 2 次成功关闭（「已出货/存档菜单处理完毕…等了 1837ms；菜单已消失」）。两次回执都留在 `scratch/t226-trigger.json` 的 `menus_closed[]`。
5. **进 Farm 的时刻**：`ensure_location("Farm")` ok 7.75s，落地 **Farm [64,15]**、`worldSeq 72→89`、**`tod=720`（10:00，落在 `t 600 1130` 窗口内）**。

## §4 过场：六句对话原文 + 两轮受控推进

`eventUp` 在进 Farm 后**第 1 秒**即为 true，2 秒后出现 `DialogueBox`。**全程 `dialogueIsQuestion=false`、`dialogueResponses=[]`、`professionsToChoose=null`** ⇒ 没有任何选择题被替游戏做；也**没有** `interact`/`use_tool`/`load_save`/点 GUI。

**六句原文（按出现顺序，逐字）**

1. `"Uh... Hi there. Good morning."`
2. `"If you want to get the most out of the ores you find, you'll need a furnace."`
3. `"Just so happens I had an extra set of blueprints lying around. Here, I want you to have them."`
4. **`"Learned how to craft a 'Furnace'"`**  ← `addCraftingRecipe Furnace` 已执行（游戏自己的"学会了"弹窗）
5. `"The furnace allows you to smelt metal bars. The bars can be used for crafting, construction, and tool upgrades."`
6. `"When you've smelted a few copper bars, consider having me upgrade one of your tools. It can make your work a lot easier."`

**第一轮受控推进（`dismiss_modal` 间隔 0.8s）**：5 次有效推进后停手。
| # | 关闭的文本 | 之后 |
|---|---|---|
| 1 | "Uh... Hi there. Good morning." | 无框（脚本过渡中） |
| 2 | （无框） | **第 2 句**出现 |
| 3 | "If you want to get the most out of the ores…" | 无框 |
| 4 | （无框） | **第 3 句**出现 |
| 5 | "Just so happens I had an extra set of blueprints…" | 无框 |
| 6–8 | — | **连续 3 次无变化 ⇒ 按护栏停手** |

**关键发现：那 3 次"无变化"落在事件的 `pause` 里，不是卡死。** 停手后仅做**被动观察**（60s 只 observe、不动任何东西），发现 `activeMenuText` 已经自己变成 **"Learned how to craft a 'Furnace'"** —— 即事件在 `pause` 后自行推进了。

**第二轮受控推进（间隔改成 3.0s，留够 `pause` 余量）**：3 次推进事件正常收尾。
| # | 关闭的文本 | 之后 |
|---|---|---|
| 1 | "Learned how to craft a 'Furnace'" | **第 5 句** 出现 |
| 2 | "The furnace allows you to smelt metal bars. …" | **第 6 句** 出现 |
| 3 | "When you've smelted a few copper bars, …" | **`eventUp=false`、`activeMenu=null` ⇒ 事件结束** |

每次 `dismiss_modal` 的回执形态（原文）：
> 「已关闭对话（非提问对话框，无需应答 `closeDialogue()` 关闭（复位 dialogueUp 与 player.CanMove））："…"；警告：模态已关闭（或本就没有模态），但游戏仍处于不可控状态（canMove=False，isPlayerFree=False），世界没有恢复（CanMove=false 会让 shouldTimePass=false，时钟随之停止推进），需要外部恢复…」

> 该警告在事件进行中是**预期**的（`eventUp=true` 时世界本来就该冻结），不是故障。

## §5 落盘与存档 XML 前后对比（PASS 的判据）

事件结束时 `tod` 仍是 720、`eventUp=false`。**`addCraftingRecipe` 只改内存**，当时最新存档仍是 fall 22 06:00 那份 ⇒ 直接退出会丢。因此做了一次落盘（唯一干净路径）：

- `FarmWorker.sleep()`（tod 1110）⇒ `ok=True code=ok`
  > 「已跨日：fall 22日 → fall 23日（体力 270→270）；已踩触发格 (10,9)」；回执：「已跨日：第 77 天 → 第 78 天（timeOfDay 1110 → 600，体力 270，1893ms）。怎么睡的：`answerDialogue(Yes："Yes")`；关框：`closeDialogue()`」
- 落盘（`[等落盘]` 判据 = `day_key` +1 **且** 存档 size/mtime 前进）：
  ```
  L1092 10:24:46 TRACE SMAPI] Synchronizing 'NewDay' task...
  L1095 10:24:47 TRACE SMAPI] Context: before save.
  L1096 10:24:47 TRACE game] SaveGame.Save() called.
  L1097 10:24:47 TRACE SMAPI] Synchronizing 'Save' task...
  L1100 10:24:47 TRACE game] SaveGame.Save() completed without exceptions.
  L1101 10:24:49 TRACE SMAPI] Context: after save, starting fall 23 Y1.
  ```

**存档四条：事件前 vs 事件后**

| 文件 | 事件前（fall 22 06:00） | 事件后（fall 23 06:00） |
|---|---|---|
| `Wahaha_450799035` | 4409846 B / 01:43:18.119 | **4449144 B / 10:24:47.741** |
| `SaveGameInfo` | 29731 B / 01:43:18.221 | **31201 B / 10:24:47.772** |
| `Wahaha_450799035_old` | 4383128 B / 23:38:17.155 | 4409846 B / 01:43:18.119 |
| `SaveGameInfo_old` | 29605 B / 23:38:17.252 | 29731 B / 01:43:18.221 |

**`<craftingRecipes>` 对比（判据本体）**

| | count | has_Furnace |
|---|---|---|
| 事件前（`Wahaha_450799035_old`，4409846 B） | **19** | **False** |
| 事件后（`Wahaha_450799035`，4449144 B） | **20** | **True** |

**Furnace 的确切键名与上下文（存档 XML 是单行文件，故取子串）**：
```xml
…<string>Sprinkler</string></key><value><int>0</int></value></item>
<item><key><string>Furnace</string></key><value><int>0</int></value></item>
```
即 `<craftingRecipes>` 字典末尾新增了键 **`Furnace`**（value `int 0`），位于 `Sprinkler` 之后。

**`copperFound` 三条存档证据（说明"买矿也算真收到"）**
1. `mailReceived` 列表末尾出现 **`copperFound`**（事件前没有）：
   `…<string>sawQiPlane</string><string>copperFound</string></mailReceived>`
2. `Stats.Values` 里 **`copperFound: 1`**：`<item><key><string>copperFound</string></key><value><unsignedInt>1</unsignedInt></value></item>`
3. `<copperFound xsi:nil="true" />` 仍然是 nil —— 这是**另一个成员**（与邮件旗标 `mailReceived`/Stats 不同），`n copperFound` 前置依的是邮件旗标，故它 nil 不影响触发；这一点容易看错，特此写明。

**SMAPI 时点冻结（退出后复制，源已停写）**

| 项 | 值 |
|---|---|
| 副本 | `logs/t226-smapi-window.txt` |
| size / 行数 | **120772 B / 1109 行**（源 120772 B / mtime 10:25:20；副本 mtime 10:25:50） |
| SHA256（源=副本） | `3675fdebaaa7f810d91384a053726fcd2c9103065615b914b523ca25096a895d` |
| BYTE_IDENTICAL | **True** |

**六串计数（全文累计，两次落盘各一套）**：`Synchronizing 'NewDay' task` **2**（L550@01:36:09 / L1092@10:24:46）、`Context: before save.` **2**（L606@01:43:17 / L1095@10:24:47）、`SaveGame.Save() called.` **2**（L607 / L1096）、`Synchronizing 'Save' task` **2**（L608 / L1097）、`completed without exceptions` **2**（L611@01:43:18 / L1100@10:24:47）、`after save, starting` **2**（L612@01:43:19 / L1101@10:24:49）⇒ **六串 2/2/2/2/2/2 全配对**。

**优雅退出（`User said (m02833)`）**：`python tools\stop-game.py` ⇒ **rc=0**、`✅ 游戏已退出（原 pids=[8520]）`；退出后 **进程 0** / `bridge.json` 已删 / 17890 只剩 **2 条 TIME_WAIT** / **存档四条退出前后逐字未变**。

## §6 结论与下一步

1. **PASS**：买 1 个铜矿 ⇒ `Stats.CopperFound=1` + `mailReceived += copperFound` ⇒ 次日 06:00–11:30 进 Farm 触发事件 992553 ⇒ 过场跑完学会 Furnace ⇒ 落盘后 `<craftingRecipes>` 19→20 且新增键 `Furnace`。
2. **与旧 wiki 相反**：**从 Clint 买的铜矿也算"真收到"**（代码层 `HasBeenInInventory`，而 `GetOneCopyFrom` 会复制该标志；task-223 的推断在真机得到证实）。⇒ **P0-0（没有铜锭）在"蓝图"这一环已解**；剩下的是钱与材料（`2000g + 5×铜锭`、熔炉 `20 铜矿 + 25 石`）。
3. **对 task-228（`advance_dialogue`/受控推进能力）的需求来源**：
   - 现有 `dismiss_modal` 在非提问 `DialogueBox` 上走 `closeDialogue()`，**会跳过该句的显示时机**（本次为抢救挂住 8.5 小时的事件才这么用）；它**没有跳过事件命令**（六句全部依次执行、`addCraftingRecipe` 正常生效），但**作为常规能力不可接受**（会看不到对话内容，也无法判断"再点一次会不会把下一句也跳掉"）。
   - 此外本次踩到两个真机坑，建议一并进卡：①**`dismiss_modal` 每句都返回 `world_stuck` 警告**（事件期间世界冻结是预期，但回执状态容易被误读为失败）；②**事件脚本有 `pause`**，用固定小间隔连点时会被误判"卡死"——**正确的等待策略是"文本变化后等 ≥3s 再试下一次"**，或由 `advance_dialogue` 内部等待。
4. **另一个真机坑（已记入 §3）**：读档即在床上时，脑侧 `sleep()` 会跳过"踩触发格"⇒ `sleep_no_question`；需要补"已在床上 ⇒ 先下床（含地点 warp 兜底）"的路径。
5. 下一步（供 Lead 决策）：①按 task-222 补 `debug_dump` 强类型资产；②按 task-228 做 `advance_dialogue`；③经济/机器链规划：先靠 `buy` 铜矿/煤/石 + `place_object` 熔炉 → `5 铜锭` → `upgrade_tool` 铜斧，唯一缺口是钱（约 6300g）。

## §7 保留物 / 不确定项 / 诚实声明

**保留物**：
- `scratch/t226-trigger.json` + `scratch/t226-event-obs-001..042.json`（逐秒 42 份观测）
- `scratch/t226-advance.json` + `t226-advance-obs-*.json`（两轮推进日志）
- `scratch/t226-passive.json`（60s 被动观察）
- `scratch/t226-persist.json`（睡一夜落盘）
- `scratch/t226-receipts.json`（SMAPI 冻结 + 六串 + 配方前后 + 存档四条）
- `logs/t226-trigger-console.log` / `logs/t226-advance2-console.log` / `logs/t226-persist-console.log` / `logs/t226-smapi-window.txt`
- 脚本 8 个：`_t226_buy / _t226_free_slot / _t226_unbed / _t226_getup_sleep / _t226_outdoor / _t226_trigger / _t226_advance / _t226_passive / _t226_persist / _t226_digest / _t226_receipts`
- 基线：`logs/t226-baseline.json`

**不确定项（如实列出）**
1. 首轮"连续 3 次无变化停手"是**我设的间隔太短**导致的误判；**至少 1 次无效 `dismiss` 调用**（未改变任何状态）—— 但它没有副作用（事件脚本不受影响，六句仍按序执行）。
2. 我**没有**在事件中途读取"当前已知配方"的能力（0.7.38 观测不暴露 `craftingRecipes`），所以"`addCraftingRecipe` 到底是在第几句执行的"只能由第 4 句 "Learned how to craft a 'Furnace'" 与最终存档反推。
3. 事件是否**已经开始就绪**（Clint 走位/`pause` 长度）依赖事件脚本本身，本次未逐帧取证。
4. 本次落盘用的 `FarmWorker.sleep()` 在 **tod 1110（18:30）** 执行；若在更早时段调用是否同样可睡未验证。
5. `Wahaha_450799035` 存档里 `<copperFound xsi:nil="true"/>` 仍为 nil 与 `Stats.copperFound=1` 并存，两者语义差异见 §5-3；**没有文档级定论**，只能确认"事件前置依的是邮件旗标"。

**诚实声明**：本次 PASS 的判据**完全来自存档文件字节变化**（size 4409846→4449144、`<craftingRecipes>` 19→20、新增键 `Furnace`），不依赖任何回执自述；购买、睡觉、事件推进每一步都有前后观测差分。唯一的流程偏离（"不要 sleep"）已在当时报备并获 Lead 正式授权，理由是判据本身要求落盘。
