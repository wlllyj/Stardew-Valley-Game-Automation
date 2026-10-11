# IL 定案：睡觉链为什么"调用返回了，却没跨日"

日期 2026-10-12 ｜ 作者 Lead ｜ 目的：给 task-8（修 sleep 跨日）一条**不再有候选分支**的机制结论。

证据文件（均为 `tools\il-probe` 产出；转储是 UTF-16LE，先用 `tools\_tmp_conv.py` 转 UTF-8 再看）：

| 文件 | 内容 |
| --- | --- |
| `scratch\il-sleep-answer-u8.txt` | `GameLocation.answerDialogueAction` / `Farm.answerDialogueAction` 反汇编（8326 行） |
| `scratch\il-sleep-body-u8.txt` | `GameLocation.startSleep()`（122 行） |
| `scratch\il-dosleep-u8.txt` | `GameLocation.doSleep()`（90 行） |

游戏目录 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`（1.6.15）。

## 1. 入口：`answerDialogueAction("<Q>_Yes", null)`

```
IL_0ABB: ldarg.1
IL_0ABC: ldstr          "Sleep_Yes"
IL_0AC1: call           Boolean op_Equality(System.String, System.String)
IL_0AC6: brtrue         -> IL_30D5
IL_0ACB: br             -> IL_393D          // 默认出口：正常返回、什么都不做
...
IL_30D5: ldarg.0
IL_30D6: call           Void startSleep()
IL_30DB: br             -> IL_3976
```

⇒ **只要传进来的字符串正好等于 `"Sleep_Yes"`，就一定执行 `startSleep()`**；这一层**没有** `isInBed` / `dialogueUp` / `lastQuestionKey` 任何前置判据。
⇒ 传别的字符串（例如 `lastQuestionKey` 前缀拼错）则一路落到 `IL_393D`：**静默 no-op，既不做事也不报错**。

`Farm.answerDialogueAction`（存在覆写）在这一点上与基类**逐字相同**：`IL_0ABC ldstr "Sleep_Yes"`、`IL_30D6 call startSleep()` ⇒ task-6 报告里的候选 **M3（Farm 覆写行为不同）不成立**。`FarmHouse` 不覆写该方法（探针输出"未找到"）。

## 2. `startSleep()`：唯一分支是 `Game1.IsMultiplayer`

```
IL_0000: call  Farmer get_player()
IL_0005: ldfld NetInt timeWentToBed
IL_000A: ldsfld Int32 timeOfDay
IL_000F: callvirt Void set_Value(Int32)      // player.timeWentToBed = Game1.timeOfDay
IL_0014: call  Boolean get_IsMultiplayer()
IL_0019: brfalse.s -> IL_006E
   // —— 多人分支：只装一个可取消的 ReadyCheckDialog，不睡觉 ——
IL_001B: ldsfld ReadySynchronizer netReady
IL_0020: ldstr  "sleep"
IL_0026: callvirt Void SetLocalReady(String, Boolean)
IL_002B: ldc.i4.0 / IL_002C: stsfld Boolean dialogueUp
IL_0031-0067: new ReadyCheckDialog("sleep", true /*isCancelable*/, <startSleep>b__437_0, <startSleep>b__437_1)
              -> Game1.activeClickableMenu
IL_006C: br.s -> IL_0074
IL_006E: ldarg.0
IL_006F: call  Void doSleep()                // —— 单人分支：直接睡 ——
```

⇒ `IsMultiplayer == true` 时 `startSleep()` **根本不调 `doSleep()`**，只是把 `activeClickableMenu` 换成 `ReadyCheckDialog("sleep", isCancelable: true, …)`，然后返回。**没有** `isInBed` 判据。

## 3. `doSleep()`：没有任何前置判据，每个分支都 `NewDay`

```
IL_0000-001C: 若 (lightLevel == 1 && Game1.timeOfDay < 2000)：
IL_0029: 若 !isOutdoors -> lightLevel = 1、localSound("openBox")
IL_0059: call get_IsMasterGame()
IL_005E: brfalse -> IL_00EC
IL_0063: ldc.r4 0; IL_0068: call NewDay(Single)      // Game1.NewDay(0f)
IL_006D: br.s -> IL_00EC

IL_006F-008B: 否则若 (lightLevel > 1 && timeOfDay >= 2000)：
IL_00C8: if (IsMasterGame) NewDay(0f)

IL_00DB: 其余情况：
IL_00E2: if (IsMasterGame) NewDay(0f)

