# 0.7.46 冻结树对抗验收（task-31）

> 验收人：deputy-lead（独立对抗验收）。日期：2026-10-18。
> 对象：`737c4a5`（`chore(release): 冻结 0.7.46（售材纪律/背包满门槛/回片区预算/挡死格口径/talk 原语/背包升级）`），3 文件 +32/−4（`brain/agentfarm/bridge.py` +32、`mod/AgentFarm.Bridge/manifest.json`、`tools/_note-0746.txt`）。
> 范围：`docs/_review-0.7.46.md` + `scratch/`。**只读生产代码；未碰游戏/桥、未 deploy、未改任务板、未写 `docs/00-开发日志.md`**。判据全部自写（探针/变异脚本在 scratch/），未抄作者脚本。

## §0 判定摘要

| 项 | 读数 |
|---|---|
| 冻结树 | `git archive 737c4a5` → 临时树；**tracked 776 / extracted 807**（+22 夹具与运行缓存）/ missing 0 / mismatch 0；9 关键文件 `git hash-object` **9/9** |
| A 段（provenance/范围） | **28 PASS / 0 FAIL / 1 INFO** |
| B 段（独立复现） | **34 PASS / 0 FAIL / 5 INFO** |
| C 段（对抗通道） | **20 PASS / 0 FAIL / 2 INFO**（11 组 / 22 条） |
| D 段（变异两列） | **5 PASS / 0 FAIL / 13 INFO**（作者 20/20 实测复现；我方 12/12 被杀） |
| E 段（读数） | **3 PASS / 0 FAIL / 1 INFO**：`py_compile -W error::SyntaxWarning` rc=0；四卡定向 **Ran 35 / OK**；冻结树全量 **Ran 1377 / OK (skipped=11)** |
| 合计 | **PASS=87 / FAIL=0 / SKIP=0 / INFO=22** |

**判定：PASS-WITH-NITS。**
- **0.7.46 代码面可放行 smoke-0746**（四卡 + task-33 talk + task-25 背包升级的改法覆盖、语义键/checks/护栏 B 未动、冒烟旧形态不可复现、talk 零作弊、售材 fail-closed 全部通过独立复现）。
- **A9/B9 仍不能凭本次验收放行**：本次是离线冻结树验收，尚未有 0.7.46 真机读数；必须等 **smoke-0746 六条门禁全绿**（见 §7）后再谈 A9。0.7.45 的 2 天 needs_review 不作 0.7.46 结论（Lead m01581 裁定）。
- 差什么：①smoke-0746 ≥1 天 `verified=true`；②真机账本出现 `inventory_blocked` 且 E1–E5 五证据齐、`day_justified=true`（0.7.46 新行为，旧 0.7.45 冬26 应当 False）；③冬27 形态（`resume_exhausted` + `pending_executable>0`）不可再出现；④全程 0 条 `stuck:`；⑤满包压力下 0 笔建材/锭卖单；⑥落盘六串配对 2/2 + guardian 干净。

## §1 验收对象与冻结树

- 冻结提交：`737c4a5`（3 files +32/−4）；前置：`6528e47` 卡片读数、`0ffe11c` 我的预热脚本、`844e63c` 冻结记录/开发日志 090。
- 装机读数（Lead）：dll **293888B** `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A`（含 talk，比 0.7.45 286208B 大）；manifest **75293B** `84FBA465…2915C9A0`；`check-release --expect 0.7.46` 六项全绿、全量 Ran 1383 / OK；C# 自检 97 断言；preflight ✅；游戏优雅退。
- 冻结树提取：`git archive 737c4a5 --format=tar` → Python `tarfile.extractall(filter="data")`（中文名正常）。**`git archive` 不含被 `.gitignore` 的夹具**，已按 task-10 #3 补：`scratch/_ledger*` 20 个、`logs/longrun-runA8-0743.jsonl`、`logs/longrun-smoke-0745.jsonl`、`-gaps.json`、`-lessons.json`，另补 `logs/longrun-smoke-0744.jsonl`（全量单测需要；见 NIT-6）。provenance **在补夹具前**跑（A0），先证纯出。
- 关键文件 blob（`git hash-object` 与 `git rev-parse 737c4a5:<path>` 逐一对上，9/9）：

