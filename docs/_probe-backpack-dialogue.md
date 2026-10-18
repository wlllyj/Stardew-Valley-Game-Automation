# task-32 只读探针：SeedShop 背包升级（Pierre 对话）入口 —— 0.7.45 真机

> 纪律：只读。不买、不升级、不改世界、不 restore A9。对话一律"不选 Yes"（`dismiss_modal` 无参数 ⇒ 自动挑否）。
> 游戏：已装冻结 0.7.45（dll `806C1069…B17F` / manifest `DECBA677…6A2E5C`，装机目录 18:54:09 / 18:53:51），本探针**跳过 deploy**（`bin\Release` 被 0.7.46 WIP 污染：291840B / `F05289C9…5B9` / 19:23:25），直接 `Start-Process StardewModdingAPI.exe` 起装好的冻结版。
> 存档：`Wahaha_450799035`（冬 28 06:00）。探针前后存档四件逐字节一致（§7）。A9-start（`5479354B…988A3D`）未动。

## 0. 结论先行（回答卡面 6 问）

1. **进店是否自动出现背包升级对话：否。** 首次进 SeedShop 触发的是世界事件 `3102768`（店内过场，推进 5 批 = 1+6+1+2+2 次点击后结束），全程无背包/购买类对话；`ui.dialogueResponses` 始终为空。
2. **interact Pierre 后是否出现：未取得（未到达触发点）。** 三类阻断：
   - `observe` 只暴露 `characters` **数量**（`Contracts.cs:372` `int Characters`、`WorldSnapshot.cs:684` `loc.characters?.Count`）⇒ 桥上看不到 NPC 格坐标；
   - 现有技能表**没有 `talk`**（`SkillCatalog.cs:32-35` Executable 无、`:42-45` Planned 里 `"talk"` 未实现）；`interact` 只调 `GameLocation.checkAction`（`Skills.cs:271-370`），对柜台 10 格实测全部 `no_action`；
   - 进店路径被 Town 事件 `15389722`（特殊订单板过场）**非确定卡死**阻断（5 次进 Town：1 次走完、4 次卡死；逐个时刻见 §3.1）。
3. **响应文本原文：** 只在 Town 事件提问里取到（非背包，§3.3）：`["I look forward to helping!", "Heh... I dunno... we'll see..."]`；背包相关响应 ⇒【无法判定·未取得】。
4. **bridge 能否读到响应选项：能。** `ui.dialogueIsQuestion=true` + `ui.dialogueResponses` 原文数组（`Contracts.cs:1042`；实拍见 §3.3）；无对话框时为空数组。
5. **入口结论：未找到可自动化入口（已试 X/Y/Z）。** 已试：①`buy` 结构化货架（20 条全表无背包，commit `27458df`）②进店事件推进（`advance_dialogue` 4 批，事件结束后无对话）③柜台 10 格 `interact`（全 `no_action`）④店内 `move_to` 寻路（[16,14]/[9,16] unreachable，[8,24]/[14,20] 可走）⑤Town 店门 4 格 `interact`（全 `no_action`）⑥像素截图核对（§4.2）。
   ⇒ 卡 A 若要做，**必须新增 mod 原语**（`talk` 或等效"打开 Pierre 对话"的入口）；已有 `dismiss_modal` 显式应答（`AnswerRules.Pick` / `ModalDismiss.DismissDialogueExplicit`）只解决"答问"，不解决"开对话"。
6. **Lead 补项：`ui.dialogueResponses` 里 Purchase 类选项的原文与下标 ⇒【无法判定·未取得】**（两处已见提问均非 Purchase；未到达 Pierre 对话；且冻结 0.7.45 无 `talk` 技能）。因此卡 A 用 `answerText` 还是 `answerIndex` **暂无真机依据**。

## 1. 环境与起跑（两次会话）

| 项 | 会话 A（19:30:47 起） | 会话 B（19:50:15 起） |
|---|---|---|
| 起法 | `Start-Process StardewModdingAPI.exe`（装好的 0.7.45；跳过 deploy） | 同左 |
| bridge.json | pid 10856 / token `2bf18e4a…9328` / startedAt 12:30:53Z / modVersion 0.7.45 | pid 15388 / token `4bf6db3e…e913` / startedAt 12:50:15Z / 0.7.45 |
| load | `python -m agentfarm load` → `Wahaha_450799035` FarmHouse [9,9] 4176ms；冬 28 06:00 sunny，体力 270，钱 3288g | `BridgeClient.load_save(force=True)` → FarmHouse，`eventUp=false`、clock 600（确认 load 是卡死事件的唯一恢复手段） |