IL_00EC 起：player.lastSleepLocation = currentLocation.NameOrUniqueName；
            player.lastSleepPoint = player.TilePoint；
            mostRecentBed = player.Position；player.doEmote(24)；player.freezePause = 2000；ret
```

⇒ `doSleep` 里**没有** `isInBed` / 时间段 / "提问是否开着"的前置 `return`；三条分支最终都做同一件事：**若 `Game1.IsMasterGame` 则为真 → `Game1.NewDay(0f)`**。
⇒ 而 `Game1.NewDay` 会**无条件** `newDay = true` + `newDaySync.create()`（task-6 §3 已证）⇒ 只要 `doSleep` 被走到，SMAPI 里必然出现 NewDay/存档流程。

## 4. 结论：三个候选收成一个

1. 22:07:55 的 PASS 探针（人已在床上）在**同一进程、同一存档**里 **1.8s** 完成跨日 ⇒ 那一刻 `IsMultiplayer == false` 且 `IsMasterGame == true`。
2. 因此 run2 两次失败**不可能**是"`startSleep`/`doSleep` 的前置判据挡住了"（第 2、3 条已证这两处没有这种判据；且若 `IsMultiplayer` 为真，PASS 那次也睡不成）。
3. 唯一自洽的解释：**Mod 发出去的应答字符串不等于 `"Sleep_Yes"`** ⇒ `answerDialogueAction` 走 `IL_393D` 默认出口，静默返回；Mod 于是等满 180s，期间世界当然毫无变化（SMAPI 零 `NewDay`、零 `SaveGame.Save()`、日期不变、`timeOfDay` 0 分钟不动 —— 与观察到的指纹逐条对上）。
4. 字符串不等的原因就是 `BuildSleepAnswerKey()` 拿到了错的 `lastQuestionKey` 前缀（提问根本没开 ⇒ 前缀不是 `Sleep`），而 `interact(bed)` 这条脑侧路径没能让游戏自己弹出睡觉提问（task-6 已证：全 SMAPI 日志 `answerDialogue(` 出现 0 次）。
5. **待真机确认的一条读数**（task-8 的 D 项会让它进 journal，一行即可定案）：Mod 回执里的 `lastQuestionKey` / `activeClickableMenu` / `dialogueUp` / `gameMode`。若 `lastQuestionKey` 不是 `Sleep …`，本节结论即为定案；若是 `Sleep …` 却仍未跨日，则反过来坐实"多人分支"（`IsMultiplayer == true`），届时再查多人准备状态。

## 5. 对 task-8 的直接影响

- **判据不是 `isInBed`，而是"游戏自己弹出了睡觉提问"**（`lastQuestionKey` 前缀 = `Sleep`，或观测里 `ui.dialogueIsQuestion`）。踩床（`move_to(bed_tile, allow_bed=True)`）之所以是对的方向，是因为它触发的正是游戏自己的 `checkAction(bed)` → 弹提问；`interact(bed)` 在我们手上从未触发它。
- **Mod 侧先判 `lastQuestionKey` 再决定发什么**：拼不出 `Sleep` 前缀就立刻 `sleep_no_question` 失败（附 `isInBed` / `lastQuestionKey` / `activeClickableMenu` / `gameMode`），**绝不等 180s**。这与 task-8 A②/① 完全一致，只是把"立刻失败"的判据从 `isInBed` 换成 `lastQuestionKey`。
- **不要反射调 `startSleep()` / `doSleep()`**：绕不过"提问是否合法 / 多人分支"这两道门，只会把同一件事做得更隐蔽（task-6 R6 同结论）。
- 只有当真机确认 `IsMultiplayer == true` 时才需要处理多人分支（让 `ReadyCheckDialog` 完成），目前**无证据**支持这条路。

## 6. 可复用教训

1. `answerDialogueAction` 一族是**字面量分派**：字符串对不上就是静默 no-op —— **回执 `ok` 完全不代表游戏做了事**（与 v0.7.17"种了种子不扣"同源的教训：只认观测差分）。
2. 判断"这行代码有没有前置判据"不要靠推理，**dump 一遍 IL**：本次三个方法合计 300 行 IL，把 3 个候选假设砍到 1 个。
3. 探针输出的两种坑：`il-probe` 重定向到文件是 UTF-16LE（首字节 `FF FE`），`read`/`grep` 会当二进制 —— 一律先 `tools\_tmp_conv.py`；dump 里 **call 指令不打印声明类型**，判断"这是不是基类/覆写"要靠偏移与序列逐字比对（本次 `GameLocation` vs `Farm` 就是这么比的）。