| 文件 | blob sha1 |
|---|---|
| `brain/agentfarm/longrun.py` | `bcb98bbe51b5` |
| `brain/agentfarm/farmwork.py` | `1e36e03bd4c1` |
| `brain/agentfarm/bridge.py` | `9d03acebb1f9` |
| `tests/test_longrun.py` | `fb40717f59d4` |
| `mod/AgentFarm.Bridge/manifest.json` | `ac50be507b12` |
| `tests/_mutate_t25_dialogue.py` | `3592c50813b6` |
| `tests/_mutate_t26_budget.py` | `0c1bafcda674` |
| `tests/_mutate_t27_enclosed.py` | `11693456047d` |
| `tests/_mutate_t28_bag.py` | `7e34d2163e62` |

## §2 A 段：provenance 与范围

- **A0**：`737c4a5` tracked 776 / extracted 807 / missing 0 / mismatch 0（多出的 31 = 22 夹具 + 运行期 `__pycache__` 等）。**A0b**：9 关键文件 9/9 相等。
- **版本面**：A1 `bridge.py MOD_VERSION_EXPECTED="0.7.46"`；A1b `manifest Version=0.7.46`；A1c 冻结树 manifest **75283B**、Lead 报 75293B —— 属 CRLF 差异（`git archive` 出 LF），**INFO 不判红**（冻结提交内 blob 已由 A0b 证明一致）。
- **checks 10 键未动**：`slept_by_us / no_blocking_modal / no_hard_failures / unreachable_within_bound / refused_within_bound / no_unmet_stages / crops_watered / watered_outdoor / day_justified / zero_action_evidenced`，顺序与 0.7.45 一致；A2b 无新字段混入 `checks`。
- **DayReport 新字段恰 10 个**（三卡并集）：task-25 `backpack_capacity_before/after`、`backpack_upgrade_ok`、`backpack_upgrade_attempts`、`backpack_upgrade_failures`、`backpack_upgrade_skip`；task-28 `relief_exhausted`、`bag_evidence`；task-27 `pending_executable_tiles`、`pending_stalled_tiles`。A3b 无字段被删。
- **journal 事件名 0 增删**：task-25 复用 `buy`（`source="backpack_dialogue"`），task-33 talk 不加新事件，task-26/27/28 都复用既有事件并加字段 —— 与"无新 journal 事件名"要求一致。
- **公式未动**：`no_unmet_stages` 逐字同 0.7.45；`unreachable_bound = max(5, int(0.2 * bound_basis_steps))` 与 refused 同式；护栏 B（`cleared_tiles`/unreachable 计数）未动。
- **malformed 一票否决在全部白名单之前**：A6 取 `is_justified_end` 函数体（先剥 docstring），`if int(malformed_tiles) > 0: return False` 位于 `veto@239`，早于任何前缀白名单（`@436`）——满足 Lead 的"A 段重点"。
- **满包写入端门槛**：A7 `_note_inventory_blocked` 的 `accepted = not gaps`，gaps 逐条检查 `free_slots==0` / `relief_exhausted` / `pending_executable==0` / `pending_malformed==0`；A7b `CLEAR_LOOT_LOSS_MAX_STEPS = 5` 且 clear 闸按剩余额度收窄。
- **逐卡改法覆盖**（A8–A12d 全 PASS）：task-26 `claim_exhausted = (exec==0 and malformed==0)`、无证据写 `resume_budget_exhausted:`、burst 带 walks/attempts/limits；task-27 目标池前置过滤 + 四邻全观测证据；task-28 建材/锭移出可卖表（只剩 92/766）；task-25 成功=观测差分；task-33 talk 唯一入口 `found.checkAction(who, loc)`、源码无写钱/背包/键鼠、回执契约字段齐、已注册 catalog/Skills。
- 越界扫描：本次未改生产代码；工作树仅他人在制 `scratch/_t34_talk_probe.py`（未触碰）。

