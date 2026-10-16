# run9b 证据（0.7.29 上的 run A）

**状态行**：已结束 —— `finish` @ `2026-10-16T22:30:13`，PID **12028** 已退出 · **判决：FAIL（尾部连续 VERIFIED 0/3、exit 1）** · **落盘配对 5/5 全过（run9 的 0/4 病已修）** · 完全 VERIFIED 的一天 ×1（summer 17）· 游戏已按用户政策优雅退出（`22:34:37`）。

**一句话结论**：run9b 把 run9 最致命的病（**跨日不落盘**）彻底修好 —— 5 次跨日 **NewDay / before save / Save called / Saving / completed / after save 逐次配对、存档逐次前进**；经济闭环四腿（卖盈余 → 次日到账 → 买种子 → 播种）真机走通；教训库 7 条非空（L0 达标）。但**尾部连续 3 天 VERIFIED 未达成**（尾部窗口 summer 16/17/18 = 未过/过/未过），原因集中在：`no_unmet_stages`（跨片地 leftover 未收口）、`day_justified`、`watered_outdoor`（`[12,30]` 等窗口外干格认输）与最后一天的 `slept_without_work`（守卫生效、当天不推进）。

---

## §0 摘要（五条最重要的读数）

| # | 读数 | 值 |
|---|---|---|
| 1 | 跨日落盘配对 | **5 次跨日 × 6 串全部配对**；存档 `3706657 / 2026-10-15 22:22:57.011` → `5766683 / 2026-10-16 22:30:13.053` |
| 2 | 尾部窗口 | `verify-run3.py --days 3`：**尾部连续 VERIFIED 0 / 要求 3** ⇒ `needs_review`；`analyze-longrun.py`：`VERIFIED 1/3`、窗口内红 45、历史 0 ⇒ 两侧同向 FAIL |
| 3 | 最强单日 | **summer 17：`verified=True`、九项 checks 全 true、`ok 70 / skip 0 / fail 0`、`final_water farm dry 0/56`** |
| 4 | 经济闭环 | `sell` 3 + `surplus_sell` 3（`why=need_slot`）→ 次日到账（summer 15 `day_start money 235`）→ `buy` 8（含 **`buy_partial` 2**）→ 播种多天有 ok |
| 5 | L0 教训库 | 7 条非空，`logs/longrun-3day-llm-run9b-lessons.json` = 3568 B / SHA256 `C2312F2D…86A0`（已按占位拷贝成 `run10-lessons.json`，**该占位不得用于判决**，见 §7.2） |

---

## §1 起跑与版本四要素

### 1.1 四要素

| 项 | 值 |
|---|---|
| `git rev-parse HEAD`（起跑时） | `06c4426fff406d9d51b50ac45baaee467b49d4d6`（`0.7.29 冻结: 出货日日切保存修活(P0, task-129) + review 空转兜底(task-124) + 复盘预算/教训覆盖(task-121/122) + 买种子量力而行(task-123)`） |
| `git status --short`（sidecar 记录） | `["M docs/00-开发日志.md"]`、`worktree_clean=false`（起跑瞬间有 1 项未提交；随后 `3a88840`（`docs/_release-0.7.29.md` +17 行，docs-only）与 `cbe42c4`（条目 057）落地，**被测五文件未变**） |
| `brain/agentfarm/longrun.py` | SHA256 `6CE4EA267A37810782BEAEAD484CDAE5D3F8CA554FF97C143120445739436724` / mtime `2026-10-16T21:50:37.018739` |
| `brain/agentfarm/farmwork.py` | SHA256 `4A39BC11ABCA3413D1608CCD58CC1F070CEA9F85EAB4AA87E809ED5E686C2D80` / mtime `2026-10-16T21:45:23.956930` |
| `brain/agentfarm/bridge.py` | SHA256 `648E988912C85FCF7DFB403A276120BCF900FB8F1605A052795A14EAED7AA507` / mtime `2026-10-16T21:57:24.901504` |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | SHA256 `02755488A532BA3D163010BAF985029B35B31C682D5AC025A9AD2E68D86297C7` / **177664 B** / mtime `2026-10-16T21:57:37.867712` |
| `mod/AgentFarm.Bridge/manifest.json` | SHA256 `8765A4735821B5B6ED6851731A0F076E01DA72A8E836334B6F68A77D3D76FB26` / **26454 B** / mtime `2026-10-16T21:57:34.089725` |
| 起跑进程 | `logs/longrun-3day-llm-run9b.pid` → **12028**，`started_at=2026-10-16T21:59:55` |
| 判定 | **`StartTime 21:59:55.726` 晚于全部被测文件 mtime ⇒ 进程加载的是 0.7.29 冻结版 ✅** |

