# `_il-shipmenu-save.md` — 出货菜单被谁推进到保存：IL 定案

姊妹篇：`docs\_il-newday-save.md`（task-47：日切保存链的入口与前置）。本篇只回答**出货日**为什么会"菜单没了、保存也没了"。
证据文件：`scratch\il-nd-4.txt`、`scratch\il-nd-10.txt`、`scratch\il-nd-12.txt`、`scratch\il-nd-15.txt`、`scratch\il-sm-2.txt`、`scratch\il-sm-3.txt`、`scratch\_api_ship_out.txt`。工具：`tools\il-probe`（IL）+ `scratch\_api_ship\ApiShip.exe`（可见性，只读反射）。

---

## 0. 一句话结论

`SaveGameMenu`（保存的唯一载体）在 1.6.15 里只有**两个**创建点：

1. `Game1.showEndOfNightStuff()` 的 **`endOfNightMenus.Count == 0`** 分支（`activeClickableMenu = new SaveGameMenu()`）；
2. **`ShippingMenu.update()` 内部**：`if (!savedYet && saveGameMenu == null) saveGameMenu = new SaveGameMenu();`（`saveGameMenu` 是 `ShippingMenu` 的**私有字段**）。

出货日 `displayedShippedItems.Count > 0` ⇒ `showEndOfNightStuff` 先 `Push(new ShippingMenu(...))` ⇒ 第 1 条走不到，**唯一入口变成第 2 条**，而它的前置是 `outro == true`，`outro` 只由 **`ShippingMenu.okClicked()`（private，玩家点 OK）** 置位。

我们 `mod\AgentFarm.Bridge\ModalDismiss.cs:106` 走的是 `menu.exitThisMenu()` ⇒ `outro` 永远 false ⇒ `SaveGameMenu` 永不创建 ⇒ `SaveGame.Save()` 一次不执行；`Game1._update` 的"日终结束"分支只要求 `showingEndOfNightStuff && endOfNightMenus.Count == 0 && activeClickableMenu == null`，**不检查 `newDaySync.hasSaved()` / `saveOnNewDay`** ⇒ 照样 `newDaySync.destroy()` + `_afterNewDayAction()` + 淡出到早晨 ⇒ **日推进、盘不落**。

---

## 1. 观测事实（Lead 复核过的输入 + 我补的账本行号）

- `logs\run9-smapi-window.txt`：`Synchronizing 'NewDay' task` 4 次（L997 / L1887 / L3003 / L4532），`Context: before save.` **0**、`SaveGame.Save() called.` **0**、`Synchronizing 'Save' task` **0**、`completed without exceptions` **0**、`after save, starting` **0**。
- 存档 `Wahaha_450799035` 起止同 size/mtime（`3706657 B / 2026-10-15 22:22:57.011`）。
- `logs\longrun-3day-llm-run9.jsonl`（行号）：L2 `sell ok`(t=0.25, `why=need_slot`)、L15 `sell ok`(t=84.69)、**L365 `sleep ok`（已跨日 summer 13→14，已踩触发格 (10,9)）** → L369 `day_end ended_by=stuck` → **L371 `goto_farm{where:"day_start"} ok=false`（回执 `ui_modal`）** → **L372 `modal_dismissed{menu:"ShippingMenu"}`** → L373 `sell ok`(t=228.63, `why=need_slot`)；同一序列再出现在 L450→L457、L602→L610、L973→L981。
- 对照：run7 无 `sell/buy/ship` ⇒ 7 NewDay / 7 before save / 7 Save called 全配对；run8 有出货 ⇒ 2 NewDay / 1 save（缺的那天正是有出货的那天）。

⇒ 相关性 = 因果，IL 侧已闭合（第 2 节）。

---

## 2. 机制（逐条 IL）

### 2.1 菜单入列（`showEndOfNightStuff` 的 lambda）

`StardewValley.Game1+<>c.<showEndOfNightStuff>b__802_0()`（`scratch\il-nd-12.txt:2-141`）：

- IL_000C-0047：`if (player.displayedShippedItems.Count > 0) { endOfNightMenus.Push(new ShippingMenu(displayedShippedItems)); displayedShippedItems.Clear(); shipped = true; }`
- IL_0048-00C3：`if (newLevels.Count > 0 && !shipped) endOfNightMenus.Push(new LevelUpMenu())`；随后每条 newLevel 再 `Push(new Billboard(x, y))`。
- IL_01A9-01DC（**收尾二选一**）：
  - `if (endOfNightMenus.Count > 0) { showingEndOfNightStuff = true; activeClickableMenu = endOfNightMenus.Pop(); }`
  - `else { showingEndOfNightStuff = true; activeClickableMenu = new SaveGameMenu(); }` ← **创建点 1**（IL_01D2 `newobj Void .ctor()`）。`Game1.endOfNightMenus` = `Stack<IClickableMenu>`（public static，`scratch\_api_ship_out.txt:93`）。

