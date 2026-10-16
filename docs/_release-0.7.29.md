# 0.7.29 发布计划（LLM 演进素材修复 + 0.7.28 遗留）

> 冻结前置：本版卡片全部 completed + 独立对抗验收 PASS（口径变更/对照机制类卡片必须过验收）。
> 上一版：`docs/_release-0.7.28.md`（run8 两病灶 + LLM 演进第一批；2026-10-16 已装机，run9 = run A 正在跑）。

## 0. 为什么有这一版（run9 实证）
run9（0.7.28）**已收尾，实测 0/5 VERIFIED**：`finish {"code":1,"verified_streak":0,"actions":436,"minutes":23.62,"no_unmet_stages":false,"unmet_days":["1年 summer 13日","1年 summer 16日"],"stuck_flushes":2}`；5 个日报告 13 `stuck`(ok35) / 14 `sleep`(ok62) / 15 `sleep`(ok94) / 16 `stuck`(ok108) / 17 `slept_without_work`(**ok0**)，**每天都 `day_justified=false`**。它把「决策演进」的**素材链**与「白丢整天」的堵点一起暴露了：

1. `review_llm_failed {"t":217.45,"reason":"llm_error:truncated: 回答被 max_tokens 截断且内容为空（推理占用了约 512 个 token）…"}` ⇒ 复盘笔记基本为空（整轮 `review_llm` 成功 **1** 次、失败 **3** 次）⇒ 教训库 `hint` 永远空 ⇒ run B 无教训可注入（**L1 不可能成立**）。
2. `lessons {"total":0,"added":[],"written":0}` 前四天，第五天才 1 条（`slept_without_work|day`）⇒ 现有 8 种 kind 覆盖不到「`stuck` 收尾 + leftover 而 `failed=0`」这种最典型退化形态。
3. `cannot_afford {"money":88,"seed_price":20,…}` 而当天更早已用 88g 买到 10 个 Wheat Seeds ⇒ 判据按「买满 `--buy-count`」算账，钱只够买一半时**当天一粒不买**。
4. **review-only 空转（本版新增的第 4 张卡）**：61 条 `['review']` 独苗决策全是 `source=deterministic, llm=false`（LLM 的 20 条边界决策每条都带真活）——`deterministic_plan()` 只看**当前片地**的 `_plot_brief`（`brain/agentfarm/planner.py:1441-1527`），守卫 `work_reasons()` 看的是**跨片地当日 leftover**，两边**没有对账路径**（`brain/agentfarm/longrun.py:3183-3185` 放行非阶段意图、`:3264-3266` review 不置 `acted`、`:3199-3207` 兜底只在 kept 为空时调用）⇒ 空转 3 轮 ⇒ `stuck`。第 5 天同族：守卫说"没种子但钱够该去买 + 73 格干作物"，却**没有任何片地拿得出目标**。
5. **【P0，本版最高优先】出货日跨日不落盘**：run9 每天出货（`sell` 5 次 + `surplus_sell` 4 次 `need_slot`）⇒ SMAPI **4 NewDay / 0 before save / 0 Save called / 0 completed**，存档 start==end（`3706657 B / 2026-10-15 22:22:57.011`）⇒ **5 个游戏日一次未落盘**，整跑不能作为验收依据或 run A 基线（`docs/_run6-criteria.md` §2 已收紧为"每次跨日必须落盘，NewDay>save 即硬问题"，commit `99eb8e0`）。根因（task-126 IL 定案 `docs/_il-shipmenu-save.md`）：出货日日切保存的唯一入口在 `ShippingMenu.update()` 内，需私有 `outro==true`（玩家点 OK ⇒ 私有 `okClicked()`）才建 `SaveGameMenu`；我们 `mod/AgentFarm.Bridge/ModalDismiss.cs:106` 的 `exitThisMenu()` 把它掐断 ⇒ 日推进、盘不落。修法卡 **task-129**（`ShippingMenu` 禁 dismiss，反射 `okClicked()` + wait-only；`SaveGameMenu` 一律 wait-only）。
6. 经济闭环四腿**各自成功但跨日衔接**（详见下方"好消息"）：`sell` 5/5、次日到账 → `buy` 9 次成交 8（当季 `(O)483`）、`plant_area` 10/23/16/19 格；`no_space` 死锁不再复现（`buy_no_space` 0，run8 是 25）；`slept_without_work` 守卫生效（summer 17 `ok=0` 被拦住、游戏日不推进）；死苗 5 天 `dead_crops=0`/`dryDeadCrops=0` ⇒ **真空未验**。
> 好消息（同一次真机取证）：经济闭环四腿已跑通（`sell{need_slot}` 腾格 → 自动跳过春季 `472` → 买当季 `(O)483` → 播种 4→13；次日出货到账 88→415 → 再买 10 个；整轮 `sell` 5 次成功、`buy` 8 ok / 1 failed），窗外干作物 `[12,30]`/`[60,29]` 也浇成 `ok`。