时间窗：Pierre 店 9:00–17:00（店门锁时提示原文 `It's locked... (Open 9:00am - 9:00pm)`，实测 clock 750 时触发）。

## 2. 进店路径实测（FarmHouse → SeedShop）

`move_to_location("SeedShop")` 路径：FarmHouse → Farm（hop1 7617ms，落 [64,15]）→ BusStop（hop2 9847ms，落 [11,23]）→ Town（hop3 被 `ui_modal` 打断）。逐跳读数：
- BusStop 进镇时事件 `520702`（巴士过场）：**无需点击**，等 ~10s 自己结束（`eventUp:true→false`，3–5 轮）。
- Town 落地即触发事件 `15389722`（特殊订单板安装过场），`worldAdvancing` 先 true 后 false。

## 3. Town 事件 `15389722`：非确定卡死（本探针最大阻断）

### 3.1 五次进 Town（事件 `15389722`）的先后时刻与结果

> 更正：先前口头报告写「3 次进 Town、1 成功 / 2 卡死」是按 goto 尝试次数估的；按两份 SMAPI 窗口的 `Warping to Town` 原文（`logs/probe-backpack-smapi.txt` / `logs/probe-backpack-smapi-2.txt`）逐段数，实际是 **5 次进 Town：1 次走完、4 次卡死**。这是本探针最重要的一手数据。

| # | 进 Town（`Warping to Town` 首行） | 推进过程 | 结果 |
|---|---|---|---|
| A#1 | 19:32:24（会话 A 第 1 次） | 19:34:45–19:35:29 批量 `1,3,2,(0),(0),1,(0),2,3,(0),2`（SMAPI A:1063–1146）；19:35:29 后连续 10 次 `no_dialogue`（19:36:00–19:36:55，每 ~6s 一次，SMAPI A:1149–1186） | **卡死**：`eventUp=true/eventId=15389722/activeMenu=null/isModal=true/canMove=false`、clock 710 冻结、`liveness.worldAdvancing=false`（`secondsSinceClockMoved` 335.8→421.s）、`worldSeq=75` 自 19:32:29 起冻结 **484s**；19:40:34 `load_save` 恢复（SMAPI A:1192） |
| A#2 | 19:42:02（会话 A 重载后） | BusStop 事件 520702 先于 19:41:37–41:42 自行结束；19:42:10–19:42:55 批量 `0,0,1,0,3,1,0,1,1,4,2,6`（SMAPI A:2163–2208）；**19:42:58 起进入提问态**，连续 8 轮 `is_question`（19:42:58–19:43:19，SMAPI A:2211–2240） | **走完**：`dialogueIsQuestion=true`、`dialogueResponses` 2 项；~19:43:2x `dismiss_modal()` 无参选否 → 1.5s 后 `eventUp=false/canMove=true/clock 730` 恢复；19:44:23 已无事件（SMAPI A:2245） |
| B#1 | 19:51:02（会话 B 第 1 次） | 19:51:14–19:51:42 批量 `2,4,2,1,1,4,2`（SMAPI B:1055–1085） | **卡死**：之后无任何 ok；`worldSeq=69` 冻结 **262s**（19:51–19:55）；19:55:43 下一次 BusStop 重试 |
| B#2 | 19:56:08（会话 B 第 2 次） | 19:56:20–19:56:50 批量 `2,3,2,1,1,4,2`（SMAPI B:2169–2196） | **卡死**：`worldSeq=138` 冻结 **360s**（19:56–20:02）；20:02:27 重试 |
| B#3 | 20:02:52（会话 B 重载后第 3 次） | 20:03:06–20:03:32 批量 `1,3,2,1,2,4,2`（SMAPI B:3281–3308） | **卡死**：`worldSeq=207` 冻结 **131s**（20:02:58–20:05:09）；脚本放弃 → 20:05:09 优雅退 |

4 次卡死态的共同读数（原文）：`eventUp=true`、`eventId="15389722"`、`activeMenu=null`（没有可推进的 DialogueBox）、`isModal=true`、`canMove=false`、clock 冻住、`liveness.worldAdvancing=false`。

### 3.2 卡死态下桥侧原语全部无效（证据）
- `advance_dialogue`：`BridgeError [no_dialogue] (HTTP 200) 当前没有 DialogueBox ⇒ 无可推进（eventUp=True）`；
- `dismiss_modal`：无活动模态 ⇒ ok/no-op，事件不动；
- `move_to_location` / `move_to`：`[ui_modal]` 拒绝；
- `interact` 店门 4 格（[43,57][43,58][44,57][44,58]）：全部 `[no_action] checkAction 返回 False`；
- 唯一恢复：`load_save(force=True)`（A#1 19:40:34 实测有效；重读档后事件会在下次进 Town 时重新触发，见 §3.1 B#1/B#2 的重试）。⇒ **A9/长跑若需要进 Town，必须先修这条**（脑侧按 task-41 只能诚实停；不能自愈）。