sidecar 原文路径：`logs/longrun-3day-llm-run9b.version.json`；`argv` = `python -u tools/run-longrun.py --days 3 --size 5 --max-minutes 150 --max-days 9 --journal logs/longrun-3day-llm-run9b.jsonl`；`boundary_llm=true`。

### 1.2 起跑前三步

1. **start 快照**（`python scratch\run9b-snapshot.py --tag start --journal logs\longrun-3day-llm-run9b.jsonl --expected-mod-version 0.7.29`，`at 2026-10-16T21:59:31`）：
   - `save_main 3706657 / 2026-10-15T22:22:57.011`、`save_info 27913 / 2026-10-15T22:22:57.145`
   - `smapi_lines 417 / newday 0 / before_save 0 / save_called 1 / save_task 0 / completed 0 / smapi_save 3`
   - `bridge_info {pid 456, modVersion 0.7.29, port 17890}`、`expected 0.7.29`、**`mod_version_matches true`**
   - `pid_file_candidates [{logs\longrun-3day-llm-run9b.pid, exists:false}]`（新脚本按 `--journal` 推导 PID 候选，不存在的候选显式打印"候选不存在"）
   - ⚠ `save_called 1` 属 **窗口外**：`deploy-mod.py` 的自动 `load_save` 留下的那一次，不是本跑的动作。
2. **`--dry-run` EXIT=0**：四判据全绿、工作树 `True`；四要素与 §1.1 一致；基线（dry-run `21:59:42` / 真起跑 `21:59:55`）= `夏13日 tod 740→800`、`Farm(64,15)`、体力 270/270、血 100、**钱 188g**、`crops 6 / unwatered 2 / dryCrops 0`、`farmScanSeq 20→22`、`worldAdvancing true`。
3. **真起跑**（脱离式 `tools\start-detached-longrun.py`，`2026-10-16T21:59:55`）⇒ PID 12028；console `logs\longrun-3day-llm-run9b.console.log`、stderr `…console.err.log`；90 秒体检 = 存活 True / 账本 19 行 / stderr **0 B**。

### 1.3 两处口径报备

- Lead 卡面写作 `--mod-version 0.7.29`，脚本实际参数是 **`--expected-mod-version`**；start 行回显 `"expected_mod_version": "0.7.29"`、`mod_version_matches: true`（同一件事，口径已报备）。
- 起跑器当时报 `工作树干净=False`，来源是 `M docs/00-开发日志.md`（Lead 的开发日志，不是被测源码）；此后 `3a88840`/`cbe42c4` 两个 **docs-only** 提交落地，`git status --short` 随即为空，**五个被测文件 size/mtime 与 sidecar 逐项一致** ⇒ 版本四要素仍锚在 `06c4426`。

---

## §2 逐日表（6 个 `day_end`）

工具原文（`logs/run9b-verify.txt` L4–L10）：

```
日           ended_by      跨日    睡前未浇     作物    钱     阶段   ok   skip  fail  verified
summer 13   sleep         True  0        19    8     9    79   0     0     False
summer 14   sleep         True  0        7     235   13   107  3     0     False
summer 15   sleep         True  0        18    235   4    31   4     0     False
summer 16   sleep         True  0        28    235   2    16   0     0     False
summer 17   sleep         True  0        50    5     9    70   0     0     True
summer 18   slept_without_work False 0   0     205   0    0    0     0     False
```

