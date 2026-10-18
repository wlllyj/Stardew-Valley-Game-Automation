# IL 取证：非提问对话的"真点击推进"到底是哪条原语（task-228）

> 结论先行：**唯一正确的推进原语 = `StardewValley.Menus.DialogueBox.receiveLeftClick(0, 0, true)`**。
> 游戏自己把"左键点击 / 右键 / 动作键"全部导到它；不能用 `closeDialogue()`（那是跳句），
> 也不能用 `Game1.pressActionButton(...)`（它会替玩家应答提问、并伪造输入边沿）。
>
> 取证方法：`tools\il-probe\bin\Release\Probe26.exe "<游戏目录>" "<Type>|<Method>" "FIND|<method>"`，
> 转储是 UTF-16LE，用 `python scratch\_t204_conv.py in.txt out-u8.txt` 转 UTF-8 再读。
> 证据文件：`scratch/t228-il-1-u8.txt` … `t228-il-4-u8.txt`（只读取证，未运行游戏）。
> 方法学参照 `docs/_il-furnace-recipe.md` 头部。

## 0. 事故背景（为什么需要这个技能）

真机事故：Clint 送熔炉配方的**事件**触发后，过场是**非提问对话**、停在第一句等点击
⇒ `ui.eventUp = true` + `liveness.worldAdvancing = false`，无人值守时**永久挂住**。
此前的应急手段是 `dismiss_modal` → `DialogueBox.closeDialogue()`，它会**直接退出对话**、
跳掉剩余句子（本次抢救就是它）—— 属应急，**不能当推进**：事件脚本会因此停在半截，
后续剧情/奖励逻辑不执行。

用户授权边界（原文）：**只推进非提问对话，永不替游戏选选项**。

## 1. `DialogueBox.receiveLeftClick(Int32 x, Int32 y, Boolean playSound)`

`scratch/t228-il-1-u8.txt:1-614`（public override）。

| IL 偏移 | 行为 | 对自动化的意义 |
| --- | --- | --- |
| `IL_0000-0006` | `if (this.transitioning) return;` | 过场动画期调用是**空操作** ⇒ 必须跨 tick 等 |
| `IL_000B-0033` | `if (characterIndexInDialogue < getCurrentString().Length - 1) { characterIndexInDialogue = getCurrentString().Length - 1; return; }` | **第一次点击只"补完打字"**，不换句 ⇒ 一次调用 ≠ 前进一句 |
| `IL_0034-003D` | `if (safetyTimer > 0) return;` | 防连点；太快的第二次点击是空操作 |
| `IL_003E-0044` | `if (isQuestion)` ⇒ 提问分支 | **会替玩家应答**（见下）⇒ 调用前必须拦掉提问 |
| `IL_0177-0196` | 非提问且 `characterDialogue == null`（事件脚本对话框）：`dialogues.RemoveAt(0); if (dialogues.Count == 0) closeDialogue();` | 事件对话的正常推进/收尾路径 |
| `IL_0231+` | 非提问且 `characterDialogue != null`（NPC 对话）：`exitCurrentDialogue()` → `isDialogueFinished()` → `prepareCurrentDialogueForDisplay()`/`beginOutro()` | NPC 对话推进 |
| `IL_0352-0396` | `setUpIcons(); safetyTimer = IsDedicatedHost ? 0 : 750; if (getCurrentString() != null && getCurrentString().Length <= 20) safetyTimer -= 200;` | **非专用主机两次有效调用至少隔 750ms（短句 550ms）** |

提问分支（`IL_003E-012F`，**必须避开**）：
`if (selectedResponse == -1) return;` → `questionFinishPauseTimer = eventUp ? 600 : 200` →
`transitioning = true` → `chooseResponse(responses[selectedResponse])` →
`answerDialogue(lastQuestionKey, selectedResponse)` → `tryOutro()`。
⇒ 未选任何选项时它**什么都不做**（不会误答）；但一旦有选中项就等价于点确认
⇒ 我们**永远不能让提问走到这条分支**（调用前 `isQuestion` ⇒ fail-closed 返回）。