### 3.3 成功样本的提问态读数（原文）
```
ui = {activeMenu:"DialogueBox", isModal:true, eventUp:true, eventId:"15389722",
      onScreenMenus:5, activeMenuText:"", dialogueIsQuestion:true,
      dialogueResponses:["I look forward to helping!", "Heh... I dunno... we'll see..."]}
player = {tile:[61,94], canMove:false, facing:1}  clock = winter 28 720
```
`dismiss_modal()`（无参数）回执原文节选：`已关闭对话框（选"Heh... I dunno... we'll see...”：answerDialogue("1")closeDialogue() 关闭…）` + 警告 `游戏仍处于不可控状态（canMove=False…）需要外部恢复`；1.5s 后 `eventUp=false, menu=null, canMove=true, clock 开始走`（7:50→9:00 内推进正常）。**全程未选 Purchase、未指定 answerIndex/answerText。**

### 3.4 怎么判定"卡死"：门限建议（给 watchdog / 事件态自愈用）

**推荐判据（三条件同时成立才判卡死）**：
1. `eventUp == true` 且 `activeMenu == null`（事件在跑但已没有可推进的 DialogueBox）；
2. `advance_dialogue` **连续 10 次**返回 `no_dialogue`（默认每次间隔 3–6s ⇒ 合计 ≥30–60s），且期间没有任何 `ok / stepped>0`；
3. 期间 `liveness.worldAdvancing == false` **且** `worldSeq` 无变化（辅助条件；见下方"不能单用"）。

**不能单用 clock / worldSeq / worldAdvancing 的理由（一手反例）**：
- 成功样本 A#2 的 `worldSeq=158` 也**冻结了 124s**（19:42–19:44）却走完并进入提问态 ⇒ worldSeq 冻结本身不是卡死；
- 事件态下 clock 本来就不走（`secondsSinceClockMoved` 会一路涨，成功事件期间也一样）⇒ clock 不是判据；
- `liveness.worldAdvancing` 在成功事件期间同样是 false ⇒ 不是充分判据；
- 成功样本里两次点击之间的最长静默约 4–8s（SMAPI A:2163–2212 段）⇒ 门限必须显著大于它，**不要低于 30s**。

**观测到的卡死持续时长**（`worldSeq` 冻结段）：A#1 **484s**、B#1 **262s**、B#2 **360s**、B#3 **131s** ⇒ 2–8 分钟内**没有任何**自愈迹象，全部只能靠 `load_save(force=True)`。
**自愈动作建议**：判卡死后 ①记 `eventId/clock/worldSeq/连续 no_dialogue 次数`；②`load_save(force=True)` 重读档（唯一实测有效手段）；③同一小时连续 2 次自愈后仍复发 ⇒ 按 task-41 的 `event_blocked` 诚实收尾，不再盲重试。建议门限做成可配置：默认 60s / 10 次 no_dialogue，下限 30s。
**更强的做法（mod 侧）**：让 `advance_dialogue` 在"事件仍在 + 连续 no_dialogue"时直接回一个 `stalled=true` 字段，脑侧就不用自己数次数/卡时间。



### 4.1 位置/世界读数
- `location.name="SeedShop"`，player 进店落 [6,29]；随后 `move_to [8,24]` ok、`[14,20]` ok；`[16,14]`/`[9,16]` ⇒ `[unreachable] 寻路无法到达（A* 未算出路径）`。
- `characters=3`（**只有数量**）；`doors=[{tile:[32,3],type:"Sunroom"}]`；`objectList=[]`；`tiles=[]`（室内不暴露 tile 列表）；`tilesTruncated=null`。
- 入店内事件 `3102768` 推进：`advance_dialogue` 批量 1+6+1+2+2 次点击，约 40s 后 `eventUp:true→false`，canMove=true。