| 日 | ended_by | `day_after` | verified | ok/skip/fail | 为 false 的 `checks` | `final_water` | 阶段（Σ ok） |
|---|---|---|---|---|---|---|---|
| summer 13 | sleep | summer 14 ✅ | False | 79/0/0 | `no_unmet_stages`, `day_justified` | `farm/Farm dry 0/24 tiles=141` | 9 阶段，water/till/plant/clear |
| summer 14 | sleep | summer 15 ✅ | False | 107/3/0 | `no_unmet_stages` | `farm/Farm dry 0/24 tiles=227` | 13 阶段 |
| summer 15 | sleep | summer 16 ✅ | False | 31/4/0 | `no_unmet_stages`, `watered_outdoor`, `day_justified` | 睡前还有没浇的作物 | 4 阶段（`gave_up_dry`，认输 3 格） |
| summer 16 | sleep | summer 17 ✅ | False | 16/0/0 | `watered_outdoor`, `day_justified` | 睡前还有没浇的作物 | 2 阶段（`gave_up_dry`，认输 3 格） |
| **summer 17** | sleep | summer 18 ✅ | **True** | **70/0/0** | **无** | `farm/Farm dry 0/56 tiles=199` | 9 阶段（`plant_area`/`till_area` 早轮 leftover 已收口） |
| summer 18 | **slept_without_work** | `null`（不推进） | False | 0/0/0 | `slept_by_us`, `day_justified` | `farm/Farm dry 0/56 tiles=200` | 0 阶段（守卫生效） |

逐日 `final`（人/钱/作物，来自 `analyze-longrun.py`）：

```
summer 13  final Farm      t=1440 体力=150   钱=8   作物=19 未浇=0 熟=0 可锄=200 种子=0
summer 14  final Farm      t=1630 体力=4     钱=235 作物=7  未浇=0 熟=0 可锄=168 种子=1
summer 15  final Farm      t=1140 体力=142   钱=235 作物=18 未浇=0 熟=0 可锄=200 种子=1
summer 16  final Farm      t=1140 体力=206   钱=235 作物=28 未浇=0 熟=0 可锄=200 种子=1
summer 17  final Farm      t=1530 体力=108.1 钱=5   作物=50 未浇=0 熟=0 可锄=62  种子=0
summer 18  final FarmHouse t=600  体力=270   钱=205 作物=0  未浇=0 熟=0 可锄=0   种子=0
```

逐日 `day_after` 链（Lead 复核器原文）：`summer 13→14→15→16→17→18` 前 5 次 **5/5 恰好 +1**；summer 18 `day_after=None`（守卫拦住、当天不推进）。

「睡前未浇」列 6 天全为 **0** —— 它取自 `day_end.final.counts_scope="window"`（人在 FarmHouse 时的窗口口径），**不能当浇水证据**；浇水一律看 `final_water`（farm 口径）与 `checks.watered_outdoor`。

---

## §3 落盘配对表（每次跨日六串齐全）

来源：冻结窗口 `logs/run9b-smapi-window.txt`（**340380 B / 4622 行 / SHA256 `BE5549886BEA2FBD2DFDE3212F7E9285E9F7348A937F3E156B565B1D5E8194E0`**，源文件 mtime `2026-10-16T22:30:17.140`，与源逐字节一致）。逐条抽取落 `logs/run9b-smapi-chain.txt`。

