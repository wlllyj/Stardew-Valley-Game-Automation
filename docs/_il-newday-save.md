# task-47：日切保存（`SaveGame.Save()`）的调用条件与 20:04:29 那次缺口

> 只读取证；不改 `brain/`、`mod/`、`tests/`、`tools/`。证据：`scratch\il-nd-*.txt`（IL 转储）、
> `C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt`（行号见正文）、`docs\_run5-evidence.md`。
> 工具语义先说清（`tools\il-probe\Probe26.cs`）：`FIND|X` 只看**方法名**含 X 的被调方，且**每个调用者方法只报第一个命中**；
> `newobj`/`ldfld` 的操作数**不带声明类型**；`FINDSTR|`/`DISASM|` 按 UTF-16LE 解 IL 裸字节 ⇒ **找 `ldstr` 字面量恒为 0，0 命中不构成证据**。

## 0. 一句话结论

**落盘的唯一通道是「日终菜单栈为空时被创建出来的 `SaveGameMenu`」**；25→26 那次早晨，前一天出货让
`Game1.showEndOfNightStuff()` 先把 `ShippingMenu` 压栈并设为当前菜单，保存菜单**按设计被推迟**——所以"跨日成功却没有
`SaveGame.Save()`"首先是**菜单链没走完**，不是"游戏把保存跳过了"；至于**关框之后为什么仍没有落盘**，本文只给候选与
未定项（缺一步 IL/现场证据），不下结论。

## 1. 答案①：谁调 `SaveGame.Save()`，前置条件是什么

- 调用点（唯一一处，master 分支）：`StardewValley.Menus.SaveGameMenu.update(GameTime)`，`scratch\il-nd-4.txt:151-153`
  `Game1.IsSaving = true; this.loader = SaveGame.Save();`（静态迭代器）。
- `SaveGame.Save()` 的**真身**是 `StardewValley.SaveGame+<Save>d__92.MoveNext()`（`scratch\il-nd-10.txt:2-156`）：
  :57 `ldstr "SaveGame.Save() called."`（= SMAPI 日志那句游戏侧字面量）、:84-85 `ldstr "Save"` + `Task.StartTask(...)`
  （= SMAPI 那句 `Synchronizing 'Save' task...`）、:134 `"SaveGame.Save() completed without exceptions."`。
  落盘实写在 `StardewValley.SaveGame+<getSaveEnumerator>d__94.MoveNext()`（`il-nd-10.txt:157-980`：:768 `"Saving without compression..."`、:790 `Serialize[SaveGame](XmlWriter, GameSave)`、:912/:917 `"_old"`）。
- 进入该分支的前置（全部要满足，均在 `il-nd-4.txt` 的 `SaveGameMenu.update` 内）：
  1. :127 `hasDrawn && completePause == -1`（菜单至少画过一帧、没有待完成的倒计时）；
  2. :134 `Game1.IsMasterGame`；
  3. :136 `saveOnNewDay == true`（**false 支 :155-166 走 `complete()`，完全不写盘**）；
  4. :138-142 `player.team.endOfNightStatus.UpdateState("ready")`；
  5. :143-145 `Game1.newDaySync.readyForSave()`（`NewDaySynchronizer.readyForSave` = `SetLocalReady("ready_for_save", true); team.Update(); UpdateLate/UpdateEarly; return NetReady.IsReady("ready_for_save")`，`scratch\il-nd-5.txt`）；
  6. :146-147 `Game1.multiplayer.saveFarmhands()`。
- `saveOnNewDay` 的**写入者**（`scratch\il-nd-16.txt`，Game1 全部方法）：`Game1..cctor` :12707-12708 `= true`；
  换日重置方法 :32912-32913 `= true`。读取者只有 `SaveGameMenu.update`(:136) 与 `draw`(:271)。
  ⇒ 本机场景下它是 true；**没有找到把它置 false 的代码**（未定：Game1/SaveGame/SaveGameMenu/NewDaySynchronizer 之外若有人写，工具看不见字段写）。
