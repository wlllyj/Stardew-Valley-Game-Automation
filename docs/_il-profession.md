# LevelUpMenu 职业选择能否被程序安全驱动（task-21 取证）

> 取证对象：`Stardew Valley.dll`，`Stardew Valley, Version=1.6.15.24356`（Steam 正式版）。
> 方式：静态 IL 反汇编 + 反射成员清单 + **对程序集自身的只读反射调用**（没有启动游戏、没有碰桥、没有改任何生产代码）。

## 0. 一句话结论

**能无人值守安全驱动，但只有两条路，且都不是"点 OK / 按 Esc"。** 推荐**状态注入路线**（读候选 → 直接往 `Farmer.professions` 写选中职业 → 关菜单），它完全不依赖光标与 OS 输入；几何点击路线也可行且不需要硬编码像素，但要求"真实光标 + 真实新按下"。
用户口径已被程序集自身确证：**耕种 5 级 Tiller = id 1，10 级 Artisan = id 4**。

---

## 1. 取证环境与复跑命令

游戏目录 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`；程序集 `Stardew Valley, Version=1.6.15.24356`。

```powershell
# 反射成员清单（自建探针，见 scratch\profession-probe\）
scratch\profession-probe\bin\Release\net6.0\ProfessionProbe.exe <gameDir> <outFile> `
    "StardewValley.Menus.LevelUpMenu" "StardewValley.Farmer|profession,newLevels,experiencePoints,skill"

# 直接问程序集要 id→名字（本次新增的 INVOKE 能力）
... ProfessionProbe.exe <gameDir> scratch\profession-names.txt `
    "INVOKE|StardewValley.Menus.LevelUpMenu|getProfessionName|1"

# IL（tools\il-probe，注意输出必须经 scratch\run_il_probe.py 落盘为 UTF-8）
python scratch\run_il_probe.py scratch\il-update.txt "StardewValley.Menus.LevelUpMenu|update"
python scratch\run_il_probe.py scratch\il-ctor.txt "StardewValley.Menus.LevelUpMenu|.ctor" `
    "StardewValley.Menus.IClickableMenu|readyToClose" "StardewValley.Menus.IClickableMenu|exitThisMenu" `
    "StardewValley.Farmer|getProfessionForSkill"