## 1. 卡片
| 卡 | 内容 | 归属 | 是否本版 |
|---|---|---|---|
| task-121 | `REVIEW_MAX_TOKENS` 512→4096 + 截断自愈重试 1 次（8192）+ 失败留 `max_tokens`/`attempts` | dev-coder | ✅ |
| **task-126** | **P0 闸门**：钉死 `showEndOfNightStuff()` 的日终菜单链（`ShippingMenu` → `SaveGameMenu`），修掉"我们清模态把日切保存链掐断"（run9 实测 **4 NewDay / 0 save**，整跑未落盘）；交付 `docs/_il-shipmenu-save.md` + 修法 | log-analyst（取证）+ Lead 定修法 | **✅ 必须先过** |
| task-122 | 教训库新增 `stuck_with_leftover` / `plot_exhausted` 两类（含"干净日仍然 0 条"用例） | dev-coder | ✅ `affa7c8` |
| task-123 | 买种子量力而行（`n=min(buy_count, money//price)`，`n>=1` 则 `buy_partial`） | dev-coder | ✅ |
| task-124 | review-only 决策不许白过：用守卫据以抱怨的那份 leftover 挑片地/挑格兜底（≥8 单测） | dev-coder | ✅ |
| task-101 | `_farm_totals` 类型校验（`"abc"` 会让整天崩）、窗口全死苗 `watered_outdoor` 字段级收口 | dev-coder | 择机 |
| task-107 | Mod `farm.dryTiles` 与 `farm.dryCrops` 同源 + `scanSeq` | dev-coder | 择机 |
| task-109 | 卖货如实性（`need_slot` 分支不可达/卖了最大叠）+ 卖后刷新 obs | dev-coder | 择机 |
| task-110 | `ensure_location` 无 try/except ⇒ `BridgeError` 穿出 `run()`（老洞，无 finish/day_end） | dev-coder | 择机 |
| task-117 | 教训库合并后 `count` 重钳 + 同 id 合并不得掉出持久化库 | dev-coder | 择机 |

## 2. 冻结与装机（九步，Lead 独占）
1. 确认 §1 标记 ✅ 的卡片全部 completed，且 task-122（口径/素材类）过了独立对抗验收。
1b. **P0 硬闸门（task-126）**：`docs/_il-shipmenu-save.md` 定案 + 修法落地 + 真机验证"关掉日终菜单后仍完成一次 `SaveGame.Save()`"（判据 = SMAPI `NewDay` 次数 == `Context: before save.` 次数 == `SaveGame.Save() called.` 次数 == `completed without exceptions` 次数，逐条配对）。**未过此闸门不许起 run9b**——run9 的 0/4 落盘使整跑证据链作废（见 `docs/_run6-criteria.md` §2 新口径）。
2. `tools/_note-0729.txt`：首串必须是 `v0.7.29（…）`，逐条写本版内容。
3. `python tools\_bump-mod-version.py 0.7.29 --note-file tools\_note-0729.txt` ⇒ `json.load` 核对 `manifest.json` 的 Version（脚本末句在 cp1252 下会 `UnicodeEncodeError`、退出码 1，**版本已写盘**）。
4. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.29"`（注释列本版内容）。
5. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 必须 0 警告 0 错误（本版若 **Mod 无源码改动**则只 bump 版本号）。
6. `git add -A && git commit`（工作树必须干净，`check-release` 会把未跟踪 scratch 算脏）。
7. `python tools\check-release.py --expect 0.7.29` ⇒ 六项全绿（manifest==brain==0.7.29、dll 不比源码旧、`py_compile`、全量单测 OK、树干净）。
8. `python tools\deploy-mod.py --no-quit` ⇒ 看 `modVersion=0.7.29` + 自动读档成功。
9. `python -m agentfarm goto Farm --no-focus` → `python tools\preflight.py --expect 0.7.29 --save-baseline logs\run9b-baseline.json` ⇒ 四项全绿。