- 菜单从哪来（唯一可定位的创建点）：`Game1.showEndOfNightStuff()` → `Game1+<>c.<showEndOfNightStuff>b__802_0()`
  （`scratch\il-nd-12.txt:2-141`）：
  - :5-21 `if (player.displayedShippedItems.Count > 0) { endOfNightMenus.Push(new ShippingMenu(player.displayedShippedItems)); displayedShippedItems.Clear(); }`；
  - :22-62 再按需压 `LevelUpMenu`、多个 `Billboard`（升级）；
  - :126-135 `if (endOfNightMenus.Count > 0) { showingEndOfNightStuff = true; activeClickableMenu = endOfNightMenus.Pop(); }`
    **:136-139 `else { showingEndOfNightStuff = true; activeClickableMenu = new SaveGameMenu(); }`**。
  ⇒ **只要有出货/升级菜单，保存菜单当期就不会被创建**。
- 菜单链的驱动（`Game1._update`，`scratch\il-nd-15.txt`）：:1200-1215 `endOfNightMenus.Count>0 && activeClickableMenu==null`
  ⇒ `activeClickableMenu = endOfNightMenus.Pop()`；:1331-1360 `showingEndOfNightStuff && Count==0 && activeClickableMenu==null`
  ⇒ `newDaySync.destroy(); endOfNightStatus.WithdrawState(); showingEndOfNightStuff=false; _afterNewDayAction(); ReequipEnchantments(); globalFadeToClear(doMorningStuff)`。
  早晨例程结尾**必调 `showEndOfNightStuff()`**（`scratch\il-nd-14.txt:2-48` 的 `<>c.<_update>b__664_0`，IL_00A7），
  `doMorningStuff()` 自身只做 `playMorningSong(false)` + `DelayedAction.functionAfterDelay(<doMorningStuff>b__679_0, 1000)`（`scratch\il-nd-18.txt:2-22`）
  ⇒ 链条的常态是：**关掉日终菜单 → 早晨例程 → 再 showEndOfNightStuff → 这次栈空 → 建 SaveGameMenu → 落盘**。

## 2. 答案②：25→26 那次为什么没进保存

- **M1+M3（出货菜单顶住保存）＝ 有 IL + 真机证据，最可能**：
  那次早晨是**唯一**有出货结算的早晨（`docs\_run5-evidence.md:56-72`：卖 2 个 Geode，`money 14 → 114 = +100g`），
  所以 `displayedShippedItems.Count > 0` ⇒ `showEndOfNightStuff` 压入 `ShippingMenu` 当当前菜单、保存菜单当期不建（上文 IL）；
  真机 20:04:30 `ui={activeMenu:"ShippingMenu", isModal:true, onScreenMenus:4}`、`worldAdvancing:false`（`:76`），
  直到 ~20:05:5x 才由 `scratch\run5-dismiss-modal.py` 关掉（回执 `worldResumed:true`，`:77`）。
- **SMAPI 计数（决定性对照）**：`SMAPI-latest.txt` 里 `Synchronizing 'NewDay' task...` 共 6 次
  （L1077 / L1435 / L2571 / L3204 / L3814 / L5121），其中**只有 L1435（20:04:29，= 出货那次）之后没有任何 save 行**：
  其余 5 次都有 `Context: before save.` → `SaveGame.Save() called.` → `Saving without compression...` → `completed without exceptions.` → `Context: after save, starting …`；
  L1437（20:04:29 的 `task complete.`）之后到 L2571（20:12:00）之间**一条 save 行都没有**，包括关框之后。
  ⇒ 与 IL 完全同向：**没有日终菜单的 5 次跨日全部落盘；有 ShippingMenu 的那 1 次没落盘**。
- **M2（两次睡眠入口不同）排除**：两次探针都走 `answerDialogue`→跨日，SMAPI 两段 `Synchronizing 'NewDay' task...` 都在；
  差别只在"前一天有没有出货"。
- **M4（`newDaySync` 同步位）无直接证据**：`hasSaved/readyForSave` 只在 `SaveGameMenu` 内被读；`flagSaved()` 的唯一调用者
  是 `SaveGameMenu.complete()`（`scratch\il-nd-4.txt:2-28`、`il-nd-5.txt`）⇒ 它不可能是"绕开保存菜单"的原因。
