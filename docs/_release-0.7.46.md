# 0.7.46 发布计划（A9 门禁：smoke-0746）

> 目的：修 0.7.45 真机冒烟（smoke-0745）暴露的四个新形态，过 smoke-0746 门禁后，才允许起 A9/B9。
> 判据纪律：缺失≠通过；独立观测差分；不许为凑 VERIFIED 放宽任何判据；不许改 `unreachable_within_bound` 公式。

## 0. 背景：smoke-0745 门禁 FAIL（0/2 天 verified）

账本 `logs/longrun-smoke-0745.jsonl`（650 行 / 2 天 / 0 坏行），mod 0.7.45，游戏 pid 1500，guardian 19:15:18 自动优雅退（进程 0 / bridge.json 删 / 17890 空闲）。

| 日 | ended_by | ok_steps | unreachable | checks 红 | pending（账本/守卫/停滞/可执行/判死/看不见/残缺） | free_slots 开/终/低 | loot_lost_steps |
|---|---|---|---|---|---|---|---|
| 冬 26（L231） | inventory_blocked | 33 | 32 | unreachable_within_bound、day_justified | 3/3/0/0/0/3/0 | 0/1/0 | 21 |
| 冬 27（L647） | sleep | 210 | 16 | day_justified | 230/7/0/**7**/223/0/0 | 0/0/0 | 205 |

- 冬26 ended_reason 原文：`inventory_blocked:背包满（空格 1）且今天已经腾不出格子：不是没活、也不是 stuck —— 是背包堵住（先去出货/卖材料腾格，明天再收）`
- 冬27 ended_reason 原文：`resume_exhausted:回片区 220 格都回去看过、换片 4 次，当前观测里没有可执行目标（守卫仍说：今天早些时候还有 7 格没做完（跨片地，最近的是 [31, 42]））`
- finish（L650）：`code=1, verified_streak=0, actions=420, minutes=14.57, no_unmet_stages=true, unmet_days=[], stuck_flushes=0`。
- 关键新事实：
  1. **12 格背包结构性死锁**：`inventoryCount=12`（未买背包升级），12 格全占（5 工具 + Acorn/Maple Seed/Copper Ore/Stone/Hay/Coal/Wheat Seeds），按纪律无可腾格项 ⇒ 清障掉落永久丢（冬27 205/210 步）。钱 3264 已够 2000g 背包升级。
  2. **售材违反纪律**：slot_relief 真卖了 (O)388 Wood×5 笔、(O)330 Clay×3、(O)92 Sap、(O)262 Wheat×5、(O)535 Geode×3（全走 shipping bin）——AGENTS.md §5 明禁「建材永不卖」。
  3. **批量把 32 个「四邻都站不过去」格记成 unreachable**（冬26 32>bound 15 ⇒ 判据红）。**归属实测更正（task-27 取证，2026-10-18）**：32 格 = till 12（field_nw、t=88.71 同秒）+ clear 20（field_ne 9 / field_sw 7 / field_se 4，t=98.97–212.17）；初版卡面「32 格全在 t=88.71 同一 till 事件」是错的，以 task-27 实测为准。clear 有 encircled 归类，till 没有；且 clear 的 encircled 只在「四邻全观测且都站不了」时才命中，四邻无观测时也落到 unreachable。
  4. **day 级 7 格可执行与守卫口径未闭合**（冬27 守卫仍说剩 7 格、resume 拿不到；`pending_blocked 223 − pending_stalled 218 = 5 格`来源未单列）。

## 1. 卡片（dev-coder 串行 A→B→C→D）