### 4.2 像素截图（只读，PrintWindow/PW_RENDERFULLCONTENT；窗口不在前台会全黑）
- `scratch/_t18_shop_ui.png`（51587B）店内视图：左墙货架/种子架、柜台区"FOR SALE"装饰牌；
- `scratch/_t18_shop_pos2.png`（56753B）/`_t18_shop_pos3.png`（60395B）：货架、种子陈列、"FOR SALE" 收银台；
- `scratch/_t18_shop_counter.png`（61889B）、`scratch/_t18_shop_pos.png`（46849B）：柜台近景；
- `scratch/_t18_shop_in.png`（8990B）为**黑帧**（PrintWindow 失败样本，如实保留）；`scratch/_t18_town_hung.png`（17692B）为卡死态 Town。
- 仓库外参考：`scratch/_t18_screen.png`/`_t18_screen2.png`（19:34/19:35，Town 过场首句 `Ah, hello there, Jay. You…`）。

## 5. Pierre 定位与对话尝试

- 存档 XML 解析（只读）：`SeedShop.characters = [Pierre, Abigail, Caroline]`；Pierre `<Position><X>256</X><Y>1088</Y>` ⇒ **tile [4,17]**（/64）。该坐标来自 19:15:01 的存档（冬 28 睡前），不是实时观测。
- **无 `talk` 原语**：`interact` 调 `checkAction`（`Skills.cs:322`），柜台区 10 格（[6,14]…[8,16]）逐格实测全部 `[no_action]`；"FOR SALE" 收银台不是 `checkAction` 入口。
- `observe` 的 `characters` 是数量（`Contracts.cs:372`），无法按名查位 ⇒ 桥侧无法"走到 Pierre 旁边再 interact"。
- 会话 A/B 均**未出现** Pierre 主动对话（进店事件结束后 `ui` 为空壳）。

### 5.1 存档 XML 原文（Pierre 坐标的唯一旁证，只读提取）

来源：`C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035`（2948770B / 19:15:01 / `6DE8419B…B594`）。抽取命令：按 `<GameLocation xsi:type="...SeedShop">` 后的 `<characters>` 段截取。原文节选（单行 XML，为阅读折行）：

```xml
<characters><NPC><name>Pierre</name>…<Position><X>256</X><Y>1088</Y></Position>
<Speed>2</Speed><FacingDirection>2</FacingDirection>…</NPC>
<NPC><name>Abigail</name>…</NPC><NPC><name>Caroline</name>…</NPC></characters>
```

⇒ Pierre 在 SeedShop 内 tile **[4,17]**（256/64, 1088/64）。注意这是**离线旁证**（19:15:01 睡前存档），不是实时观测，也未驱动任何寻路/交互。

### 5.2 已试通道清单（6 条，避免后人重复试）

| # | 通道 | 做法 | 结果 | 证据（文件/行号） |
|---|---|---|---|---|
| 1 | **货架 buy 结构化清单** | `buy {"shop":"SeedShop","item":"__probe_none__"}`（不真买；回执带 `availableItems` 全表） | `item_not_sold`；20 条货架无任何背包条目（`backpack_hits=[]`，价格 100g–30,000g，20<30 未被截断）⇒ 背包升级**不在店里直接买** | `scratch/_t18_shop_shelf.json`（26619B / 19:22:09）；脚本 `scratch/_t18_shop_shelf.py`；commit `27458df`；`docs/_smoke-0745-shop-probe.md` |
| 2 | **进店事件自动对话** | 进 SeedShop 后 `advance_dialogue` 批量推进 | 只触发世界事件 `3102768`（1+6+1+2+2 次点击后结束），`dialogueResponses` 始终为空 ⇒ 不会自动弹背包升级对话 | `logs/probe-backpack-smapi.txt:2271-2336`（19:46:04–19:47:19）；§4.1 |
| 3 | **柜台区 interact ×10** | `interact` 逐格打 [6,14]…[8,16]（"FOR SALE" 收银台周边） | 全部 `[no_action]`（`checkAction` 返回 False）⇒ 柜台不是交互入口 | 会话 A 终端 exec 回执（**未独立落盘**，SMAPI A 窗口同段 exec 记录可对时）；`Skills.cs:271-370` |
| 4 | **店内 move_to 寻路** | `move_to` 试 [16,14]/[9,16]/[8,24]/[14,20] | [16,14]/[9,16] `[unreachable]`；[8,24]、[14,20] ok（室内可走但走不到收银台后区） | SMAPI A 窗口 exec 段（19:48:2x–19:48:5x）；§4.1 |
| 5 | **Town 店门 interact ×4** | 卡死态下对店门 [43,57][43,58][44,57][44,58] 用 `interact` | 全部 `[no_action]` ⇒ 事件卡死时连门都进不去 | `scratch/_t18_pierre_probe.py`（门格常量）；SMAPI B 窗口 20:04:5x exec 段；§3.2 |
| 6 | **像素截图核对** | `PrintWindow`(PW_RENDERFULLCONTENT) 抓游戏窗口 | 拿到店内 5 张视图（货架/种子架/"FOR SALE" 收银台）+ Town 卡死态 1 张；另有 1 张黑帧失败样本 ⇒ UI 上**没有任何背包升级按钮/对话** | `scratch/_t18_shop_ui.png`(51587B)/`_pos.png`(46849B)/`_pos2.png`(56753B)/`_pos3.png`(60395B)/`_counter.png`(61889B)/`_town_hung.png`(17692B)；黑帧 `_t18_shop_in.png`(8990B)；§4.2 |