### 2.2 `ShippingMenu` 自己驱动保存（创建点 2）

`ShippingMenu.update(GameTime)`（`scratch\il-sm-2.txt:354-553`）：

- IL_0000-0014：`base.update(time)`；IL_0019-003C：`if (!_activated) { _activated = true; player.team.endOfNightStatus.UpdateState("shipment"); }`
- IL_0041-0058：`if (_hasFinished) { if (Game1.PollForEndOfNewDaySync()) { exitThisMenu(false); return; } return; }`
- **IL_0059-008D：`if (saveGameMenu != null) { saveGameMenu.update(time); if (saveGameMenu.quit) { saveGameMenu = null; savedYet = true; } }`** ← 保存就是在**它的 update 里**跑的。
- IL_00CC-0100：`if (outro) { if (outroFadeTimer > 0) { outroFadeTimer -= dt; … } }`（**outro 为 false 时整段跳过**）
- IL_018A-01C4：`outroPauseBeforeDateChange` 倒计时到 0 ⇒ `newDayPlaque = true`（换日铭牌动画）
- **IL_0231-024C：`if (!savedYet && saveGameMenu == null) saveGameMenu = new SaveGameMenu();`** ← **创建点 2**（`scratch\il-sm-2.txt:550-552`）
- IL_024D-0289：`if (finalOutroTimer > 0 && savedYet) { finalOutroTimer -= dt; if (finalOutroTimer <= 0) _hasFinished = true; }`

`ShippingMenu.okClicked()`（**private**，`scratch\il-sm-3.txt:2-31`）：

```
outro = true;
outroFadeTimer = 800;
Game1.playSound("bigDeSelect");
Game1.changeMusicTrack("none", false, MusicContext.Default);
```

只有 `receiveLeftClick` 在「`CanReceiveInput()`、`!savedYet`、`currentPage == -1`、`introTimer <= 0`、`okButton.containsPoint(x,y)`」全真时才调它（`scratch\il-sm-3.txt` IL_0009-004D）。

⇒ 玩家点 OK 后的有界序列：`okClicked()` → 800ms 淡出 → 铭牌下移 → 700ms 停顿 → `new SaveGameMenu()` → 每帧 `saveGameMenu.update()` ⇒ **`SaveGame.Save()`**（master + `saveOnNewDay` + `readyForSave()`，见 `_il-newday-save.md` §1）→ `quit` ⇒ `savedYet = true` → 2000ms → `_hasFinished = true` → `PollForEndOfNewDaySync()` ⇒ **`exitThisMenu(false)`**（游戏自己关，`playSound=false`）。

### 2.3 天气/日终结束（为什么"不保存也能进早晨"）

`Game1._update`（`scratch\il-nd-15.txt`）：

- IL_1018-105A（:1198-1215）：`if (local12) { if (endOfNightMenus.Count > 0 && activeClickableMenu == null) { activeClickableMenu = endOfNightMenus.Pop(); if (SnappyMenus) snapToDefaultClickableComponent(); } }`（`local12` = `IsMultiplayer() || currentMinigame == null || currentMinigame.doMainGameUpdates()`，单机恒真）
- **IL_120B-127C（:1331-1360）：`if (showingEndOfNightStuff && endOfNightMenus.Count == 0 && activeClickableMenu == null) { newDaySync.destroy(); player.team.endOfNightStatus.WithdrawState(); showingEndOfNightStuff = false; _afterNewDayAction?.Invoke(); player.ReequipEnchantments(); globalFadeToClear(doMorningStuff); }`**
- `_update` 里**没有**任何 `showEndOfNightStuff` 调用 ⇒ 栈空了以后不会"补建" SaveGameMenu。

⇒ 只要有人在 `okClicked()` 之前把 ShippingMenu 抽走（`exitThisMenu()`/`emergencyShutDown()`/`Game1.exitActiveMenu()`），栈就空了、菜单也没了 ⇒ IL_120B 直接当"日终菜单都结束了"处理：**`newDaySync.destroy()` + 进早晨，保存步骤从未发生，也没有任何闸门会发现**。

---

## 3. 我们现有代码错在哪一行

`mod\AgentFarm.Bridge\ModalDismiss.cs:104-111`（情况 2，非 `DialogueBox` 模态）：

```csharp
// ---- 情况 2：其它任何模态 → exitThisMenu()（等价按 Esc）----
try { menu.exitThisMenu(); } catch { }      // ← 第 106 行：这里
```