| 卡 | 任务 | 优先级 | 提交 | 读数 |
|---|---|---|---|---|
| A-前置 | task-33 Mod 新增 `talk` 原语：按 NPC 名找 `characters` → 相邻校验（否则回 `not_adjacent`+`npcTile`）→ 调游戏 `NPC.checkAction(Farmer,GameLocation)`；禁合成键鼠/禁改 Money/Items/MaxItems | P0 | 待填 | 待填（真机探针 task-34 验收：talk 能否开 Pierre 背包对话） |
| A | task-25 背包升级经济动作（12→24，Pierre 2000g）。**Plan A（按货架买）已否证**；真机探针又证**无 talk 原语** ⇒ 分两步：task-33 加 `talk` + 本卡脑侧 `talk Pierre` → observe `ui.dialogueResponses` → `dismiss_modal{answerText:"Purchase"}` → 差分判据：钱−2000 且 inventoryCount 12→24；含 Town 事件卡死自愈（≤90s + load_save(force) 兜底） | P0 | 待填 | 待填（task-34 探针通过后实现） |
| B | task-26 冬27 形态：`resume_walks` 先加后走（失败步行烧成功预算）+ `_resume_exhausted` 无条件宣称无目标 ⇒ 改为 attempts/walks 拆分 + `claim_exhausted=(exec==0 and malformed==0)`，假则写 `resume_budget_exhausted:`；未放宽 `is_justified_end` | P0 | `002afdb`（3 files +476/−28） | 定向 `TestTask26ResumeBudget` Ran 6 OK；全量 Ran 1354 OK；变异 3/3 被杀；Lead 亲跑 6/6 OK |
| C | task-27 挡死格证据口径收口：目标池前置过滤（`_known_enclosed`/`_prefilter_known_enclosed`）+ 执行层 `_observed_foothold` 判"本该可达"、无落脚点证据归 encircled；判死格仍进 assigned/assigned_undone（不洗成没活）；bound 公式与 20% 未动；附带 `pending_executable_tiles[:8]`/`pending_stalled_tiles[:8]` | P1 | `acf2f6c`（5 files +628/−24）+ `1800ef1`（3 files +70/−1） | 定向 `TestTask27EnclosedBatch` Ran 9 OK（总 195 OK）；全量 Ran 1363 OK；变异 8/8 被杀（worktree+冻结 HEAD 双跑）；Lead 核公式与 `:9811` 未动、测试 195 OK |
| D | task-28 售材白名单收紧（建材/锭类全部移出）+ inventory_blocked 证据门槛 + 满包清障有界（loot_lost_steps ≤ 常量，留痕） | P1 | 待填 | 待填 |

## 2. 冻结九步（沿用 0.7.44/0.7.45 口径）

1. 写 `tools/_note-0746.txt`（本批四卡一句话 + 冻结前置）。
2. `python tools\_bump-mod-version.py 0.7.46 --note-file tools\_note-0746.txt`（manifest Version + Description 头）。
3. 改 `brain/agentfarm/bridge.py` `MOD_VERSION_EXPECTED = "0.7.46"` + 新注释块（旧块移 `# --- 历史 ---`）。
4. `dotnet build -c Release --no-incremental`（0 警 0 错）+ C# 自检（`dotnet run -c Release`，OK 91 断言）+ `python -W error::SyntaxWarning -m py_compile brain\agentfarm\bridge.py`。
5. 按路径 `git add`/`git commit`（禁 amend / 禁 add -A；bridge.py、manifest.json、_note-0746.txt）。
6. `python tools\check-release.py --expect 0.7.46`（六项全绿：版本一致 / dll 不比源码旧 / py_compile / 全量单测 / 工作树干净）。
7. 部署前核对（无 Stardew 进程、仓库根与 %APPDATA% 无 bridge.json、17890 无 LISTENING；**`bin\Release\AgentFarm.Bridge.dll` 哈希必须 == 冻结产物**，否则先 `dotnet build -c Release --no-incremental` 重建再核——见 §7.2 事故）→ `python tools\deploy-mod.py --no-quit`（ALSOFT_DRIVERS=null）。
8. `PYTHONPATH=<repo>\brain python -m agentfarm goto Farm`（落 Farm）。
9. `python tools\preflight.py --expect 0.7.46 --save-baseline logs\runA9-baseline.json` → `python tools\stop-game.py --wait 45` 优雅退 → 复核进程 0 / bridge.json 删 / 17890 空闲。

## 3. smoke-0746 门禁（machine-runner，tag `smoke-0746`）

- 跑法：`scratch\smoke-0742.py` 四阶段（pre → guardian 先起 → launch → wait → post），launch 参数 `--days 1 --size 5 --max-minutes 60 --max-days 2 --capture-observe --observe-every 120 --no-crops --expect-version 0.7.46`，guardian tag `longrun-smoke-0746`；窗口 `logs\smoke-0746-smapi-window.txt`。
- **放行条件（全满足）**：
  1. `finish.code == 0` 且 `verified_streak >= target_days`（即 ≥1 天 verified=true）；
  2. 0.7.44/0.7.45 的 FAIL 形态转 PASS：冬26 形态 `inventory_blocked` 带证据门槛且 day_justified=true（或当天空格>0 根本不触发）；冬27 形态 `pending_executable==0` 且 day_justified=true（不再是假红）；
  3. 全程 0 条 `stuck:` 掩盖（允许有界诚实停，必须是 resume_exhausted/inventory_blocked/stamina 等命名前缀）；
  4. 售材纪律：`sell` 事件中 0 笔建材/锭类（388/390/330/771/382/378/380/384/386/909）；
  5. 背包证据在场：`free_slots_*`/`loot_lost_steps` 字段非空；若 free_slots==0 且 relief 用尽 ⇒ loot_lost_steps 有界；
  6. 落盘六串配对 2/2（退前退后逐字节）；guardian 优雅退干净。