附带通道（离线，未起游戏）：存档 XML 按名定位 NPC（§5.1）——只能旁证坐标，不能当实时观测。



| 需要 | 现有能力 | 结论 |
|---|---|---|
| 找到 Pierre | `observe.characters`（数量） | 缺：NPC 坐标 |
| 打开 Pierre 对话 | 技能表无 `talk`（Planned 未实现） | 缺：入口原语 |
| 读选项文本/下标 | `ui.dialogueResponses` ✅ | 有 |
| 显式应答 | `dismiss_modal(answerIndex/answerText)` ✅（fail-closed） | 有（但只在对话已打开时可用） |
| 自动推进非提问对话 | `advance_dialogue` ✅ | 有 |

## 7. 收尾四项与证据

- 优雅退：`stop-game.py --wait 45` → 会话 A `pids=[10856]`、会话 B `pids=[15388]`；两次均 rc=0；退后 `进程数=0`、`bridge.json exists=False`、`17890 LISTENING=False`（仅 TIME_WAIT）。
- 存档四件（探针前后**逐字节一致**，未落盘任何世界变更）：
  - `Wahaha_450799035` 2948770B 19:15:01 `6DE8419B098EA16972C7DB761F4080127599523A2C1AD8EC5A6176F86861B594`
  - `SaveGameInfo` 32264B 19:15:01 `B5B51971BFF129EDE468D2671731A50B0D0A7964755AE7AB5643AEF07A7310A1`
  - `Wahaha_450799035_old` 3137234B 19:04:33 `1695C1ED3286601FD951837AD0D4363EA45542024E01CD0B4F45B26FD453509D`
  - `SaveGameInfo_old` 32259B 19:04:33 `BCC85C1B47EE63CE043EDE9668EA44E76D67867DD1C5E1CBCB4392D3AAE57DAA`
- SMAPI 窗口冻结（源=副本字节一致，`grep Backpack|Pierre` 0 命中）：
  - 会话 A `logs/probe-backpack-smapi.txt` 192381B / 2379 行 / mtime 19:49:18 / SHA256 `E94B835DDFD75762BCFDA02037976C3D8BEBF6E10A6E8F823AFBAD289D97E5E7`
  - 会话 B `logs/probe-backpack-smapi-2.txt` 229423B / 3347 行 / 20:05:09 / SHA256 `5F598EE696FE695418F5C475BBF2F2A079A5A08AAF93D95D0934A9283A0C0B7A`
- 装机目录再核（探针结束）：dll 286208B / `806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F` / 18:54:09；manifest 73663B / `DECBA6775569D7C42DF910E7E6A72BC2CF59B1E2729C29484E700F6E786A2E5C` / 0.7.45。`bin\Release` 仍为 WIP `F05289C9…5B9`（291840B，19:23:25）。
- HUD「Inventory Full」：本轮**未复现**（SMAPI 两份窗口 `HUD` 0 命中；`Inventory` 仅命中 Mod 发布说明）。

## 8. 已知限制

1. Town 事件 `15389722` 卡死是**非确定**的：按 SMAPI warp 原文 5 次进 Town 中 1 次走完、4 次卡死（A#1 19:32、B#1 19:51、B#2 19:56、B#3 20:02，见 §3.1），未取得触发条件 ⇒ 定因【无法判定】。
2. 未取得 Pierre 对话原文；`Purchase` 选项下标/文本、背包升级价格文本均【无法判定】。
3. `characters` 只有数量（`Contracts.cs:372`），NPC 坐标只能从**存档 XML**旁证（离线、滞后）。
4. 截图依赖窗口前台（PrintWindow 黑帧样本已保留）；`ui.activeMenu`/`activeMenuText` 仅在模态打开时出现（无模态时为 null）。
5. 会话 A 的 `world_stuck` 警告（dismiss 后 1.5s 内）是已知形态，事件仍能正常结束；但不能据此认为"卡死可自愈"（3.1 #2/#3 的反例）。
