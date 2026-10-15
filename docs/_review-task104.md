# task-108：独立对抗验收 task-104（`_water_far_dry` 人不在农场时不扣额度）

**判定：PASS-WITH-NITS（无必修项，建议 0.7.28 放行；三条 NIT 归 0.7.29）**

- 验收对象：dev-coder 的 task-104 = `9b5b592`（`0.7.28 task-104: 人不在农场时不去浇窗口外干作物…`）
- 验收人：deputy-lead（只读生产代码；不改 `brain/`、`mod/`、`tools/verify-run3.py`、`docs/00-开发日志.md`）
- 复现脚本：`scratch/_t108_adv.py`（真 `FarmWorker` + 真 `LongRun`，journal 写盘后喂**进程内** `tools/verify-run3.py`）
- 原始读数：`scratch/_t108_all_out.txt`（全量 57/58 PASS，唯一 FAIL = §5 NIT-2 的发现）、`scratch/_t108_j/t108_*.jsonl`（真账本）、`scratch/_t108_c7_{pre,post}.json`

## 1. 一句话结论

task-104 的四条承诺（**先尝试回农场 → 回不去就不扣额度/不认输 → 收尾点名 `not_on_farm` → 人在农场时行为不变**）
在真代码端到端上全部成立，且我在 8 组对抗里**没有找到任何"白拿达标"**：所有 fail-closed 情形工具判决都是
`needs_review`，`verified=false`。三条 NIT 都是诚实性/健壮性层面的（不阻塞），其中 NIT-2 是**老洞**（早于 task-104）。

## 2. 范围与读数（A 段，亲跑）

| 项 | 读数 |
| --- | --- |
| HEAD / 对象 | `7e2ad95`；`git show --stat 9b5b592` = **恰 2 文件** +246/−2（`brain/agentfarm/longrun.py` +66/−2、`tests/test_longrun.py` +182） |
| 越界扫描 | `^mod/\|^tools/\|manifest\.json\|bridge\.py\|^logs/\|00-开发日志` ⇒ **0 命中** |
| 工作树 | ` M docs/_release-0.7.28.md`（Lead 的）、未跟踪 `scratch/_t103_introspect*.py` ×4、`tools/_note-0728.txt`（都不是 task-104） |
| SHA256 前 16 | `longrun.py 3DA5B6839F2A5DC8`、`test_longrun.py 8A8B809F36658C50` ⇒ **与作者自报逐字一致**；对照未变：`tools/verify-run3.py 7356D4CBA1D0A1EE`、`brain/agentfarm/farmwork.py 3D2A9E5AD4B84A7A` |
| py_compile | `-W error::SyntaxWarning` exit 0 |
| 单测 | `tests.test_longrun` 单模块 **Ran 171 / OK**；`tests.test_farmwork tests.test_longrun` **Ran 281 / OK**（= 作者自报）；全量 `discover -s tests` **Ran 618 / OK**（作者当时 611，差 7 = task-106 的新用例，`6293696` 已提交） |
| 工具判决（真 journal） | B1 / C1a / C1b / C2 / C3 / C4 ⇒ `needs_review`；B2 / C7 ⇒ `VERIFIED`（§4） |

## 3. 逐条对卡

| 卡面 | 结果 | 证据 |
| --- | --- | --- |
| A1 范围只许两文件 | ✅ | `git show --stat 9b5b592`；越界 0 命中 |
| A2 读数亲跑 + 核对作者数字 | ✅ | §2；hash 逐字一致；全量 618（作者 611 差 task-106） |
| B3 复现 run8 day12：室内 + 窗外干作物 ⇒ 先试回农场；不 `try++`、不进 `given_up`；给正例 | ✅ | **B1**：恰 1 次 `goto_farm{where:"water_far"}`、恰 1 条 `water_far_skipped{reason:"not_on_farm", count:1, tiles:[[61,10]]}`、`far_dry_tries=={}`、`far_dry_given_up==set()`、无 `water_far`；**B2/C5**：回得去时当天真浇上（`water_far ok=True, dry_before=1→dry_after=0`） |
| B4 收尾点名 `not_on_farm` | ✅（附口径修正） | B1 理由原文 `…；not_on_farm：人在室内，窗口外干作物这轮没去浇（不扣该格当日额度、不进 given_up）`；`verified=false`、`day_justified=false`、工具 `needs_review`。**口径修正见 INFO-1** |
| C5 伪造成"人在农场"+ 坐标不可达 ⇒ 会不会被骗扣额度 | ✅（有洞但**不白过**） | **C1a/C1b**：额度确实照扣（`far_dry_tries[FAR]=2`、2 次 `water_far ok=False code=unreachable`）、两次不成进 `given_up`、**没有** `not_on_farm` 留痕；但 `verified=false`、`day_justified=false`、`ended_by=slept_without_work`（理由含 `gave_up_dry:…坐标都够不着…这不是「没活可做」`）、工具 `needs_review` ⇒ **NIT-1** |
| C6 回不去是否**有界** | ✅ | **C2**（4 天上限跑出 3 天）/ **C4**（3 天封顶）：每天恰 1 次 `goto_farm{water_far}`、`goto_farm` 总数 ≤2/天、`stuck_flush ×2 + stuck_flush_skipped ×1`（`MAX_STUCK_FLUSH=2`）、`no_day_progress ×1` |
| C7 `water_far_skipped` 会不会被当"已认输" | ✅ | **C3**：3 天 3 条 skip **全部** `reason=not_on_farm`；每天 `gave_up_tiles` 均为空；`FAR` 从未进 `far_dry_given_up`；次日仍重试同一格 |
| C8 人在农场时一字不变 | ✅ | **C7** pre/post 对照：同世界在两棵树跑出的产物**除 `has_flag` 外逐字相同**（`water_far`/`goto_farm`/`water_far_skipped`/`day_end.checks`/`ended_by`/`ok_steps`/`watered_tiles`）；pre 树 = `9b5b592^` |
| C9（加分）与 `goto_farm{day_start_retry}`+`slept_without_work` 组合的死循环 | ✅ 无死循环 | **C4**：不变量 `day_after ∧ ok_steps==0 ∧ verified` 三者绝不同时；直接调 `_do_sleep`（0 动作 + 有活）⇒ `slept_without_work`、游戏日 `8→8` 不变、理由后缀仍点名 `not_on_farm`；端到端由 `_stuck_flush` 有界翻篇收尾（≤3 天） |
| D NIT 表 + 判定 | ✅ | §5 / 本页抬头 |