| # | `Synchronizing 'NewDay' task` | `Context: before save.` | `SaveGame.Save() called.` | `Saving without compression...` | `completed without exceptions.` | `after save, starting …` | 存档 size / mtime |
|---|---|---|---|---|---|---|---|
| 1 | L1008 `22:05:11` | L1020 `22:05:15` | L1021 `22:05:15` | L1023 `22:05:15` | L1025 `22:05:16` | L1026 `22:05:17` → **summer 14** | 3731582 / `2026-10-16T22:05:16.092` |
| 2 | L2167 `22:13:27` | L2169 `22:13:28` | L2171 `22:13:28` | L2173 `22:13:28` | L2175 `22:13:28` | L2176 `22:13:29` → **summer 15** | 3770274 / `2026-10-16T22:13:28.229` |
| 3 | L2881 `22:18:07` | L2884 `22:18:07` | L2885 `22:18:07` | L2887 `22:18:07` | L2889 `22:18:08` | L2890 `22:18:09` → **summer 16** | 3813991 / `2026-10-16T22:18:07` |
| 4 | L3511 `22:22:44` | L3513 `22:22:45` | L3515 `22:22:45` | L3517 `22:22:45` | L3519 `22:22:45` | L3520 `22:22:47` → **summer 17** | 3843606 / `2026-10-16T22:22:45.355` |
| 5 | L4598 `22:30:09` | L4610 `22:30:12` | L4611 `22:30:12` | L4613 `22:30:12` | L4615 `22:30:13` | L4616 `22:30:14` → **summer 18** | **5766683 / `2026-10-16T22:30:13.053`** |

- 计数：`NewDay 5 / before_save 5 / save_task 5 / completed 5 / after_save 5` ⇒ **逐次配对，无缺口**。
- **⚠ 工具自身的坑：`SaveGame.Save() called.` 原始计数是 6，真实是 5。** 多出来的那一条是 **L16 插件描述文本**（`[21:58:08 INFO SMAPI] AgentFarm Bridge 0.7.29 …` 的版本说明里写着"run9 实测 4 NewDay / 0 Save called"），被正则 `SaveGame\.Save\(\) called\.` 命中。机制写清楚的原因：**Lead 的独立复核器 `scratch/run9-lead-check.py` 也踩了同一个坑**，它据此报了两条 ❌（"before save(5) != Save called(6)"、"有 save(6) 无 NewDay(5) —— 保存没有对应的跨日"）——**这两条是假阳性**，实际 5 次跨日各自都配齐了 `NewDay → before save → Save called → Saving → completed → after save`。后续判据若要自动化，**必须先排除插件描述行（`INFO  SMAPI]  AgentFarm Bridge`）再计数**。
- 存档四条（收工时）：`Wahaha_450799035` **5766683** / `22:30:13.053`、`SaveGameInfo` **26933** / `22:30:13.055`、`Wahaha_450799035_old` 3843606 / `22:22:45.355`、`SaveGameInfo_old` 26891 / `22:22:45.356`。

---

## §4 两侧工具与 Lead 独立复核（原文）

### 4.1 `tools/verify-run3.py --journal logs\longrun-3day-llm-run9b.jsonl --days 3`

- 文本版（`logs/run9b-verify.txt`，57 行）：`行数 357 坏行 0`、`decision 44 条（LLM 调用 31 条 / 其中模型产出 31 条）`、`尾部连续 VERIFIED 天数 0 / 要求 3`、`结论：needs_review`；**问题 13 条**（原文）：
  1. `[summer 13] day_end verified=false`
  2. `[summer 13] checks.no_unmet_stages=false（有阶段后置条件未成立；自算有目标阶段 leftover=9 格）`
  3. `[summer 14] day_end verified=false`
  4. `[summer 14] checks.no_unmet_stages=false（… leftover=11 格）`
  5. `[summer 14] 0 目标阶段 leftover=5（task-15 修 A 后应为 0；请查 stage_no_target 分支）`
  6. `[summer 15] checks.watered_outdoor=false（睡前还有没浇的作物）`
  7. `[summer 15] day_end verified=false`
  8. `[summer 15] checks.no_unmet_stages=false（… leftover=13 格）`
  9. `[summer 16] checks.watered_outdoor=false（睡前还有没浇的作物）`
  10. `[summer 16] day_end verified=false`
  11. `[summer 18] ended_by=slept_without_work（不是我们主动睡过去的）`
  12. `[summer 18] day_end verified=false`
  13. `journal 里出现 跨日没有推进 ×1`