## §3 B 段：独立复现（夹具 = smoke-0745 旧账本 + A8 账本）

**B1 旧账本形态（0.7.45 的 smoke-0745，只作历史，不当 FAIL）**
- 冬26（E1–E5 逐条）：`E1_理由=True`、`E2_最后观测真满=False（last=1）`、`E3_腾格用尽=False`、`E4_无可执行无残缺=True`、`E5_浪费有界=False（loot=21）` ⇒ **旧代码不认，正确**；0.7.46 起该形态必须 `day_justified=true`（门禁②要看的行为变化）。
- 冬27：旧账本 `resume_exhausted` + `pending_executable=7` ⇒ 0.7.46 的 `claim_exhausted=(exec==0 and malformed==0)` 必为 False ⇒ **该旧账本组合在新代码下不可复现**，只记【0.7.46 起不可复现】，不当卡 FAIL（Lead m01581 ⑥）。
- A8 账本：12 天 `deferred_by_budget` 与 `watered_outdoor=true`/`dry=0` 同真 **12/12**（task-6 面未回归）。
- 冬26 32 格归因复算：**till_area 12 + clear_area 20 = 32**，旧账本 `encircled=0 / prefiltered=0`（旧代码无 task-27 证据字段）⇒ 逐格"该不该归 encircled"对旧账本【无法判定】，只能按 stage 复算口径记；真机 0.7.46 账本必须带 encircled/prefilter 证据。
- 旧账本售出 `{262, 330, 388, 535, 92}`：禁售命中 **330(C)/388(Wood)**；`92(Sap)` 保留但旧账本无归类依据字段（NIT-7）。

**B2 `is_justified_end` 动态 11 例**：malformed=3 ⇒ False（否决生效）；`resume_exhausted+exec>0` ⇒ False；`resume_exhausted+exec=0` ⇒ True；`inventory_blocked+exec=0` ⇒ True；`inventory_blocked+exec>0` ⇒ False；`stuck:` ⇒ False；`resume_budget_exhausted` 即使 exec=0 也 False（不入白名单，Lead m01581 ③）；`night/stamina/no_work` 仅 sleep 生效；`ended_by` 缺失/未知 ⇒ False；malformed+exec=0 ⇒ False。**bad=[]**。另 B2b 确认 `checks.day_justified` 调用同时传 `pending_executable` 与 `malformed_tiles`。

**B3 pending 快照 / resume 证据闸门**
- 冬27 七格形态重放：`snap={'ledger':7,'guard':7,'stalled':0,'blocked':0,'executable':7,'unobserved':0,'malformed':0}` ⇒ `claim_exhausted=False`（B3b），即旧形态"exec>0 却宣称无目标"被关闭。
- `exec=0 & malformed=0` ⇒ `claim_exhausted=True`（B3c）；残缺 tile ⇒ `malformed=1` ⇒ False（B3d，NIT-1 原形不可复活）；不变式 `ledger==guard+blocked`、`guard==executable+unobserved+malformed` 成立（B3e）。

**B4 挡死格证据口径（task-27）**：四邻全观测 + 都不可站 + 无可清障邻格 ⇒ `enclosed`；缺邻、可站邻、可清障邻（乐观可站）⇒ **不判死**；预过滤把已判死格剔出目标池并 `encircled` 留痕（`prefilter=True`），不进 `unreachable`（B4e kept=[]、entries=1）。⇒ 真走不到仍计、挡死不丢证据。

**B5 售材白名单（task-28）**：可卖表 = 材料 `{92,766}` + 39 作物 + 高价值 `{535,536,537,538,72,74,749}`；十类禁售 qid `{388,390,330,771,382,378,380,384,386,909}` 不在任何可卖表；锭/升级材料 `{334,335,336,337,338,787}` 在 `SLOT_RELIEF_NEVER_SELL_IDS`。动态：满包压力下 plan 只挑 `(O)92`，**不挑 388/330**；把 334/787 放进背包也不挑 ⇒ **双保险**（表 + 永不卖守卫）成立。