## 3. 真机跑法（本版的核心目的：把演进素材链跑通）
1. **重跑 run A**（因为 0.7.28 的 run9 攒不到教训）：`logs\longrun-3day-llm-run9b.jsonl`，脱离式起跑器，**不做操作员预置**。
   - 关注：`review_llm`（成功、有 `notes`）与 `lessons {"added":[…],"total":≥1,"written":≥1}` 必须出现；`review_llm_failed` 允许出现但**不许每天都失败**。
2. **run B（run10）**：run A 收工后**同一存档线继续**跑 `logs\longrun-3day-llm-run10.jsonl`（唯一差异 = journal 路径 ⇒ 教训/笔记/决策史不同）。
   - 判据见 `docs/_run10-criteria.md` 的 **L1–L5**；对照取证用 `python tools\compare-runs.py --run-a logs\longrun-3day-llm-run9b.jsonl --run-b logs\longrun-3day-llm-run10.jsonl`。
3. 两次 run 都要：起跑前 `scratch\run8-snapshot.py --tag start`（显式传 `--pid-file`，脚本默认 PID 候选写死 run8！）、结束后 `--tag end` + 冻结 SMAPI 窗口 + `docs\_runN-evidence.md`（两侧工具原文 + 外部证据 + 本版关注项）。

## 4. 本版判据
- 硬：全量单测 0 红；`check-release` 六绿；装机 `modVersion` 一致。
- 主目标（P3 ⑥）：尾部窗口连续 **3 个游戏日 VERIFIED** + 四腿（清障/开垦/播种/浇水）+ **经济闭环**（卖→到账→买→种 四步留痕）。
- 演进：L1–L5（`docs/_run10-criteria.md`）；**L1–L3 任一不成立 ⇒ 写"不足以判定自我进化"**，不许含糊。
- 不变量：`day_after` 推进 ∧ `ok_steps==0` ∧ `verified==true` 三者绝不同时（`_stuck_flush` 有界例外）。
- 缺失字段一律【无法判定】，**缺失 ≠ 通过**。

## 5. 与 run9 对比（填表）
| 项 | run9（0.7.28，run A） | run9b（0.7.29，run A） | run10（run B） |
|---|---|---|---|
| `review_llm` 成功次数 | **1**（`review_llm_failed` 3 次，全 truncated@512） | | |
| `lessons.total` / `written` | **0 / 0**（前四天）→ 第五天 1 条 `slept_without_work\|day` | | |
| 经济闭环四腿 | 卖✅ 到账✅ 买✅ 种✅（`sell` 5 / `buy` 8ok+1fail） | | |
| 尾部 VERIFIED 天数 | **0/5**（`finish code=1, streak=0`） | | |
| `unreachable`/`stuck` 形态 | 13/16 `stuck`（剩 14 与 2 格）、14/15 `sleep` 仅挂 `day_justified`、17 `slept_without_work` ok0 | | |

## 6. 遗留
- task-101 / 107 / 109 / 110 / 117（若本版未做，顺延到 0.7.30）。
- task-14（逐帧 warp 活锁，run7/8 仍上千次 `Warping to Farm`）、task-18、task-53、task-83（田块规整）、task-98。
- run9 现场若再现"真·够不着的活苗"，当天如实 `gave_up_dry`/不 VERIFIED（不许洗白）。