## 4. 对抗矩阵（真代码；`scratch/_t108_all_out.txt`）

| 用例 | 场景 | 关键读数 | 工具（真账本） |
| --- | --- | --- | --- |
| B1 | 开工后翻室内 + 1 格窗外干作物（run8 day12 最小复现） | 额度 0 扣、无 given_up、1 skip、1 goto、收尾点名 not_on_farm | 21 行 → `needs_review`（`ended_by=stuck`、`watered_outdoor=false`、`verified=false`） |
| B2 | 同上，但清模态后回得去 | `water_far ok=True`、`dry 1→0`、`watered_outdoor=true` | 7 行 → **VERIFIED** |
| C1a | 真在农场但目标格四邻全站不住 | `tries=2`、进 given_up、无 not_on_farm、世界没被浇 | 8 行 → `needs_review`（`ended_by=slept_without_work`） |
| C1b | Mod 字段谎报 `isOutdoorFarm=true`（人在 FarmHouse） | 与 C1a 逐字相同 ⇒ 守卫被绕过 | 8 行 → `needs_review` |
| C2 | 连续多天回不去（窗内有活让天数推进） | 4 天上限只跑 3 天；每天 1 次 goto；跨天不认输 | 72 行 → `needs_review`（3 天全 stuck + `跳日没有推进 ×1`） |
| C3 | skip 与 given_up 是否混淆 | skip 全 `not_on_farm`；`gave_up_tiles` 每天空；次日重试 | 72 行 → `needs_review` |
| C4 | 0 农场动作 + 有活 + 回不去 | 不变量成立；`_stuck_flush` 有界（×2）；直调 `_do_sleep` ⇒ `slept_without_work` 且日不推进 | 60 行 → `needs_review` |
| C5 | 先室内置 flag → 回农场浇上 | 工作不受影响（照浇）；flag **日级粘性** ⇒ 理由失真 | 单测直调（无 run） |
| C6 | `ensure_location` 抛 `BridgeError`（观测失败） | **穿出 `run()`**（无 `finish`、无 day_end） | 无账本（异常） |
| C7 | 人在农场（pre/post 同世界） | 产物除 `has_flag` 外逐字相同 | 6 行 → **VERIFIED** |

## 5. NIT 表（都不阻塞 0.7.28）