- `--json`（`logs/run9b-verify.json`）：**`verdict = needs_review`**、**`strict_verdict = needs_review`**、`strict_problem_count = 13`、`problems = 13`、`history_problems = 0`。
  - 说明：`strict_verdict` 只在**与 `verdict` 不同**时打印"严格口径"行（`tools/verify-run3.py:1232-1235`），本跑两者相同 ⇒ 文本版没有该行；其算法是 `needs_review if (problems or history_problems) else VERIFIED`（`:1168-1171`）。**`history_problems=0`** 与尾部窗口口径一致：本跑尾部没有连续 VERIFIED 段，工具**拒绝把任何问题降级为历史**（"历史问题不能替本跑开脱"）。
- 信息段要点（不影响结论）：summer 15/16 均为**诚实收尾 `gave_up_dry`**（`gave_up_tiles=3`）；每日 `unreachable`/`tool_refused` 的「账本 vs 自算」逐日一致（summer 14 `tool_ineffective` 3 格、summer 15 4 格，均在豁免上界内）；`encircled` 全 0；`plant_area`/`till_area`/`water_area` 多轮 leftover **按最后一轮计**（遮蔽已显式列出）。

### 4.2 `tools/analyze-longrun.py --journal logs\longrun-3day-llm-run9b.jsonl --window 3`

- `退出码: 1`；**`VERIFIED: 1/3 天`**；`有红 45 条`（`missed:cancel:clear_area/plant_area/till_area/water_area`、`missed:check:day_justified/no_unmet_stages/slept_by_us/watered_outdoor`、`missed:plot_exhausted`、`missed:seeds`、`missed:stage_exhausted`、`missed:stage_no_target`）。
- **`窗口: --window 3（尾部连续 VERIFIED 0 天，不足 ⇒ 不启用窗口降级（窗口外也照常 fatal））；窗口内红 45 条；窗口外历史问题 0 条；已结清（当天 VERIFIED）1 条（行 [340]）`**。
- `环境挡路: 0 条（0 格）`；`自旋到上限 0 次`；`没拿到结论: 0 条`（配额被吃掉 0 格）。
- 判决权威仍是 `tools\verify-run3.py`；两侧**同向 FAIL**（`needs_review` vs `exit 1`）。

### 4.3 `scratch/run9-lead-check.py --journal … --smapi logs\run9b-smapi-window.txt --snapshots scratch\run9b-external-snapshots.jsonl --days 3`

- `rc = 1`，原文要点（全文 `logs/run9b-lead-check.txt`）：
  - `[1] 跨日链`：`summer 13→14→15→16→17→18` 前 5 次 **`+1 ✅`**，summer 18 `day_after=None（slept_without_work）⇒ 当天没跨日，不计入`；`合计 跨日 5 次，其中恰好 +1 的 5/5`。
  - `[2] 存档链`：start `3706657 / 2026-10-15T22:22:57.011 mod_version_matches=True`；end `5766683 / 2026-10-16T22:30:13.053 mod_version_matches=True`。
  - `[3] SMAPI 配对`：`NewDay 5 / before save 5 / Save called 6 / completed 5`；`NewDay 行号 [1008, 2167, 2881, 3511, 4598]`、`before-save 行号 [1020, 2169, 2884, 3513, 4610]`。
  - `[4] 自述 vs 自算`：6 天 `ok_steps ↔ Σ stages[].ok`（与 `failed` 同理）**6/6 全部 ✅**。
  - `[5] 尾部窗口`：`summer 16 verified=False 未通过项=['watered_outdoor','day_justified']`、**`summer 17 verified=True 未通过项=[]`**、`summer 18 verified=False 未通过项=['slept_by_us','day_justified']` ⇒ **未达标 ❌**。
  - `[6] finish: code=1 streak=0 actions=432 minutes=30.35 no_unmet_stages=False`。
  - 两条 ❌（`before save(5) != Save called(6)`、`有 save(6) 无 NewDay(5)`）**是 §3 已定性的 L16 假阳性**，不是真实异常。

---

## §5 六问逐条读数

### ① 出货日日切保存：五串是否齐全、存档是否前进