- **仍未解释的一步（未定，不许写成结论）**：按上面的 IL，ShippingMenu 被 `exitThisMenu()` 关掉后
  （`IClickableMenu.exitThisMenu` 基类体见 `scratch\il-nd-18.txt:25-79`；`ShippingMenu.exitThisMenu` 的转储与它**逐字节相同**
  ⇒ ShippingMenu 没覆写、内部只在 `activeClickableMenu==this` 时调 `Game1.exitActiveMenu()`），
  `_update` :1331-1360 应当再跑一遍早晨例程并建出 `SaveGameMenu` → 1~2 秒内应出现 save 行；实际没有。
  我已确认 `Game1` 里**没有任何方法在关框路径上改 `showingEndOfNightStuff`**（该字段在 Game1 的全部访问点：
  `il-nd-16.txt:1151`(Draw)、`12361/12491/12739`(cctor)、`_update` 区），所以"标志位被关框清掉"这条**不成立**。
  剩下两个候选，需要下一步证据：**(a)** 第二遍 `newDaySync.destroy()`（`_update` IL_1225 无 null 检查）之后
  `SaveGameMenu.update` 的 `readyForSave()` 是否恒 false（→ 菜单在但不落盘）；**(b)** 该早晨 `endOfNightMenus`
  里除 ShippingMenu 外还有别的项（观测 `onScreenMenus:4`）导致链条又进了一次 pop，而 Mod 的 `dismiss_modal`
  只关了最上面那个。**下一步只需在下次出货日抓一次 `observe` 序列**（`ui.activeMenu`/`onScreenMenus` 逐秒 + SMAPI save 行）。

## 3. 答案③：判据（"跨日却不落盘"何时是设计、何时是异常）

- **设计内**：跨日成功（`day_after` 恰 +1、`clock` 前进），但当天早晨出现日终菜单（`ShippingMenu`＝前一天有货进箱 /
  `LevelUpMenu` / `Billboard`）⇒ 保存被**按设计推迟**；此时"存档 size/mtime 未前进"**既不能判失败、也不能判通过**。
- **异常**：**没有任何**日终菜单（`ui.activeMenu` 一直 null、`onScreenMenus` 正常），SMAPI 却缺
  `Context: before save.` / `SaveGame.Save() called.`，且存档未动 ⇒ 是真缺口，按第 2 节候选继续查。
- 可写进验收口径的一句：**"跨日"与"落盘"是两件事**；落盘证据必须来自 SMAPI 的
  `SaveGame.Save() called.`（或存档 size/mtime 前进），而**有出货的次日早晨要单独标注**，不能一律当成功/失败
  （`docs\_run5-evidence.md:83` 的结论这一条站得住；`:80` "是游戏自己跳过了保存"这一句按本文应改为"**保存被出货菜单推迟，且关框后仍未落盘，原因未定**"）。

## 4. 未定清单

- **U1** `Game1.exitActiveMenu()` 的完整体（`_update` 之外的菜单清理语义）——我只确认它不碰 `showingEndOfNightStuff`。
- **U2** `newDaySync.destroy()` 之后再调 `readyForSave()` 的返回值（`NetReady` 在单机被 destroy 后的行为）。
- **U3** 是否存在 `b__802_0` 之外的 `new SaveGameMenu()` 创建点：`FIND` 看不见 `.ctor` 调用（方法名不含类型名），
  所以只能说"可定位的唯一创建点"。
- **U4** `saveOnNewDay` 是否有 Game1/SaveGame 之外的写入者（`FIND` 看不见字段写；`FINDSTR` 对字面量恒 0）。

## 5. 复核命令（只读）

```powershell
# IL：保存链
python scratch\_probe_il.py scratch\il-nd-4.txt  "StardewValley.Menus.SaveGameMenu|*" "StardewValley.SaveGame|*" "StardewValley.NewDaySynchronizer|*" "FIND|SaveGameMenu" "FIND|saveFarmhands"
python scratch\_probe_il.py scratch\il-nd-10.txt "StardewValley.SaveGame+<Save>|MoveNext" "StardewValley.SaveGame+<getSaveEnumerator>|MoveNext"
python scratch\_probe_il.py scratch\il-nd-12.txt "StardewValley.Game1+<>c|<showEndOfNightStuff>b__802_0"
python scratch\_probe_il.py scratch\il-nd-15.txt "StardewValley.Game1|_update"
python scratch\_probe_il.py scratch\il-nd-18.txt "StardewValley.Game1|doMorningStuff" "StardewValley.Menus.IClickableMenu|exitThisMenu"
# 日志：save 行对照
Select-String -Path "$env:APPDATA\StardewValley\ErrorLogs\SMAPI-latest.txt" -Pattern "Synchronizing '(NewDay|Save)' task|Context: before save|SaveGame\.Save\(\) called|after save, starting"
```