**B6 背包升级对话购买（task-25 观测差分）**：成功 `money 3264→1264`、`cap 12→24`、`rep.backpack_upgrade_ok=True`（B6）；失败面：`money_unchanged ⇒ money_not_deducted`、`capacity_unchanged ⇒ capacity_not_changed`、窗口跨日 ⇒ `money_diff_ambiguous`、`response_missing ⇒ response_not_found`、`response_ambiguous ⇒ response_ambiguous`、`no_question ⇒ dialogue_not_question`、`npc_not_found`、`no_action` —— 全部失败码正确且**钱未动**。"进背包计数增量"旧判据未出现。

**B7/B8 task-33 talk（源码面）**：不相邻 ⇒ `not_adjacent` + `applied=false`、不替脑走路；`applied` 但无 `activeMenu`/非提问 ⇒ `not_supported`（fail-closed）；`npc_not_found` 带 `available`（≤30）。C# 源码红线：只调 `found.checkAction(who, loc)`；`TalkRules` 原文"不改 Money/Items/MaxItems"；C# 自检断言禁 `Money =`/`MaxItems =`/`.increaseBackpackSize(`/`SendInput`。**运行时 dotnet 自检/真机 drop-in 本次未跑 ⇒【无法判定】**（作者/Lead 报 97 断言）。

## §4 C 段：对抗通道（22 条 / 11 组，全部按"防洗白"设计）

| 组 | 通道 | 结果 |
|---|---|---|
| C1 | `inventory_blocked` 有可执行格仍放行？ | PASS（False） |
| C2 | 删 malformed 否决的等价行为 | PASS（malformed=3 仍 False） |
| C3 | `resume_exhausted` 门槛清空 | PASS（exec>0 ⇒ False） |
| C3b | `resume_budget_exhausted` 混进白名单 | PASS（即使 exec=0 也 False） |
| C4 | 生产代码直写钱/物品/背包容量 | PASS（`_code_only` 后 hits=[]） |
| C4b | 卖东西绕过桥 `self.c.sell(`（Farm.shipItem）直改背包 | PASS |
| C5 | 清障丢失上界被放宽 | PASS（常量=5 且闸门收窄） |
| C5b | `loot_lost_steps` 塞进 checks | PASS（只 info，不进 10 键） |
| C6/C6b | 新字段污染 checks 10 键/序 | PASS |
| C7/C7b | 挡死格归 `already` 而非 `encircled`；判死格回填成功集合 | PASS |
| C8 | 抬高 `unreachable_bound`（0.7.45 vs 0.7.46 逐字） | PASS（两版公式逐字相同；两行 INFO） |
| C9/C9b | 满包闸不看证据；证据不可读时猜 0 | PASS（只认 free==0 且 exhausted；不可读不闸） |
| C10/C10b/C10c | talk 作弊写钱/背包/键鼠；替脑走路；用"进背包计数"当成功判据 | PASS（hits=[]；仅 checkAction；成功=观测差分） |
| C11/C11b | 收尾仍写 `stuck:回片区` / `stuck:同一秒连发`；无证据时冒充无目标 | PASS（代码面无 `stuck:`；无证据改 `resume_budget_exhausted:`） |

## §5 D 段：变异两列（冻结副本跑；"副本跑"=复制冻结树→文本变异→probe+定向单测）

**D1 作者脚本（自报 vs 实测）**