对 `ShippingMenu` 而言 `exitThisMenu()` ≠ "玩家按 OK"：它只调基类 `IClickableMenu.exitThisMenu(Boolean)`（`scratch\_api_ship_out.txt:73`；`ShippingMenu` **没有**覆写它 —— 其转储与基类逐字节相同，见 `_il-newday-save.md` §2.5），内部顺序是 `behaviorBeforeCleanup?.Invoke` → `cleanupBeforeExit()` → `Game1.exitActiveMenu()` → `exitFunction?.Invoke()`，**完全不碰 `outro`/`saveGameMenu`**。

⇒ run9 每次 `modal_dismissed{menu:ShippingMenu}`（L372/L457/L610/L981）都是这一次错误关闭：**菜单没了、保存也没了**。同一份实现也被 `SleepSkill` 共用（`ModalDismiss.CloseDialogueBox`），所以修一处即两处受益。

---

## 4. 正确做法（有界、零鼠标）

**(A) 首选：反射点 OK（让游戏自己保存并关框）**

```csharp
if (menu is StardewValley.Menus.ShippingMenu ship)
{
    var mi = typeof(StardewValley.Menus.ShippingMenu)
        .GetMethod("okClicked", BindingFlags.Instance | BindingFlags.NonPublic);   // private，见 _api_ship_out.txt:60
    mi?.Invoke(ship, null);        // 之后：不许再 exitThisMenu()/emergencyShutDown()，等游戏自己关
    return Finish(true, "ok", "已点出货菜单 OK（okClicked）⇒ 等游戏自己保存并关框");
}
```

- 代价：反射一个 private 方法（本 Mod 已有先例：`BuySkill.cs:280-305` 反射 `ShopMenu.tryToPurchaseItem`）。
- 有界等待：`okClicked()` 之后保存链最长约 `800ms + 铭牌动画 + 700ms + 保存 + 2000ms`（run7 实测一次保存约 2s）⇒ 给 **8s** 上限轮询 `Game1.activeClickableMenu` 不再是这个 ShippingMenu；期间**不得**再发任何 move/exec。

**(B) 兜底：用公开 API 点 OK 按钮**（若不想反射 private）

```csharp
if (ship.currentPage == -1 && ship.CanReceiveInput())        // public，_api_ship_out.txt:15/:53
    ship.receiveLeftClick(ship.okButton.bounds.Center.X,      // okButton public，:31
                          ship.okButton.bounds.Center.Y, true);
```

注意 `receiveLeftClick` 在 `introTimer > 0` 时会**静默什么都不做**（`introTimer` 是 private，读不到）⇒ 必须"重试直到菜单消失"，不能只点一次。

**(C) 工程护栏（无论 A/B 都要有）**

- `brain` 的模态策略把 `ShippingMenu` 当**只能等/只能点 OK**（`brain\agentfarm\longrun.py` 的 `MODAL_WAIT_ONLY` 目前只含 `SaveGameMenu`…（`NewDaySavingMenu` 在 1.6.15 已不是类型名，见 `_api_ship_out.txt:117`））；**任何情况下都不许对 `ShippingMenu`/`SaveGameMenu` 调 `exitThisMenu()`/`emergencyShutDown()`**（后者会走同一段基类代码）。
- 白天看到 ShippingMenu 说明**已经跨日**：先等保存完成（`Game1.IsSaving` public、`Game1.newDaySync.hasSaved()` public、`Game1.saveOnNewDay` public），再继续任何动作。

### 4.1 判据（写死，可外部验收）

关闭动作发出后，必须同时满足：

1. SMAPI 日志出现**各一次**：`Context: before save.` → `SaveGame.Save() called.` → `Saving without compression...` → `SaveGame.Save() completed without exceptions.` → `Context: after save, starting <下一天>`；
2. 存档主文件 size/mtime **前进**（run7 有、run9 无）；
3. 期间 `activeClickableMenu` 由 ShippingMenu → 自己消失（不需要我们再关），且 `newDaySync` 完成。

任一条不满足 ⇒ 按"保存链被掐断"记 **problem**（不许当成功）。

---

## 5. `saveOnNewDay` / `newDaySync` 的角色（回答"NewDay 完成却不保存"）