## 2. 备选原语逐条否掉

### 2.1 `Game1.pressActionButton(KeyboardState, MouseState, GamePadState)` —— 不选

`scratch/t228-il-1-u8.txt:615-2447`：

1. `dialogueUp` 且 `isQuestion` ⇒ 直接 `chooseResponse` + `answerDialogue` ⇒ **替游戏选**（越权）。
2. 非提问分支驱动 `Game1.currentSpeaker.CurrentDialogue` 栈（NPC 对话老路径），**不推进事件脚本**。
3. 尾部 `Game1.currentEvent?.receiveActionPress((int)x, (int)y)`；而
   `Event.receiveActionPress(Int32, Int32)`（`t228-il-2-u8.txt:2-109`）只有
   `playerControlSequenceID` 的 `haleyBeach` / `haleyBeach2` 两个特例（调 `Game1.currentLocation.performAction`），
   **不推进对话**。
4. 它会改写 `Game1.oldKBState` / `oldMouseState` / `oldPadState`（伪造输入边沿）并触发
   吃食物/用工具等副作用 ⇒ 与"只推进对话"的最小作用面原则冲突。

### 2.2 `DialogueBox.receiveRightClick(x, y, playSound)` —— 等价别名，不是独立原语

`scratch/t228-il-4-u8.txt:2-10`：

```
IL_0000: ldarg.0
IL_0001-0003: x, y, playSound
IL_0004: callvirt Void receiveLeftClick(Int32, Int32, Boolean)
IL_0009: ret
```

⇒ 它只是转发。**选 receiveLeftClick 作为唯一原语，不必再叠一层。**

### 2.3 `DialogueBox.receiveKeyPress(Keys)` —— 游戏自己的映射，佐证选型

`scratch/t228-il-4-u8.txt:12-60`：

* `Options.SnappyMenus && !isQuestion && key ∈ Options.menuButton` ⇒ `receiveLeftClick(0, 0, true)`；
* `!Options.gamepadControls && key ∈ Options.actionButton` ⇒ `receiveLeftClick(0, 0, true)`。

⇒ **游戏自己就把"菜单键/动作键推进"实现成 `receiveLeftClick(0,0,true)`**，这正是我们选它的直接依据；
但我们**不注入按键**（`receiveKeyPress` 还带 `eventUp` 提问分支与输入系统副作用），直接调原语更窄。

### 2.4 `DialogueBox.closeDialogue()` —— 跳句，禁止当推进

`scratch/t228-il-1-u8.txt:2457+`：

```
IL_0000-000B: if (activeClickableMenu == this)
IL_0010: exitActiveMenu()
IL_0015-0016: dialogueUp = false
（后续：NPC 对话栈清理 / 动画等）
```

⇒ **立即退出、跳掉剩余句子**。事件脚本停在半截、`eventUp` 消失但剧情未走完
⇒ 只能作为"救不回来时解除阻塞"的应急路径（`dismiss_modal` 现状），**不作为推进**。

【真机教训（task-226 / machine-runner `d1e085a`）】`closeDialogue()` 会**跳过该句的显示时机**，
而事件脚本里挂在后面的效果（例如 `addCraftingRecipe`）仍会执行 —— 看起来"事也办了"，
但**对话语义丢了**：玩家/日志看到的剧情被截断，且事件脚本里依赖"这句被看到"的分支
（例如同一事件里的后续 `pause`/`question` 编排）会走错。所以它只能是应急，
`advance_dialogue` 必须走 `receiveLeftClick` 把每一句真的翻过去。

### 2.5 `DialogueBox.clicked` / `DialogueBox.gotClick` —— 1.6.15 不存在

`scratch/t228-il-1-u8.txt` 中两处均 `(未找到)` ⇒ 不作为候选。

### 2.6 真点击入口对照（证明 receiveLeftClick 是正路）

`FIND|receiveLeftClick`（`scratch/t228-il-3-u8.txt`）：

* `Game1.updateActiveMenu` / `Game1.updateTextEntry` → `IClickableMenu.receiveLeftClick`
  ⇒ 玩家真实鼠标点击就是走这条；