| # | 现象 | 行号 | 反例命令 | 建议 |
| --- | --- | --- | --- | --- |
| NIT-1 | 守卫的信任锚是 Mod 字段 `isOutdoorFarm`：字段说谎/自相矛盾（人在 FarmHouse 却报 `true`）时，task-104 的保护被绕过 ⇒ 额度照扣、两次不成进 given_up、无 `not_on_farm` 留痕。**但绝不白过**（`verified=false` + 工具 `needs_review`），且该字段同时是全部 farm 口径策略的锚（`_farm_scope_work`/`work_reasons`/`sleep_guard`）⇒ 属既有信任边界 | `longrun.py:1020`（`_is_farm` 判据 `:762`） | `python scratch\_t108_adv.py c1` | 0.7.28 不改；在 `docs/_run6-criteria.md` 记一句"守卫以 Mod 的 `isOutdoorFarm` 为锚"；要修则在 `_water_evidence`/`_farm_scope_work` 一并做一致性校验（0.7.29） |
| NIT-2 | `_goto_farm_for_water` 里的 `worker.ensure_location` **没有 try/except**；`FarmWorker.ensure_location` 自己的 `snap()`（`farmwork.py:1522`/`:1567`）可抛 `BridgeError` ⇒ 异常从 `_water_far_dry`（`longrun.py:3397`，不在 try 内）→ `_run_day` → `run()`（`:3935` 无兜底）穿出整轮，**没有 finish、没有 day_end**（本该 graceful `ended_by="bridge_down"`）。**归因：老洞**——`_ensure_on_farm` 的同一写法在 `cc2988e`（2026-10-13）就有，我的探针在 pre 树同样复现 | `longrun.py:974`（新）/ `:776`、`:788`（老） | `python scratch\_t108_adv.py c6` | 0.7.29：两处 `ensure_location` 调用包 `try/except BridgeError ⇒ ended_by="bridge_down"`（或让 `FarmWorker.ensure_location` 把自身 snap 失败折成 StepResult） |
| NIT-3 | `water_far_not_on_farm` 是**日级粘性**标志，只在次日重置（`:3320`）清：当天先室内跳过、后来回农场真浇上，收尾理由仍会说"这轮没去浇"（文案失真）。判据不受影响（`checks.watered_outdoor` 说了算） | `longrun.py:1022`、后缀 `_not_on_farm_suffix` | `python scratch\_t108_adv.py c5` | 0.7.29：`_goto_farm_for_water` 成功返回时清 flag，或把后缀改成"本日曾因人在室内跳过一轮" |
| INFO-1 | 卡面 B4 的字面句"不许 day_key +1 而当天 0 农场动作"在 `_stuck_flush`（task-73，`MAX_STUCK_FLUSH=2`）下**确实会出现**（B1/C2/C4：`day_after=true` + `ok_steps=0`），但 `verified=false`。这与 Lead 记录的口径 N1「`day_after ∧ ok_steps==0 ∧ verified` 三者绝不同时」一致 ⇒ 按 N1 判，不按字面句判 | `longrun.py` `_stuck_flush`（`:2219-2276`，`require_work=False`） | `python scratch\_t108_adv.py b1 c4` | 口径写进 `docs/_run6-criteria.md`（Lead 已记 N1） |
| INFO-2 | 真在农场 + 目标格真够不着（四邻站不住）⇒ 照旧 2 次后 given_up、当天 `gave_up_dry` 诚实收尾。这是 task-50/63 的既有策略，不是 task-104 回归 | `longrun.py:1081-1082`、`:951-961` | `python scratch\_t108_adv.py c1` | 无需动作 |

## 6. 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"
# A 段
git show --stat 9b5b592 ; git status --short
& $py -m py_compile -W error::SyntaxWarning brain\agentfarm\longrun.py tests\test_longrun.py
$env:PYTHONPATH = "D:\Deepseek Harness Workspace\星露谷游戏自动化\brain"
& $py -m unittest tests.test_farmwork tests.test_longrun -v
& $py -m unittest discover -s tests -t .
# B/C 段（全量 57/58，唯一 FAIL 是 NIT-2 的发现）
& $py scratch\_t108_adv.py ; Get-Content scratch\_t108_all_out.txt
# C7 pre/post 对照
git archive "9b5b592^" -o scratch\_t108_pre.tar ; tar -xf scratch\_t108_pre.tar -C scratch\_t108_pre
& $py scratch\_t108_adv.py c7
$env:T92_ROOT = (Resolve-Path scratch\_t108_pre).Path ; $env:T108_TAG = "pre"
& $py scratch\_t108_adv.py c7 ; $env:T92_ROOT = "" ; $env:T108_TAG = ""
Compare-Object (Get-Content scratch\_t108_c7_post.json -Raw) (Get-Content scratch\_t108_c7_pre.json -Raw)
```

## 7. 结论与放行建议

1. task-104 的核心承诺**成立**：B1 复现出的 run8 day12 老病灶（6 格窗外干作物被室外坐标空转、全进 given_up）
   已被堵死 —— 回不去时**一格额度都不扣、一次都不认输**，收尾如实点名 `not_on_farm`，工具判 `needs_review`。
2. 8 组对抗（含"伪造 on-farm"、"跨天有界"、"skip/given_up 混淆"、"一字不变"、"死循环组合"）全部无白过：
   `day_after ∧ ok_steps==0 ∧ verified` 不变量成立，fail-closed 情形一律 `needs_review`。
3. 三条 NIT 不阻塞：NIT-1 是既有信任边界（且不白过）；**NIT-2 是老洞**（`cc2988e` 起就在 `_ensure_on_farm` 上，
   我的 pre 树探针复现），影响面是"回归途中一次观测失败 ⇒ 整轮 traceback 而非 graceful bridge_down"；
   NIT-3 只是文案。建议 NIT-2/NIT-3 一起进 0.7.29（若 Lead 想让 run9 更稳，NIT-2 的两行 try/except 可以随
   0.7.28 一起修，但**不是本卡放行条件**）。
4. **放行建议：可以开 0.7.28 冻结链**（`check-release --expect 0.7.28` → 装机 → `preflight --save-baseline
   logs/run9-baseline.json` → task-105 起 run9）。