python scratch\run_il_probe.py scratch\il-mouse.txt "StardewValley.Game1|getMouseX" "StardewValley.InputState|GetMouseState"
```

| 证据文件 | 内容 |
| --- | --- |
| `scratch\reflect-members.txt` | LevelUpMenu 全量成员 + Farmer 关键词成员（含可见性/泛型友好名） |
| `scratch\il-levelup-named.txt` | 按方法名精确 IL：getProfessionName / getProfessionTitleFromNumber / getProfessionDescription / getImmediateProfessionPerk / removeImmediateProfessionPerk / okButtonClicked / receiveLeftClick / receiveKeyPress / applyMovementKey / performHoverAction / RemoveLevelFromLevelList / AddMissedProfessionChoices / RevalidateHealth / CanReceiveInput / RepositionOkButton / getLevelPerk / cleanupBeforeExit |
| `scratch\il-update.txt` | `LevelUpMenu.update(GameTime)` 全文 + 嵌套 `<>c__DisplayClass47_0` + `FIND` 结果 |
| `scratch\il-ctor.txt` | 两个 ctor + `IClickableMenu.readyToClose/exitThisMenu` + `Farmer.getProfessionForSkill` |
| `scratch\profession-names.txt` | `INVOKE getProfessionName(0..29)` 的 30 条实测结果 |
| `scratch\il-mouse.txt` | `Game1.getMouseX/Y`、`InputState.GetMouseState`（决定"输入能否伪造"） |

探针口径（踩过的坑）：`FIND|名字` 只匹配**方法名**，查字段名必 0 命中；`FINDSTR|字面量` 只搜 IL 字节内联串，而 `ldstr` 走 #US 字符串堆，所以搜 `Tiller`/`Artisan` 也是 0 命中——**两者都是假阴性，不要在结论里引用**。探针也**不解码 `switch` 跳转表**（dump 里 switch 之后那几行是跳转表被当指令反汇编的垃圾）。

---

## 2. 职业 id 表（1.6.15 实测，非文档抄录）

`INVOKE|StardewValley.Menus.LevelUpMenu|getProfessionName|<id>` 逐条调用结果：

| id | 名字 | id | 名字 | id | 名字 |
| --- | --- | --- | --- | --- | --- |
| 0 | Rancher | 10 | Mariner | 20 | Blacksmith |
| **1** | **Tiller** | 11 | Luremaster | 21 | Prospector |
| 2 | Coopmaster | 12 | Forester | 22 | Excavator |
| 3 | Shepherd | 13 | Gatherer | 23 | Gemologist |
| **4** | **Artisan** | 14 | Lumberjack | 24 | Fighter |
| 5 | Agriculturist | 15 | Tapper | 25 | Scout |
| 6 | Fisher | 16 | Botanist | 26 | Brute |
| 7 | Trapper | 17 | Tracker | 27 | Defender |
| 8 | Angler | 18 | Miner | 28 | Acrobat |
| 9 | Pirate | 19 | Geologist | 29 | Desperado |

旁证（口径独立的第二条证据）：`Farmer.getProfessionForSkill(skillType, skillLevel)` 在 `skillLevel == 5` 分支的 `switch (skillType)` 里，case 0 依次 `Contains(0)→return 0`、`Contains(1)→return 1`，case 1 是 6/7，case 2 是 12/13，case 3 是 18/19，case 4 是 24/25（这段是有效 IL，不是跳转表垃圾）→ 与上表每 6 个一组的分组完全一致。

本地化显示名走 `getProfessionTitleFromNumber(int)`：
`Game1.content.LoadString("Strings\UI:LevelUp_ProfessionName_" + getProfessionName(id))`
→ **屏幕上没有英文字面量**，任何"靠屏幕文本匹配 Tiller/Artisan"的做法都不可行。

---

## 3. 候选是怎么决定的（`update` 填充 `professionsToChoose`）

`update(GameTime)` 里（`scratch\il-update.txt` IL_078B–IL_0880）：

```csharp
if ((currentLevel == 5 || currentLevel == 10) && currentSkill != 5) {
    professionsToChoose.Clear();
    isProfessionChooser = true;
    if (currentLevel == 5) {
        professionsToChoose.Add(currentSkill * 6 + 0);
        professionsToChoose.Add(currentSkill * 6 + 1);
    } else {                                  // level == 10
        if (Game1.player.professions.Contains(currentSkill * 6 + 0)) {
            professionsToChoose.Add(currentSkill * 6 + 2);   // 5 级选了"第一个" → 走 +2/+3 支线
            professionsToChoose.Add(currentSkill * 6 + 3);
        } else {
            professionsToChoose.Add(currentSkill * 6 + 4);   // 选了"第二个" → 走 +4/+5 支线
            professionsToChoose.Add(currentSkill * 6 + 5);
        }
    }
    leftProfessionDescription  = getProfessionDescription(professionsToChoose[0]);
    rightProfessionDescription = getProfessionDescription(professionsToChoose[1]);
}
```

**索引 0 = 左框，索引 1 = 右框。** 由此得到本任务最要紧的一张操作表：

| 场景 | 候选（左, 右） | 目标 | 要点 |
| --- | --- | --- | --- |
| 耕种 5 级 | (Rancher 0, **Tiller 1**) | Tiller | **点/选右半区（索引 1）** |
| 耕种 10 级（已选 Tiller 1，未选 0） | (**Artisan 4**, Agriculturist 5) | Artisan | **点/选左半区（索引 0）** |

→ 左右**不是**"好选项恒定在左/右"：5 级要右、10 级要左。这一点如果按固定半边点击就会选错。

---

## 4. 唯一的提交入口：`update` 内的几何判定

### 4.1 精确条件（IL 还原）

```csharp
if (timerBeforeStart > 0) {                   // ctor 里 timerBeforeStart = 250
    timerBeforeStart -= time.ElapsedGameTime.Milliseconds;
    if (timerBeforeStart <= 0 && Game1.options.SnappyMenus) {
        populateClickableComponentList(); snapToDefaultClickableComponent();
    }
    return;                                   // 250ms 内完全不处理选择
}
if (isActive && isProfessionChooser) {
    leftProfessionColor = rightProfessionColor = IClickableMenu.textColor;
    Game1.player.completelyStopAnimatingOrDoingAction();
    Game1.player.freezePause = 100;           // 时钟冻结，世界不推进
    if (Game1.getMouseY() > yPositionOnScreen + 192 && Game1.getMouseY() < yPositionOnScreen + height) {
        if (Game1.getMouseX() > xPositionOnScreen && Game1.getMouseX() < xPositionOnScreen + width / 2) {
            leftProfessionColor = Color.Green;
            if (freshClick()) {                       // 见 4.2
                if (readyToClose()) {                 // IClickableMenu.readyToClose() 恒 true
                    Game1.player.professions.Add(professionsToChoose[0]);   // 返回值被 pop 丢弃
                    getImmediateProfessionPerk(professionsToChoose[0]);
                    isActive = false; informationUp = false; isProfessionChooser = false;
                    RemoveLevelFromLevelList();
                }
            }
        } else if (Game1.getMouseX() > xPositionOnScreen + width / 2 &&
                   Game1.getMouseX() < xPositionOnScreen + width) {
            rightProfessionColor = Color.Green;
            /* 同上，索引换成 [1] */
        }
    }
}
height = 512;                                  // 每条路径都会重设
oldMouseState = Game1.input.GetMouseState();
```

### 4.2 "新按下"的判据

`mouse.LeftButton == ButtonState.Pressed && oldMouseState.LeftButton != ButtonState.Pressed`，或手柄：`Game1.options.gamepadControls && padState.IsButtonDown(Buttons.A=4096) && !oldPadState.IsButtonDown(A)`。`oldMouseState` 每帧末尾被刷成当前值（IL_0555）。

### 4.3 关键结论

- **`receiveLeftClick(x,y,bool)` 与 `performHoverAction(x,y)` 在 LevelUpMenu 里都被重写成空方法**（IL 只有 `ret`）→ 不存在"调用菜单的点击方法就能选"这条路。
- **OK 按钮在选职业状态下被显式忽略**：`IL_0AA1: ldfld isProfessionChooser; IL_0AA7: brtrue -> IL_0B0A`——`okButton.containsPoint(oldMouseX, oldMouseY)` 成立后仍因 `isProfessionChooser` 跳过 `okButtonClicked()`。所以"点 OK"既不会选职业也不会关掉选择页。
- **`receiveKeyPress` 在 `isProfessionChooser` 时吞掉 `options.cancelButton`/`options.menuButton`**（Esc/菜单键无效）；键盘/手柄左右由 `applyMovementKey` 处理（`direction==1/3` 且 `CanReceiveInput()`）。
- **`CanReceiveInput()` = `informationUp && timerBeforeStart <= 0`。**
- 几何值来源：`xPositionOnScreen`、`yPositionOnScreen`、`width`（ctor 里置 960）、`height`（512）——**都是 `IClickableMenu` 的 public 字段**；`x = uiViewport.Width/2 - 384`、`y = uiViewport.Height/2 - 256`。
  `okButton.bounds`（`x+width+4, y+height-64-borderWidth, 64,64`）**与职业选择无关**，只有信息页用；`RepositionOkButton()` 也是同一套来源。→ **不需要任何硬编码像素**。
- 建议点击点（自算，留足余量）：右 = `(x + width*3/4, y + 256)`，左 = `(x + width/4, y + 256)`；`y+256` 位于 `y+192` 与 `y+height` 之间，即使 `height` 稍后被信息面板改大也仍然有效。

---

## 5. 非几何入口评估

| 问题 | 答案 |
| --- | --- |
| 有 `selectProfession(id)` 吗？ | **没有**。反射成员清单无此名；`FIND|selectProfession` 在整个程序集 0 命中（FIND 对方法名可信）。 |
| 有别的 public 选择 API 吗？ | **没有**。`okButtonClicked()` 只调 `getLevelPerk` + `RemoveLevelFromLevelList`，**不加职业**；`AddMissedProfessionChoices(Farmer)` 只"补排队"，也不选职业。 |
| 那能非几何地选吗？ | **能，走状态注入**（下节）。 |

### 路线乙（推荐）：写 `professions` + 关菜单

```csharp
// 1) 先确认真实候选（反射读私有 professionsToChoose，List<int>，长度 2）
//    或按 §3 公式推导：lvl5 → [skill*6+0, skill*6+1]；lvl10 → Contains(skill*6+0) ? [+2,+3] : [+4,+5]
Game1.player.professions.Add(targetId);      // NetIntHashSet，public readonly；Add 返回值游戏自己也丢弃
Game1.activeClickableMenu.exitThisMenu();    // 或 Game1.exitActiveMenu()
```

等价性分析：

- `exitThisMenu(bool)` → `behaviorBeforeCleanup?.Invoke(this)` → `cleanupBeforeExit()`（本类重写）→ `isActive` 为 true 时 `okButtonClicked()` → `getLevelPerk(currentSkill,currentLevel)` + `RemoveLevelFromLevelList()` + `isActive=false; informationUp=false` → 然后 `Game1.exitActiveMenu()`。见 `scratch\il-ctor.txt` IL_0000–IL_005B（`IClickableMenu.exitThisMenu`）与 `scratch\il-levelup-named.txt` IL_0589–IL_0595（`cleanupBeforeExit`）。
- 相对游戏内点击，唯一少做的是 `getImmediateProfessionPerk(id)` 和 `isProfessionChooser=false`。前者实测**只对 id 24/27 有分支**（`24 → maxHealth += 15`、`27 → maxHealth += 25`），然后 `health = maxHealth; stamina = maxStamina`；**Tiller(1)/Artisan(4) 没有任何分支** → 跳过零副作用。后者对已关闭的菜单无意义。（若哪天要选战斗线 24/27，必须自己补 `maxHealth` 或反射调用它。）
- `NetIntHashSet.Add` 的 bool 被游戏 `pop` 掉 → 重复写同一 id 不会二次加成，**幂等**。
- 事后不会被重新排队：`AddMissedProfessionChoices` 的条件是 `GetUnmodifiedSkillLevel(skill) >= 5 && !newLevels.Contains(Point(skill,5)) && getProfessionForSkill(skill,5) == -1`，而此刻 `getProfessionForSkill` 会返回刚写进去的 id。

### 路线甲（几何点击）可行性

可行，但依赖真实输入；且要注意**点击必须发生在 250ms 之后**（否则那一次 new-press 边沿被 `timerBeforeStart` 的早退吃掉，需要重新按下）。`Game1.getMouseX()/getMouseY()` 读的是 `Game1.input.GetMouseState()` 的真实状态（主实例分支直接返回 `_currentMouseState`；只有非主实例才用 `_simulatedMousePosition` 且按钮全 Released）→ **无法在进程内伪造一次"真实点击"**，要么走 OS 级光标/按键，要么走路线乙。

---

## 6. 不可逆性与风险

1. **`RemoveLevelFromLevelList()` 会永久删掉 `newLevels` 里的 `Point(currentSkill,currentLevel)`**（`Game1.player.newLevels.RemoveWhere(p => p == new Point(currentSkill, currentLevel))`）。之后该等级点不会再自动开菜单；若此时职业没选上，唯一的补救是 `LevelUpMenu.AddMissedProfessionChoices(Farmer)`（public static，由 `Game1.fixProblems()` 调用）——掉档可恢复，但**恢复时机不可控**（不是当天必然重开）。
2. **现有桥的 `dismiss_modal` 是危险路径**：`mod\AgentFarm.Bridge\ModalDismiss.cs:104-106` 对"其它任何模态"一律 `menu.exitThisMenu()`；而 `UiRead.ActiveMenuText()` 对 LevelUpMenu 只返回类型名（`mod\AgentFarm.Bridge\UiRead.cs:33-44`）→ 会把职业选择当普通模态关掉 → **静默丢档**。task-18 必须在 `dismiss_modal` 里显式排除 `LevelUpMenu`，或"先选职业再关"。
3. **选错半区 = 选了不想要的职业，不可逆**：`removeImmediateProfessionPerk(id)` 只能回退血上限（24 减 15、27 减 25），**不能撤销选择**；`professions` 虽是可写的 `NetIntHashSet`，游戏没有任何"重选"流程，帧内也没有回滚点。
4. `LevelUpMenu` 是模态：`player.freezePause = 100`、`completelyStopAnimatingOrDoingAction()`，时钟不走 → 等待判据必须用"菜单还在不在"，不能用时间/游戏时钟推进。
5. 250ms 的 `timerBeforeStart` + `CanReceiveInput()` → 菜单出现后立刻操作会无效（不是失败，是被忽略）。

---

## 7. 观测差分验收（选完怎么证明）

现状可用字段（`mod\AgentFarm.Bridge\WorldSnapshot.cs:790/797/801`、`Contracts.cs:478/494`）：`ui.activeMenu`（类型名）、`ui.activeMenuText`（对 LevelUpMenu 仅 `"LevelUpMenu"`）、`ui.isModal`、`ui.onScreenMenus`。

验收三元组（建议 task-18 落地）：

1. `Farmer.professions` 含目标 id（1 或 4）；
2. `Farmer.newLevels` 不再含 `[skill, level]`（证明 `RemoveLevelFromLevelList` 跑过）；
3. `ui.activeMenu` 不再是 `LevelUpMenu`。

**缺失的桥字段（必须新增，否则这条验收做不出来）**：

- `Farmer.professions`：`NetIntHashSet` → `int[]`；
- `Farmer.newLevels`：`NetList<Point, NetPoint>` → `[[skill,level], ...]`（注意**不是 int 列表**）；
- 建议同时上报职业选择上下文，否则"菜单里不是这两个就记 `levelup_profession_unmatched` 并回报菜单文本"这条用户要求**无法满足**（`activeMenuText` 只给类型名）：
  - `professionsToChoose`（私有 `List<int>`，需反射）——**这是最直接、最不会撒谎的候选来源**；
  - 或者 `getProfessionName(id)` / `getProfessionTitleFromNumber(id)`（本地化名）；
  - `leftProfessionDescription` / `rightProfessionDescription`（私有 `List<string>`，来自 `getProfessionDescription(id)`，即 `Strings\UI:LevelUp_ProfessionDescription_*`）。

`Farmer` 侧相关签名（已确认）：`public readonly NetList<Point,NetPoint> newLevels`、`public readonly NetIntHashSet professions`、`public Int32 getProfessionForSkill(Int32 skillType, Int32 skillLevel)`（-1 = 未选）、`public static void AddMissedProfessionChoices(Farmer farmer)`（在 LevelUpMenu 上）、`public static Int32 checkForLevelGain(Int32 oldXP, Int32 newXP)`、`public static Int32 totalLevels`。

---

## 8. 未定项

- **谁在什么时机 `new LevelUpMenu(skill, level)`**：本次未查。`FIND` 只能按方法名匹配，查不了"哪个方法构造了某类型"；已知线索是 `Farmer.newLevels` 非空时游戏会开，且 `Game1.fixProblems()` 会调 `AddMissedProfessionChoices`。task-18 若需要"菜单何时出现"的判据，建议直接轮询 `ui.activeMenu`。
- **中文档位下的职业名与描述文案**：要走 `Game1.content.LoadString`，本次静态取证（未启动游戏）拿不到；但 id 与键名公式已确定。
- **真机验证**：按任务要求未碰游戏（真机由 machine-runner 独占，取证时游戏未开）。所有结论来自程序集静态/反射证据。
- 5 个技能共用同一套左右半区公式（已由 §3 确认），但"每个技能的具体推荐职业"不在本任务范围。

---

## 9. 给 task-18 的一句话口径

出现 `ui.activeMenu == "LevelUpMenu"` → 反射读 `professionsToChoose`；若 `(skill==0 && level==5 && 含 1)` 或 `(skill==0 && level==10 && 含 4)` → `Game1.player.professions.Add(1|4)` → `exitThisMenu()` → 验收三元组；**其余任何候选一律不动**，记 `levelup_profession_unmatched` 并把候选 id/名字（走到本地化名）报给用户人工决定。全程不需要鼠标，且禁止 `dismiss_modal` 对此菜单兜底。