| 脚本 | 目标类 | 自报 | 实测（副本） | 红用例摘要 |
|---|---|---|---|---|
| `_mutate_t25_dialogue.py` | `TestTask25BackpackUpgrade` | 4/4 | **4/4** | m1 trust_receipt 红 2；m2 direct_money_write 红 10；m3 response_guard 红 1；m4 attempts 红 1 |
| `_mutate_t26_budget.py` | `TestTask26ResumeBudget` | 3/3 | **3/3** | m1 失败走不耗成功预算 红 2；m2 放宽判据 红 1；m3 尝试上限 红 2 |
| `_mutate_t27_enclosed.py` | `TestTask27EnclosedBatch` | 8/8 | **8/8** | 8 条各红 1–2（prefilter 失效/挡死当 already/optimistic foothold/列表删等） |
| `_mutate_t28_bag.py` | `TestTask28BagEvidence` | 5/5 | **5/5** | m1/m5 Wood 回白名单 红 1/5；m2 满包无条件 红 1；m3 clear 闸删 红 1；m4 loot 上限删 红 2 |

**D2 我方变异（12 条，全部实测被杀；杀器 = 探针 B/C FAIL 或定向单测红）**

| 变异 | 被杀 | 杀器 |
|---|---|---|
| m31a malformed 否决删 | ✅ | probe FAIL×2 + 单测红 2 |
| m31b malformed 归回 unobserved | ✅ | probe FAIL×1 + 单测红 2 |
| m31c resume_exhausted 门槛清空 | ✅ | probe FAIL×2 + 单测红 2 |
| m31d inventory_blocked 无条件 accepted=True | ✅ | 单测红 1（写入端口径） |
| m31e Wood(388) 加回可卖表 | ✅ | probe FAIL×2 + 单测红 1 |
| m31f 绕过 `self.c.sell(` 直改背包 | ✅ | probe FAIL×1（C4b 代码级判据） |
| m31g 背包升级信回执不查差分 | ✅ | probe FAIL×2 + 单测红 2 |
| m31h loot 上限 5→50 | ✅ | 单测红 3 |
| m31i 新字段塞进 checks | ✅ | probe FAIL×2 + 单测红 1 |
| m31j unreachable bound 20%→50% | ✅ | probe FAIL×1（C8 逐字比对） |
| m31k talk 内直写 Money | ✅ | probe FAIL×1（C10 源码红线） |
| m31l 锭 334 塞可卖表 + 拆永不卖守卫（两处同破） | ✅ | probe FAIL×1（B5e 动态双保险） |

合计：作者 **20/20**（t25 4 + t26 3 + t27 8 + t28 5）实测复现；我方 **12/12**，未杀 0、异常 0。

## §6 NIT 单列 / 已知限制 /【无法判定】

- **NIT-1（工具卫生）**：作者 t27 脚本用 `结果：` 结尾，t25/t26/t28 用 `结论：`；我方探针已兼容两种文案。建议统一（不在本卡判定内）。
- **NIT-2（读数差）**：Lead 报全量 **1383**，冻结树实测 **1377**（skipped=11），差 6。夹具/未提交测试两树不同，**差额【无法判定】，不采信任何猜测**（与 task-21 的 1324 vs 1330 同类）。
- **NIT-3（字节差）**：冻结树 `manifest.json` 75283B vs Lead 报 75293B —— `git archive` LF vs 工作树 CRLF；A0b 已证 blob 一致，非缺陷。
- **NIT-4（运行时缺口）**：task-33 talk 的 C# 自检 97 断言与真机 drop-in 本次**离线未复跑** ⇒【无法判定】；仅源码审计（C10/B7/B8）通过。
- **NIT-5（旧账本证据缺口）**：smoke-0745 冬26 的 32 格在旧代码里没有 encircled/prefilter 证据字段（`encircled=0/prefiltered=0`）⇒ "每格该不该判死"对旧账本【无法判定】，只能按 stage 口径复算 12+20；不做缺陷处理、也不当 PASS。
- **NIT-6（夹具清单）**：纯 `git archive` 树跑全量会缺 `logs/longrun-smoke-0744.jsonl`（本次补上才 1377/OK）；后续冻结验收清单需含 smoke-0744（或让该测试自跳过）。
- **NIT-7（Sap 保留依据）**：`92 Sap`/`766 Slime` 留在可卖表，旧账本 `sell` 事件没有 category/归类依据字段 ⇒ 保留是否合规对旧账本【无法判定】；smoke-0746 账本需带 `sell` 的 tier/why 或归类依据。
- **NIT-8（写入端缺动态通道）**：m31d（`accepted=True`）只被作者单测杀，我方 C 段没有覆盖 `_note_inventory_blocked` 写入端的动态通道（C1 测的是 `is_justified_end` 读出端）。建议 0.7.47 把写入端四门槛也做成探针动态判据。
- **NIT-9（槽位/全量覆盖说明）**：`SLOT_RELIEF_CROP_IDS` 39 项/`HIGH_VALUE` 7 项未逐项与游戏数据核对（本卡只要求建材/锭移出与十禁售零卖单）；逐项正确性属数据面，未在本判定范围内。