- 失败处置：写 docs/_smoke-0746.md 如实读数 → Lead 判 → 继续开卡，**不许为过门禁放宽判据**。

## 4. A9/B9 协议（smoke-0746 通过 + Lead 放行后才起）

- 起点：`logs\ab-backup\A9-start\`（winter 26 存档，四件 SHA256 已记）；start 前 `scratch\arm-start-helper.py restore --arm A9` → `verify --arm A9` 4/4 OK。
- 起跑：`tools\start-detached-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs\longrun-runA9-0746.jsonl --expect-version 0.7.46` + `tools\run-guardian.py --tag longrun-runA9-0746 --detach`（guardian 先起）。
- 判据：`verify-run3 --days 5 --smapi` + `analyze-longrun --window 5` + `compare-runs` L0–L5 + 三检查器；**A9/B9 一律 already/attempted_ok 与 ok 双列读**；A8 与 A9 起点不同，不可跨对比较。
- B9：restore A9 起点 + `<journal>-lessons.json` 字节拷贝 → 同 argv（零 LLM 边界对照）。

## 5. 已知限制 / 风险

1. 背包升级**不在 SeedShop 货架**（真机只读探针实测 20 条全表无 Backpack/Deluxe Backpack，见 §7.1）；机制是 Pierre 对话式购买已由探针定位（§7.3：DB 级证据 `NPC.checkAction` + DLL 对话键 `SeedShop_BuyBackpack_*`/`Purchase`），但**现有技能无 talk 原语**（task-32 六问已试 6 条通道全败）⇒ 卡 A 拆成 task-33（Mod talk）+ task-25（脑侧购买）。若 task-34 探针证 talk 也打不开对话 ⇒ 卡 A 停、Plan B（木箱存储/接受 12 格 + 证据门槛）由 Lead 另裁。
2. 建材/锭类移出白名单后可腾格项变少 ⇒ 满包时更容易诚实收工；结构性解法是背包升级（卡 A），不是放宽白名单。
3. 冬26 40 格（263−223）账本无坐标 ⇒【无法判定】，不参与任何 PASS 结论。
4. 0.7.45 的 `stage_midway_leftover` 遮蔽形态仍有（8 条/1 天），只 info。
5. 春季农务腿（crops/watering/harvest）仍未真机验证；smoke 用 `--no-crops`。
6. **Town 事件 `15389722` 非确定卡死（真机 5 次进 Town = 1 成功 / 4 卡死，task-32 探针）**：`eventUp=true / activeMenu=null / isModal=true / canMove=false / worldAdvancing=false / clock 冻结`；`advance_dialogue`→`[no_dialogue]`、`dismiss_modal` no-op、`move_to*`→`[ui_modal]`、店门 interact 全 `no_action`；唯一恢复 = `load_save(force=True)`。农务长跑不进 Town 时无影响；任何进城动作（卡 A）必须带事件自愈超时兜底（判据见 §7.4）。

## 6. 冻结记录（待填）

- 冻结提交：待填
- 版本一致性 / dll 指纹 / manifest 指纹 / build 读数 / C# 自检 / check-release / 装机 / goto Farm / preflight baseline / 优雅退：待填

## 7. 勘察记录（2026-10-18 晚，Lead）

### 7.1 背包升级机制：Plan A 否证 → 对话式购买

- 真机只读货架探针（machine-runner commit `27458df`、`docs/_smoke-0745-shop-probe.md`）：SeedShop `availableItems` **20 条全表无 `Backpack`/`Deluxe Backpack`**（`backpack_hits=[]`）；20<30 说明不是 `Shelf()` 截断（`BuySkill.cs:456-469` 的 12 条只是**文字 Listing** 显示截断）。⇒ 现有 `buy` 技能按 `itemPriceAndStock` 找条目，**结构上买不到背包升级**。
- 离线侦察（Lead，未动游戏）：
  - `Stardew Valley.dll`（1.6.15.24356）二进制串：`increaseBackpackSize`/`clearBackpack`/`backpack`/`MaxItems` 存在；**无** `TryBuyBackpack`/`BuyBackpack`/`SeedShop_BuyBackpack`/`backpackCost`。
  - net6 反射元数据探针（`logs/_probe_sdvmeta/`）：`ShopMenu` 无任何名字含 backpack 的成员；`Farmer.increaseBackpackSize(Int32)`；`SpecialItem` 静态常量 `backpack`（Int32）+ `actionWhenReceived(Farmer)`；全库含 backpack 成员仅 `Farmer.increaseBackpackSize` / `Farmer.clearBackpack` / `SpecialItem::backpack`(static) / `DebugCommands.Backpack` / `FillBackpack`。
  - 维基：[Backpack](https://stardewvalleywiki.com/Backpack)（Large Pack 2000g / Deluxe 10000g）；[1.6.16 迁移页](https://wiki.stardewvalley.net/mediawiki/index.php?title=Modding:Migrate_to_Stardew_Valley_1.6.16) 把 `Strings/Locations: SeedShop_BuyBackpack_Response2000/Response10000/ResponseNo` 改名 `GenericPurchase_*`；[1.6 迁移页](https://wiki.stardewvalley.net/mediawiki/index.php?title=Modding:Migrate_to_Stardew_Valley_1.6) `Utility.TryOpenShopMenu`/`GetShopStock`。
  - `Content/Data/Shops.xnb` 离线解压失败（非标准 LZ4/raw-deflate）⇒ 走真机取证，不再手写解压器。
- 结论：背包升级是**对话式购买**，不是货架条目 ⇒ 卡 A 改「`interact` Pierre → 按响应文本 `answerDialogue(Response)` → 观测差分（钱 −2000 且 `inventoryCount` 12→24）」，先等 task-32 只读对话探针确认入口与响应文本。

### 7.3 task-32 结论 + DB 级证据 → 卡 A 拆成「Mod talk 原语 + 脑侧购买」

- 真机只读探针（machine-runner `9d97d5d`/`ad65c03`，`docs/_probe-backpack-dialogue.md`）六问：
  1. 进 SeedShop 不自动弹背包升级对话（触发的是世界事件 `3102768` 店内过场，推进 4 批结束）；
  2. **interact Pierre 未取得**：`observe`/`WorldSnapshot` 只给 `characters` 数量（`Contracts.cs:372`、`WorldSnapshot.cs:684`）；**技能表无 talk**（`SkillCatalog.cs:32-35` Executable 无、`:42-45` Planned 未实现）；`interact` 走 `GameLocation.checkAction`（`Skills.cs:271-370`）⇒ 柜台 10 格全 `[no_action]`；
  3. bridge **能**读 `ui.dialogueIsQuestion` + `ui.dialogueResponses`（`Contracts.cs:1042`）；
  4. 已试 6 条通道全败：货架 buy 20 条 / 进店事件推进 / 柜台 interact×10 / 店内寻路 / 店门 interact×4 / 截图核对（PrintWindow 黑帧样本已保留）；
  5. `dismiss_modal`（`AnswerRules.Pick`/`DismissDialogueExplicit` 走 `GameLocation.answerDialogue`）只能「答问」，不能「开对话」。
- Lead 离线 DB 级证据（`logs/_probe_sdvmeta/`，SDV 1.6.15.24356，未动游戏）：
  - `StardewValley.NPC` 有 `checkAction(Farmer who, GameLocation l) -> Boolean`；`StardewValley.GameLocation` 有 `getCharacterFromName(String) -> NPC`、`isCharacterAtTile(Vector2) -> NPC`、`characters: NetCollection`；`Game1.pressActionButton(...)` 存在。
  - `Stardew Valley.dll` 的 #US 用户字符串堆（UTF-16，offset `0x48b8d8`–`0x48bbc0`）实锤背包对话键：`Strings\Locations:SeedShop_BuyBackpack_Response2000`、`…_Response10000`、`…_ResponseNo`、`…_Question24`、`…_Question36`、`Backpack`，以及响应键 **`Purchase`**（与 `buyJojaCola` 同类用法）⇒ 该对话由游戏本体代码创建、扣钱、调 `Farmer.increaseBackpackSize`。
  - 另在 `0x4819fa`/`0x481a18` 见 `BackpackTip`/`pierreBackpack` 字符串（Game1 侧提示/一次性标记），不影响入口。
- 裁决：卡 A 拆两步 —— **task-33**（Mod 新原语 `talk`：找 NPC → 相邻校验 → `npc.checkAction(Game1.player, Game1.currentLocation)`，禁合成键鼠）→ **task-34**（真机只读探针：`talk Pierre` 是否开出背包提问、响应原文是否含 `Purchase`，永不应答购买）→ **task-25**（脑侧 `dismiss_modal{answerText:"Purchase"}` + 观测差分）。

### 7.4 事故风险：Town 事件 `15389722` 非确定卡死（产品缺陷线索）

- task-32 探针按 SMAPI 窗口 `Warping to Town` 原文逐段数：**5 次进 Town = 1 成功 / 4 卡死**（A#1 19:32 卡 484s、B#1/B#2/B#3 worldSeq 冻结 262s/360s/131s；唯一成功 A#2 推进到提问态后 `dismiss_modal()` 无参选否即走完；此前口头"3 次"按 goto 尝试估，已按一手数据更正）；卡死读数 `eventUp=true, eventId=15389722, activeMenu=null, isModal=true, canMove=false, worldAdvancing=false`、clock 冻结、worldSeq 不动；`advance_dialogue`→`[no_dialogue]`、`dismiss_modal` no-op、`move_to*`→`[ui_modal]`、店门 interact 全 `no_action`；**唯一恢复 = `load_save(force=True)`**。
- 卡死门限建议（同探针 §3.4）：`eventUp==true && activeMenu==null` + `advance_dialogue` **连续 10 次 no_dialogue**（≥30–60s）+ worldSeq 无变化/`worldAdvancing==false`（辅助）；**不得单用 clock/worldSeq/worldAdvancing**（成功样本 worldSeq 也冻结 124s 却走完）；默认 60s/10 次，自愈 load_save(force)，同小时 2 次自愈仍复发 ⇒ 诚实收尾；更稳做法是 mod 侧让 `advance_dialogue` 直接回 `stalled=true`。
- 影响面：农务长跑（A9/B9）不进 Town ⇒ 不触发；任何进城动作（卡 A 买背包）必须带「事件态持续 + 无 worldAdvancing ⇒ 记 `event_hang` + load_save(force) 兜底 / 当日诚实收工」的自愈逻辑（已写进 task-25 卡面）。长期：事件态识别与自愈应单独立卡（backlog）。

### 7.2 事故：`mod/AgentFarm.Bridge/bin/Release` 被 WIP 构建污染

- 现象（machine-runner 2026-10-18 19:2x 探针前发现）：`bin\Release\AgentFarm.Bridge.dll` = **291840B / mtime 19:23:25 / SHA256 `F05289C9D44D38762232E2410178CEF38B82037135943A26A086257E8A05E5B9`**，不是冻结 0.7.45 的 **286208B / `806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F`**（0.7.46 WIP 构建）。
- 风险：`tools\deploy-mod.py:154-172` 无条件从 `bin\Release` 复制 ⇒ 此时 deploy 会把 WIP dll 当 0.7.45 装机，覆盖冻结 dll、并使任何冒烟证据作废。
- 处置：machine-runner **跳过 deploy 的装机步骤**、直接启动已装好的冻结 0.7.45（装机目录 dll 286208B `806C1069…B17F` 18:54:09、manifest `DECBA677…` 0.7.45），探针继续；本条记为开发日志事故记录。
- **新硬检查（写入冻结九步第 7 步）**：任何 deploy 前必须核对 `bin\Release\AgentFarm.Bridge.dll` 哈希 == 冻结产物（或从冻结提交 `dotnet build -c Release --no-incremental` 重建后再核）；未核对不得 deploy。dev-coder 本地 C# 验证建议 `-o` 到隔离目录，避免仓库 bin 长期停在非冻结状态。

## 8. 口径裁定（2026-10-18 20:1x，Lead；防冻结后返工）

> 背景：deputy 离线预热提出 5 个待定口径（prep 草案在旧 smoke-0745 冬26 上"四门槛全过"，无法区分 0.7.45 前后行为）。以下为冻结前裁定，C 段验收照此写判据。

### 8.1 inventory_blocked 诚实收工：字段级五条件（全满足才认 day_justified=true）
- **E1** `day_end.ended_by == "inventory_blocked"`（该理由只由 clear 步因满包被拒时写入）；
- **E2** 观测可用且真满：`day_end.free_slots_status == "ok"` 且 `day_end.free_slots_last == 0`（不用 `min`，`min==0` 只说明某刻满过）；
- **E3** 腾格已用尽（字段级）：当天存在 ≥1 次 `slot_relief` 事件（`trigger=="space_pressure"` 或 `demand_basis=="buy_full"`），且**最后一次腾格尝试之后**无 `freed>0`；且其后不再出现可卖白名单 `sell`（`strategy=="slot_relief_space"`）事件；
- **E4** `day_end.pending_executable == 0` 且 `day_end.pending_malformed == 0`（`pending_unobserved` 允许 >0）；
- **E5** 浪费有界：`day_end.loot_lost_steps <= 5`（卡 D 常量）。
- 反向三例必须 False：冬27 形态（loot_lost_steps=205）、满包但 `pending_executable>0`、满包但最后一次腾格之后又有成功卖出。
- 旧 smoke-0745 冬26 在 0.7.45 下 `day_justified=false` 是旧代码无 E1 白名单项；0.7.46 起它应为 True——**这正是门禁第②条要看的行为变化，不是缺陷**。

### 8.2 卡 A 观测面与差分窗口
- `observe('summary')` 的 `player.inventoryCount`/`player.money` 已直出（0.7.45 真机账本验证）。
- 购买差分窗口**必须同一天且不跨 NewDay**：`before` 紧接 talk/应答前，`after` 在应答后 1–2 tick；窗口内出现 `sell`/`ship`/`NewDay` 事件或 `shippingBin.count` 变化 ⇒ 记 `money_diff_ambiguous` 判该次失败（不计成功、不许另算）。
- 负对照：同窗口不买、observe 两次，`money` 必须不变（进探针/单测）。
- 结构断言：`after.inventoryCount == 2*before.inventoryCount`（12→24）且 `money_after == money_before - 2000`。

### 8.3 `resume_budget_exhausted` 不进 `is_justified_end` 白名单
- 保持 `day_justified=False`（预算耗尽≠证据门）；代价：这类日子不计入 5 日 streak；5 日窗口内出现 ≥2 天按缺陷升级（另卡提预算/改换片），不许放宽判据。
- 证据要求：`no_progress_burst` 的 `walks/attempts/limits` 齐全且 `claim_exhausted==false`；缺任一 ⇒ 该日【无法判定】并红。

### 8.4 task-33 `talk` JSON 契约（冻结）
- exec：`POST /v1/exec {"skill":"talk","args":{"npc":"Pierre"}}`（大小写不敏感；可选 `"npcTile":[x,y]`）。
- 回执：`{ok, applied, code:"ok"|"npc_not_found"|"not_adjacent"|"no_action"|"not_supported", npc, npcTile, distance, available(仅 npc_not_found), activeMenu, dialogueIsQuestion, dialogueResponses}`。
- 判定：`code=="ok" && applied==true` ⇒ 必须同时有 `activeMenu`（DialogueBox/ShopMenu）或 `dialogueIsQuestion==true`，否则判实现缺陷（红）。
- `dismiss_modal` 接口不变（`answerText` 精确匹配 / `answerIndex`）。
- 禁区：talk 内不得改 Money/Items/MaxItems、不得调 `increaseBackpackSize`、不得合成键鼠。

### 8.5 task-32「无可自动化入口」与卡 A 的张力
- 冻结后按 task-34 实跑 walkthrough 三档判：`talk` 开出背包提问且响应含 `Purchase` ⇒ 卡 A 继续；`talk` applied 但只有普通商店/其它对话 ⇒ 卡 A **停**（记"入口形态不符"，Plan B 另裁）；`talk` 不可 applied ⇒ 记【无法判定·入口不存在】，卡 A 停。
- **不许用推理替代实测**，不许拿 0.7.45 失败当 0.7.46 结论。

### 8.6 对 deputy 重放草案的补充判法
- J2（旧账本冬27 `resume_exhausted` + `pending_executable=7`）在 task-26 之后是**旧形态、新代码不可复现**：改判"source 级证据（`claim_exhausted=(exec==0 and malformed==0)`）+ 单测反向用例"，旧账本不一致只记【0.7.46 起不可复现】，不当卡 FAIL。
- J3（`223−218=5`）已由 log-analyst 判【无法判定】（5 格属 `self.blocked`，坐标未落账）；冻结树验收只核「独立复算=223 且 5 格差额可解释」，既不当缺陷也不当 PASS。
- prep 的 4 个产物留 scratch 不提交；task-31 正式报告时把 `.py` 按路径 `git add -f` 提交，证据 `.txt` 留 logs/scratch（被忽略）。