**齐全且前进** —— 见 §3：5 次跨日 × 6 串逐次配对，存档 `3706657 → 3731582 → 3770274 → 3813991 → 3843606 → 5766683`，`_old` 每次正常轮换。**run9 的 `4 NewDay / 0 save` 形态在 0.7.29 上不再出现。**

### ② 经济闭环四腿

| 腿 | 读数 |
|---|---|
| 卖（腾格） | `sell` **3** 条 + `surplus_sell` **3** 条（全部 `why=need_slot`）：`(O)771 Fiber stack 1`（t=0.31）、`(O)390 Stone stack 163`（t=85.47）、`(O)388 Wood stack 100`（t=1761.49）；`keep=10`、整叠卖出时如实记 `below_keep=true`；`trigger.freeSlots=0 / freeSlotsStatus=ok` |
| 次日到账 | summer 15 `day_start money=235`（前一夜出货由游戏自己结算；成交当天 `money` 不变是设计） |
| 买 | `buy` **8** 条：1 条探路失败（`item_not_sold`：商店没有 `472`，回执带在售清单 Melon/Tomato/Blueberry/Pepper/**Wheat 10g**/Radish/Poppy/Spangle）× 7 条成交（全是当季 `(O)483 Wheat Seeds` 10g：`188→88`、`88→8`、`335→235`、`235→135`、`135→35`、`35→5` 等） |
| 播种 | `plant_area` 多天有 ok（summer 13 起即落格；summer 17 阶段聚合含 `plant_area` 且 `Σ ok=70`） |

⇒ **四腿都真机走通**；`cannot_afford` / `seed_unavailable_today` 各 0 条（本跑没有"买不起"的场景）。

### ③ 死苗是否真空通过

- 逐日 `day_end`：`dead_crops=0`、`dry_dead=0` **6/6 天**；`logs/longrun-3day-llm-run9b-lessons.json` 里 `far_dry_given_up|water_far` 的 `evidence="gave_up=3 dry_dead=0"`。
- ⇒ 本跑**没有可证伪的死苗样本**（既非"通过"也非"失败"）：判定为【无法判定】——**缺失 ≠ 通过**。

### ④ `review_only_fallback` / `plot_exhausted_burst` 是否生效、有界

- `review_only_fallback` **2 条**、`source="pending_walk"`、`walked=true`（`#127 t=496.81 tiles=12 attempt=1`、`#179 t=702.56 tiles=9 attempt=3`），note 原文"只有 review 却说还有活 ⇒ 回到跨片地 leftover 旁边再看一次" ⇒ **兜底生效**。
- `plot_exhausted_burst` **1 条**（`#95 t=293.72 count=5 zone=""`，note："同一秒内连发换片（run9 形态：0.6 秒 12 次）⇒ 不再把整天耗在无目的换片上，按既有有界机制收尾"）⇒ **连发被收口**。
- `review_only_no_target` 0 条（兜底都拿到了目标）；`plot_exhausted` 11 次跨 6 天（单日 ≤5）。

### ⑤ `farm_evidence_unavailable` 是否伴随假 VERIFIED

- 账本 357 行里**关键字 `farm_evidence` 命中 0 条**；唯一 VERIFIED 的 summer 17 其 `checks` 九项全真、`final_water` 有真值（`farm/Farm dry 0/56 tiles=199`）⇒ **不存在"证据不可用却自证 VERIFIED"的形态**。

### ⑥ `buy_partial` / `no_space` 读数（task-123 是否真机生效）

- **`buy_partial` 2 条**，原文 note："钱只够买 8 个（想买 10 个，单价 10g）⇒ 量力而行，这不是失败；缺的种子明天钱结算后再补"（t=85.56）、"钱只够买 3 个"（t=1761.58）⇒ **真机生效**。
- **`no_space` / `no_inventory_space` 命中 0 条**（对照 run8：25 次 + 13 次重试）⇒ 腾格策略生效，**run8 的空格死锁本跑未复现**。

---

## §6 收尾现场与优雅退出