- `newDaySync` 只是**多人就绪/已保存的同步位**：`readyForSave()`/`flagSaved()`/`hasSaved()`（`scratch\il-nd-5.txt`）。`flagSaved()` 的**唯一**调用者是 `SaveGameMenu.complete()`（`scratch\il-nd-4.txt:2-28`）⇒ **没有 SaveGameMenu 就没有 `saved` 标记**。
- 但 `Game1._update` 的日终结束分支（IL_120B）**并不读** `hasSaved()`；它只要求"夜菜单栈空 + 没有活动菜单"。`_newDayAfterFade` 协程也不负责保存（`_il-newday-save.md` §1）。⇒ `Synchronizing 'NewDay' task...` 完成 = **日期/地点已推进**，与"是否落盘"完全解耦；run9 的 4 次 NewDay 因此全部无 save。
- `saveOnNewDay`（public static，`_api_ship_out.txt:98`）是 `SaveGameMenu.update` 的门闸（false ⇒ 只 `complete()` 不写盘），本事故与它无关（未定：谁会置 false 仍未查到写点，见 `_il-newday-save.md` U4）。

---

## 6. 未定项

- U1：`ShippingMenu` 是否还有**其它**创建 `SaveGameMenu` 的路径（构造器调用不是方法名，`FIND` 查不到；本次只定到两个创建点：`b__802_0` IL_01D2 与 `ShippingMenu.update` IL_0241）。**未定**，但两个点的语义已足够解释 run7/8/9。
- U2：`okClicked()` 的反射调用在菜单处于 intro 动画中是否会留下视觉/状态残留（`introTimer > 0`）——按 IL 应无副作用（它只置 `outro/outroFadeTimer` 与播放音效），**真机未验证**。
- U3：`exitThisMenu(true)`（我们现在的默认参数）与游戏自己用的 `exitThisMenu(false)` 只差音效；与本事故无关（已定）。

---

## 7. 这算不算 0.7.29 的放行条件 —— **算，而且是最高优先**

理由（每条都可复核）：

1. **落盘是"连续 3 个游戏日"验收的唯一外部证据**：run9 的 5 天在磁盘上零痕迹（start==end），run10/run9b 若还这样跑，等于白跑。
2. **失败是确定性的、且由新功能放大**：只要当天出过货（`sell/surplus_sell` 现在每天都做）就必然走 ShippingMenu 分支；run7 无出货 ⇒ 7/7，run8 有出货 ⇒ 缺 1 次，run9 每天出货 ⇒ 0/4。相关性已被 IL 机制解释。
3. **是我们自己的 `dismiss_modal` 掐断的**，不是游戏限制 ⇒ 修得动、且修法很小（一处分支 + 等待）。
4. 修复有**硬判据**（SMAPI 五个 save 行 + 存档 mtime 前进），可以在一次真机上低成本验证，不需要整天 run。

建议顺序：先落 (A)+ (C) 的 Mod 侧改动 → 单日真机验证判据（含 `save` 行与存档 mtime）→ 再跑 run10 全量；`dismiss_modal` 对 ShippingMenu 的新路径要有**专门的验收记录**（回执里带 `save` 证据），否则 run10 的"3 日连续"仍然不可信。

---

## 8. 复核命令（只读）

```powershell
# 1) 可见性（public/private 权威）
dotnet build "scratch\_api_ship\ApiShip.csproj" -c Release -v q
& "scratch\_api_ship\bin\Release\net6.0\ApiShip.exe" > scratch\_api_ship_out.txt

# 2) IL：ShippingMenu 交互/驱动 + okClicked + 日终结束分支
python scratch\_probe_il.py scratch\il-sm-2.txt "StardewValley.Menus.ShippingMenu|receiveLeftClick" "StardewValley.Menus.ShippingMenu|update" "StardewValley.Menus.ShippingMenu|exitThisMenu" "StardewValley.Menus.ShippingMenu|cleanupBeforeExit"
python scratch\_probe_il.py scratch\il-sm-3.txt "StardewValley.Menus.ShippingMenu|okClicked" "StardewValley.Game1|PollForEndOfNewDaySync" "StardewValley.Menus.ShippingMenu|receiveLeftClick"

# 3) 账本证据（run9：出货→关框→无 save）
python -c "import io,json;[print(i,l[:120]) for i,l in enumerate(io.open(r'logs\longrun-3day-llm-run9.jsonl',encoding='utf-8'),1) if '\"modal_dismissed\"' in l or '\"event\": \"sleep\"' in l]"
```

---

**姊妹篇交叉引用**：入口与前置（`newDaySync`/`readyForSave`/`saveOnNewDay`、`SaveGame.Save()` 的两个迭代器体、`Game1.endOfNightMenus` 空栈建 SaveGameMenu 的设计）见 `docs\_il-newday-save.md`；本篇补充其"§2.5 反例"的**根因**：那次关框之所以永久掐断保存链，是因为出货日保存的唯一入口在 `ShippingMenu.update` 里，而它只认 `okClicked()`。