## §7 放行建议：smoke-0746 / A9

**0.7.46：可放行 smoke-0746（PASS-WITH-NITS）。** smoke-0746 门禁（全部满足才放行 A9）：
1. `finish.code==0` 且 `verified_streak >= target_days`（≥1 天 `verified=true`）；
2. 冬26 形态：真机账本出现 `inventory_blocked` 且 **E1–E5 五证据全过**（E1 ended_by；E2 `free_slots_status=="ok"` 且 `free_slots_last==0`；E3 最后一次腾格后无 `freed>0` 且其后无 `slot_relief_space` 卖单；E4 `pending_executable==0` 且 `pending_malformed==0`；E5 `loot_lost_steps<=5`）⇒ `day_justified=true`；
3. 冬27 形态：`resume_exhausted` 仅当 `claim_exhausted=(exec==0 and malformed==0)`；否则必须是 `resume_budget_exhausted:` 且 `day_justified=false`（预算耗尽不进白名单；5 日窗口内 ≥2 天即缺陷升级，不许放宽判据）；
4. 全程 **0 条 `stuck:`**（允许有界诚实停，但必须是有名有据的前缀）；
5. 售材纪律：满包压力下 **0 笔** `388/390/330/771/382/378/380/384/386/909`；`92/766` 若卖出，账本须有 tier/why 归类依据；
6. `free_slots_*`、`loot_lost_steps`、`relief_exhausted`、`bag_evidence` 字段非空；`free_slots==0` 且 relief 用尽时 `loot_lost_steps<=5`；落盘六串配对 2/2 + guardian 干净。

**A9/B9 判定必读（双列口径）**：`day_end.stages[].already` 与 `ok`/`cleared` 必须**并列**读（`tools/verify-run3.py:1104/:1122` 只单列 ok，NIT 沿用 task-23 NIT-4）；A9/A8 起点不同不可跨对比较；`pending_ledger/guard/stalled/blocked/unobserved/malformed` 与 `pending_executable_tiles[:8]` 一起读；`slot_relief` 事件的 `trigger/demand_basis/failed/blocked_reason/round/max_rounds/pressure` 与 `sell` 的 `qid/tier/why` 一起读；`buy` 事件须带 `source=backpack_dialogue`、money/capacity before/after 与窗口无 sell/ship/day_start/day_end。
**真机行为变化核对点**：同一满包日，0.7.45 是 `day_justified=false`，0.7.46 应为 `true`（E1–E5 全过时）——这是门禁②要看的"修复生效"，不是新缺陷。

## §8 边界声明

- 本次只做**离线冻结树**验收：未进游戏、未起长跑、未 deploy、未改生产代码；真机行为不在此结论内。
- 判据为独立实现（`scratch/_t0746b_probe.py` + `scratch/_t0746b_mutate.py`），未抄作者脚本；夹具只借用作者 `FakeWorld/make_run` 当数据源。
- 变异一律在**冻结树副本**跑（`--base %TEMP%\t0746_frozen`，复制到临时目录后变异），冻结树与仓库工作树未被修改。
- 缺失/不可得一律写【无法判定】（NIT-2/4/5/7）；"没看到"不等于"通过"。
- 工作树中他人 WIP（`scratch/_t34_talk_probe.py` 等）未提交、未回滚。