### 6.1 收尾现场（唯一一次收尾只读观测 `observe?detail=full`，`2026-10-16T22:33:16`）

落盘原文：`scratch/run9b-live-observe.json`（7367 B）。

| 字段 | 值 |
|---|---|
| `clock` | `{year:1, season:"summer", day:18, timeOfDay:1000, weather:"rain", weatherOnFarm:"rain"}` |
| `ui` | `activeMenu=null`、`isModal=false`、`eventUp=false`、`dialogueIsQuestion=false`、`onScreenMenus=4`、`professionsToChoose=null` |
| `game` / `liveness` | `{paused:false, shouldTimePass:true}` / `{worldAdvancing:true, secondsSinceClockMoved:4.77}` |
| `player` | `Jay @ FarmHouse [9,9]`、`stamina 270/270`、`money 105`、`isInBed=true`（**已知残留**）、`canMove=true`、`farmingLevel 0`、`wateringCan.waterLeft=8` |
| `inventory` | 12 格：Axe/Hoe/Watering Can/Pickaxe/Scythe(47)/Geode `(O)535`×2 … |
| `farm` | `crops=55`、`ripe=0`、`dryCrops=0`、`deadCrops=0`、`dryDeadCrops=0`、`unwateredCrops=34`、`hoeDirt=186`、`complete=true`、`scanSeq=3354` |
| `health` | `modVersion=0.7.29`、`runtime={ticks:125316, uptimeSeconds:2108.2, worldSeq:3354, hasSaveLoaded:true}` |

### 6.2 优雅退出（用户 m02833 政策）

- `python tools\stop-game.py` ⇒ `rc=0`：`回执：ok — 已置 Game1.quit=true…`、`✅ 游戏已退出（原 pids=[456]）`。
- 退出后四条复核：**进程 0 个**；**`bridge.json` 已删除**；**17890 无 LISTENING**（只剩 2 条 `TIME_WAIT`）；**存档四条退出前后逐字未变**（5766683/`22:30:13.053`、26933/`22:30:13.055`、3843606/`22:22:45.355`、26891/`22:22:45.356`）。
- SMAPI 尾部（自己走的退出路径，非崩溃）：`22:34:37 Disconnected: ClosedGame` → `Disposing...` → `已删除发现文件 …\bridge.json` → `Disposing the content coordinator`；窗口内 `ERROR/Disconnected/ClosedGame/soft_oal` 全 0。

---

## §7 诚实缺口清单与盲区