* `DialogueBox.receiveRightClick` / `DialogueBox.receiveKeyPress` → `receiveLeftClick(0,0,true)`
  ⇒ 游戏自己把右键/按键也归到这里。

⇒ 我们的调用与"玩家点一下"同一条路径、同一个入口，只是坐标取 `(0,0)`（非提问分支不使用坐标）。

## 3. 据此定下的实现口径

技能 `advance_dialogue`（跨 tick）：

1. **每次调用前 fail-closed**（顺序固定）：
   * `Game1.activeClickableMenu` 不是 `DialogueBox` ⇒ `no_dialogue`；
   * `box.isQuestion`（或 `responses` 非空）⇒ `is_question`（**一次都不点**）；
   * `Game1.activeClickableMenu is LevelUpMenu` 且 `professionsToChoose` 非空 ⇒ `professions_pending`；
   * `Game1.eventUp == false` ⇒ `event_not_running`（本技能只服务事件对话）。
2. **点击 → 等 → 再点**：每次 `receiveLeftClick(0, 0, true)` 之后，跨 tick 等
   `transitioning == false` 且 `safetyTimer <= 0`，并额外等 `safetyGap + 50ms`
   （`safetyGap = 750`，`getCurrentString().Length <= 20` 时 `550`）——否则下一次点击是空操作。
3. **判据 = 观测差分**：点击前后比较 `DialogueBox` 实例、`getCurrentString()` 文本、
   `characterIndexInDialogue`（"补完打字"算 progress），任一变化 ⇒ 计 `stepped`；
   一次点击后三者都没变且无 waiting ⇒ `advance_stalled`（fail-closed，不静默空转）。
4. **有界**：单次调用最多 `maxSteps`（卡面 1..10，默认 1）；总量由脑侧控制（每轮 ≤10 步、每天 ≤60 步）；总时长受 `ClampTimeoutFor` 约束
   （默认 60000ms）。任何失败都带 `before/after {eventUp, menuText, isQuestion}` 便于审计。
5. **事件 `pause` 不是卡死**：事件脚本里有 `pause` 命令（真机实测，`pause 8000` 这类），
   期间对话文本不变是**正常**的。因此"单步之后文本没变"**不能立刻判 `advance_stalled`**：
   * 每次无变化后隔 **≥3.0s** 再点一次（`StallRetryGapMs=3000`），最多重试 **2 次**
     （即同一处最多 3 次点击）；
   * 成功判据**包含** `activeMenuText` 变化与 `eventUp` 变化（不只是 `getCurrentString()` 文本）；
   * 三次都没有任何变化 ⇒ 才 `advance_stalled`。
6. **每步都带"世界有没有变"的警告字段**：回执带 `stalled:true/false` 与
   `worldSeqBefore`/`worldSeqAfter`；脑侧守卫看到 `stalled` **连续 2 次** ⇒ 该事件停止推进、
   `event_blocked` 诚实收尾（**不许**再靠人工计时抢救）。
7. **不新增 journal 事件名**：脑侧成功推进复用既有 `modal_dismissed`（`kind="dialogue_advance"`），
   失败/预算耗尽复用既有 `event_blocked`（`eventUp` 诚实收尾），避免 analyzer 机械枚举漂移。

## 4. 真机冒烟（装 0.7.39 后由 machine-runner 执行）

1. 触发一个非提问事件对话（例如 Clint 送熔炉配方事件）；
2. 发 `advance_dialogue{maxSteps:10}` ⇒ 期望 `ok=true`、`status="ok"`、`stepped>0`，
   观测 `ui.eventUp` 最终变 `false`、`liveness.worldAdvancing` 恢复 `true`；
3. 反例：遇到提问（`ui.dialogueIsQuestion=true`）⇒ 期望 `ok=false`、`status="is_question"`、
   **世界未被替玩家应答**（`activeClickableMenu` 仍是同一个 `DialogueBox`）；
4. 反例：`eventUp=false` 时调用 ⇒ `event_not_running`；
5. 失败/挂住时把回执 `before/after` 原样贴回来（这是审计链）。
