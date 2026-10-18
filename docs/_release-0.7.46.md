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
  3. **till 批量把 32 个「四邻都站不过去」格记成 unreachable**（冬26 32>bound 15 ⇒ 判据红）；clear 有 encircled 归类，till 没有。
  4. **day 级 7 格可执行与守卫口径未闭合**（冬27 守卫仍说剩 7 格、resume 拿不到；`pending_blocked 223 − pending_stalled 218 = 5 格`来源未单列）。

## 1. 卡片（dev-coder 串行 A→B→C→D）

| 卡 | 任务 | 优先级 | 提交 | 读数 |
|---|---|---|---|---|
| A | task-25 背包升级经济动作（SeedShop 买 Backpack 2000g，12→24；能力型差分判据：钱−2000 且 inventoryCount 12→24；走 `ShopMenu.tryToPurchaseItem`） | P0 | 待填 | 待填 |
| B | task-26 冬27 形态 day 级 7 格逐格归因（L641 burst samples 坐标 → 为何 resume 拿不到；5 格未单列；10 格账本差；冬26 plot_pending_executable=3 不同源）；核 ended_by=sleep 与 resume_exhausted 自洽 | P0 | 待填 | 待填 |
| C | task-27 till_area 32 格前置过滤 + 事后 encircled 归类（不计 rep.unreachable、后续阶段不再选）；bound 公式不动 | P1 | 待填 | 待填 |
| D | task-28 售材白名单收紧（建材/锭类全部移出）+ inventory_blocked 证据门槛 + 满包清障有界（loot_lost_steps ≤ 常量，留痕） | P1 | 待填 | 待填 |

## 2. 冻结九步（沿用 0.7.44/0.7.45 口径）

1. 写 `tools/_note-0746.txt`（本批四卡一句话 + 冻结前置）。
2. `python tools\_bump-mod-version.py 0.7.46 --note-file tools\_note-0746.txt`（manifest Version + Description 头）。
3. 改 `brain/agentfarm/bridge.py` `MOD_VERSION_EXPECTED = "0.7.46"` + 新注释块（旧块移 `# --- 历史 ---`）。
4. `dotnet build -c Release --no-incremental`（0 警 0 错）+ C# 自检（`dotnet run -c Release`，OK 91 断言）+ `python -W error::SyntaxWarning -m py_compile brain\agentfarm\bridge.py`。
5. 按路径 `git add`/`git commit`（禁 amend / 禁 add -A；bridge.py、manifest.json、_note-0746.txt）。
6. `python tools\check-release.py --expect 0.7.46`（六项全绿：版本一致 / dll 不比源码旧 / py_compile / 全量单测 / 工作树干净）。
7. 部署前核对（无 Stardew 进程、仓库根与 %APPDATA% 无 bridge.json、17890 无 LISTENING）→ `python tools\deploy-mod.py --no-quit`（ALSOFT_DRIVERS=null）。
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

1. 背包升级条目在 SeedShop 货架 20 条中是否真的存在**尚未真机确认**（`buy` 回执 `availableItems` 20 条、文字 Listing 只列 12 条）——machine-runner 只读货架探针产物 `scratch/_t18_shop_shelf.json` 为准；若不存在 ⇒ 卡 A 停、Plan B=木箱（Chest 50 木），Lead 另裁。
2. 建材/锭类移出白名单后可腾格项变少 ⇒ 满包时更容易诚实收工；结构性解法是背包升级（卡 A），不是放宽白名单。
3. 冬26 40 格（263−223）账本无坐标 ⇒【无法判定】，不参与任何 PASS 结论。
4. 0.7.45 的 `stage_midway_leftover` 遮蔽形态仍有（8 条/1 天），只 info。
5. 春季农务腿（crops/watering/harvest）仍未真机验证；smoke 用 `--no-crops`。

## 6. 冻结记录（待填）

- 冻结提交：待填
- 版本一致性 / dll 指纹 / manifest 指纹 / build 读数 / C# 自检 / check-release / 装机 / goto Farm / preflight baseline / 优雅退：待填