1. **没有拿到尾部连续 3 天 VERIFIED** —— 尾部窗口是 `summer 16（未过）/ 17（过）/ 18（未过）`；`finish.code=1`、`stuck_flushes=0`、`unmet_days=[summer 13, 14, 15]`。判 FAIL 是工具口径的直接结论，不是解释。
2. **`run10-lessons.json` 的这次拷贝只作占位、不得用于判决** —— 本轮 22:30 把 `logs/longrun-3day-llm-run9b-lessons.json` 原样拷成了 `logs/longrun-3day-llm-run10-lessons.json`（两侧 SHA256 同为 `C2312F2D7FA3C9AAC3DBE3273E7DC9EBD220555AF5368A2F0AC8F342338486A0`），但 run9b 那本库里 `far_dry_given_up|water_far` 的 `hint` 与自身 `evidence`（`gave_up=3 dry_dead=0`）**自相矛盾**（Lead 已立 task-136）。run10 的注入基线必须以 **run9c（0.7.30 上的 run A）** 的 `logs\longrun-3day-llm-run9c-lessons.json` 重新原样拷贝为准，并在 `docs/_run10-evidence.md` 记"拷贝时刻 + 两侧 SHA256"。
3. **存档只保留两代** ⇒ 窗口内中间几次落盘的 size 物理上不可恢复（每一次都由 SMAPI 六串 + `_old` 轮换佐证）。
4. **收尾现场的 `money=105` 与 summer 18 `day_end.final.money=205` 不一致（-100g），成因未定** —— 期间（`22:30:17`–`22:33:16`）SMAPI **没有任何 `/v1/exec`**（只有我 `22:33:16` 的 health+observe），因此**不是脑侧动作造成的**；列为盲区，不做推测性解释。同理 `farm.crops` 在 17 日 `final=50` 与收尾现场 `55` 的差异（不同 `tod`/窗口口径）只作读数并列。
5. **`isInBed=true` 残留**：收尾现场玩家在 FarmHouse 走动（`canMove=true`）仍报 `isInBed=true`，与 run2 起记录的同一现象一致（`FarmWorker.sleep` 的"上床"判断会因此跳过，属已知风险，不影响本跑结论）。
6. **`farm.unwateredCrops` 不是干格数**：收尾现场 `unwateredCrops=34` 而 `dryCrops=0`；浇水判据一律用 `dryCrops`/`final_water.dry`（`farm.unwateredCrops` 不参与判定）。
7. **`plot` 观测被 400 格上限截断**（`tilesTruncated=true`）：田区统计与锚点打分只覆盖已返回的格，跨片地 leftover 的一部分成因可能在这个盲区里。
8. **`eventUp` / 剧情事件本跑 0 次**；`modal_dismissed` 2 次（普通框，均成功）。若有 `eventUp`，按 task-41 纪律一律停手等人工，本条不适用（无样本）。
9. **本跑没有可证伪的死苗样本**（`dead_crops=0`/`dry_dead=0` 6/6 天）⇒ 六问③ 判【无法判定】。
10. **`save_called` 计数 6 vs 5 的工具坑**（§3）：插件描述行会被正则命中，两套独立工具（Lead 复核器）都踩了 ⇒ 后续自动化必须先过滤该行。

---

## §8 保留物清单

| 文件 | 说明 |
|---|---|
| `logs/longrun-3day-llm-run9b.jsonl` | 账本 357 行（`finish` 在末行） |
| `logs/longrun-3day-llm-run9b.version.json` | 版本四要素 sidecar（HEAD / 五文件 SHA256+mtime / PID / argv / worktree） |
| `logs/longrun-3day-llm-run9b.pid` | PID 12028 |
| `logs/longrun-3day-llm-run9b.console.log` / `.console.err.log` | console 21251 B / 192 行；stderr **0 B** |
| `logs/longrun-3day-llm-run9b-llm.jsonl` | LLM 调用留痕（decision 44 / LLM 31） |
| `logs/longrun-3day-llm-run9b-lessons.json` | 教训库 7 条（L0 达标） |
| `logs/longrun-3day-llm-run10-lessons.json` | **占位拷贝**（不得用于判决，见 §7.2） |
| `logs/run9b-smapi-window.txt` | 冻结窗口 340380 B / 4622 行 / SHA256 `BE554988…94E0` |
| `logs/run9b-smapi-chain.txt` | 六串逐条行号表 |
| `logs/run9b-verify.txt` / `logs/run9b-verify.json` | `verify-run3` 文本版 + JSON（verdict/strict_verdict） |
| `logs/run9b-analyze.txt` | `analyze-longrun` 全文（30771 字符） |
| `logs/run9b-lead-check.txt` | Lead 独立复核器全文 |
| `logs/run9b-six.txt` / `logs/run9b-brief.txt` | 六问取证（65160 B）与精简摘要 |
| `scratch/run9b-external-snapshots.jsonl` | 起止快照原文两行 |
| `scratch/run9b-live-observe.json` | 收尾现场 full 观测 |
| `scratch/run9b-snapshot.py` / `run9b-tools.py` / `run9b-six.py` / `run9b-brief.py` / `run9b-live-observe.py` | 本跑取证脚本 |
| `logs/run9b-baseline.json` | Lead 的起跑前基线 |

**纪律声明**：本跑与本文档只写 `logs/`（新增）、`scratch/`、`docs/_run9b-evidence.md`；**未改动** `brain/`、`mod/`、`tests/`、`tools/`，未 bump/未装机，未在跑批中 `load_save`，未替游戏做选择（本跑无 `eventUp`）。
