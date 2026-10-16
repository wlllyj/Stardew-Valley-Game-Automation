# task-157 / task-158 独立对抗验收（deputy-lead）

判定：**PASS-WITH-NITS**（无必修项；0.7.32 可放行，两条 NIT 建议 0.7.33 收）

- 对象：`ef59f30`（task-157，water_far 遇 unreachable 先有界开路再试）+ `cf7432a`（task-158，体力预算闸门）+ `63ef273`（task-158 补钉，常量集中）
- 方法：只读生产代码；`scratch/_t159_probe.py`（35 项检查：B 段形态复现 + C 段对抗 + 工具侧伪账本）在三棵树上跑（pre-157 `fab1f58` / pre-158 / 新树 HEAD），外加三工具对 `logs/longrun-3day-llm-run9d.jsonl` 的并排离线重放。
- 原始读数：`scratch/_t159_post_out.txt`（新树 **35/35 PASS**）、`scratch/_t159_pre157_out.txt`（**22/31**）、`scratch/_t159_pre158_out.txt`（**26/31**）、`scratch/_t159_v_run9d.txt`、`scratch/_t159_a_run9d.txt`、`scratch/_t159_l_run9d.txt`。

## §1 A 段：范围与读数（我亲跑）

| 项 | 读数 |
| --- | --- |
| HEAD（开验时） | `48dac79`（docs: task-155 设计稿），工作树干净 |
| `git show --numstat ef59f30` | `brain/agentfarm/longrun.py` +123/−12、`tests/test_longrun.py` +228/−2（合计 351 ins / 14 del，与卡面逐字一致） |
| `git show --numstat cf7432a` | `brain/agentfarm/farmwork.py` +16、`longrun.py` +156/−4、`tests/test_longrun.py` +121 |
| `git show --numstat 63ef273` | `farmwork.py` +3、`tests/test_longrun.py` +74 |
| 越界扫描（三提交 `--name-only`） | `^mod/`、`^tools/`、`manifest.json`、`bridge.py`、`^logs/`、`docs/00-开发日志.md` **0 命中** |
| SHA256 前 16 | `longrun.py 587CDF372D582343`(366105 B)、`farmwork.py F7B844FC52E2AB8E`(154339 B)、`test_longrun.py 817C5F82A02D31F7`(440044 B)、`test_farmwork.py CC7AB7CB3ED4751D`、`tools/verify-run3.py B577F980C152D8A2`(未变) |
| `py_compile -W error::SyntaxWarning` | longrun/farmwork/planner/bridge **rc=0** |
| 定向 | `tests.test_farmwork tests.test_longrun tests.test_planner` **Ran 473 / OK** |
| 全量 | `Ran 832 / FAILED (failures=2)` = `TestBagSpaceDeadlock.test_mechanical_enumeration_has_no_unmapped_event` + `TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name` |

- 两条红**归属 task-160**（analyzer 桶未跟新事件，Lead 已派单）⇒ 不是本批回归，也不影响本批判定。
- 卡面与 `docs/_release-0.7.32.md` 均**未给代码 SHA256**（只有 SMAPI 窗口 SHA `E1340346…DC0E`）⇒ 我记录自己的读数，并核对"工作树内容 == 提交内容"（`git show …:file` 与工作树一致）。

## §2 B 段：三形态 FAIL→PASS（旧树 vs 新树）

### B① summer 25 形态（`[12,30]` 够不着）：pre-157 FAIL → post PASS

同一世界（窗口外 1 格干苗 + 够不着）：`scratch/_t159_probe.py` B1 家族。

| 检查 | pre-157（`fab1f58`） | 新树 |
| --- | --- | --- |
| 有界开路留痕 | FAIL：`opens=0 blocked=0`（一次都没试） | PASS：`opens=2`（= `FAR_DRY_OPEN_MAX`）、`water_far_open` 有 journal |
| 仍走不到 ⇒ `water_far_blocked` | FAIL：`blocked=[]`（事件不存在） | PASS：`blocked[0]={tile:[61,10],cause:"unreachable",attempts:1,limit:2,opens:1,cleared_tiles:[[61,11]],cleared_count:1}` |
| 开路 ≠ 浇水 | （无开路，无从谈起） | PASS：`watered_tiles=[]`、`watered_outdoor=False`、理由 `gave_up_dry:…其中 1 格已放弃当天…` |
| 当天不 VERIFIED | PASS（旧树也诚实，但reason 归因含糊） | PASS：`verified=False`，`cause` 显式分离 |
| 可救形态（开路后能站到） | FAIL：`opens=0 watered_tiles=[]`（本该能浇上却放弃） | PASS：`opens=1`、`watered_tiles=[(61,10)]`、`watered_outdoor=True`、当天可 VERIFIED |
| 回执撒谎（`lie`） | — | PASS：`wf_ok=[False,False]`、`cause=['not_watered','not_watered']`、`watered_tiles=[]` |

⇒ **task-157 的核心承诺（有界开路、开路≠浇水、blocked 如实、cause 可分离）全部有 FAIL→PASS 原文。**

### B② summer 27/28/fall 1 形态（dry 17→79→140、体力见底）：pre-158 FAIL → post PASS

同世界（农场 `crops=146 dry=17`、窗口 5 格干苗 + 20 格空地、体力 60/上限 270）：

| 检查 | pre-158 | 新树 |
| --- | --- | --- |
| 预算快照 | FAIL：`_stamina_budget` 不存在 ⇒ `stamina_budget=None` | PASS：`reserve=304.0`、`dry=17`、`capacity=0`、`basis="farm"` |
| 预算留痕 | FAIL：`defer=[]` | PASS：`deferred_by_budget` 点名 `clear_area`（只 clear/till/plant，`harvest`/`clear_dead`/`water_area` 从不在列 ⇒ C5a PASS） |
| 有干苗 ⇒ 零播种 | pre 也 `planted=20`（旧树另有"干苗不许播种"规则） | PASS：`capacity=0` + `plant_area` 目标 0 + `planted=20`（**不新增行为，属加固**，见 §4 INFO-1） |
| 没浇完不达标 | `watered_outdoor=False` | `crops_watered=True`（窗口已浇完）但 `watered_outdoor=False`、`verified=False` |
| 体力中途耗尽（B2f） | `assigned_undone=5`、`crops_watered=False` | 同（新树也 PASS）⇒ 未浇完如实留账，不是新特性但**未被 task-158 破坏** |
| 有界性 | `ended_by=stuck`（3 轮无变化） | `ended_by=sleep`（`stuck:同一秒连发 5 次换片都没有目标…`，`plot_exhausted_burst` ≤1） |

⇒ **task-158 的 reserve/capacity 语义在新树成立，且不产生假绿。**

### B③ 正对照：改前改后逐字相同

- B3（预算充足、无干作物的普通一天）：`_t159_b3_post.json` 与 `_t159_b3_pre158.json`（以及 `_t159_b3_pre157.json`）SHA256 **完全相同**（`418248EE613E7851…`，636 B）。
- `checks` 键集：new == pre-158，**10 项完全一致**（`crops_watered / day_justified / no_blocking_modal / no_hard_failures / no_unmet_stages / refused_within_bound / slept_by_us / unreachable_within_bound / watered_outdoor / zero_action_evidenced`）⇒ 两卡都**没往 `checks` 塞可洗白键**。

### B④ run9d 离线重放（三工具并排，`logs/longrun-3day-llm-run9d.jsonl`）

| 工具 | rc | 关键读数 |
| --- | --- | --- |
| `tools/verify-run3.py --days 5` | 1 | `needs_review`；尾部 0/5；问题含 summer 25 `gave_up_dry`（info）+ 25/26/27/28/fall 1/2/3 `verified=false`、27/28/fall 1/2 睡前未浇 14/50/64/61、`crops_watered=false` |
| `tools/analyze-longrun.py --days 5 --window 5` | 1 | 窗口 0 天 VERIFIED ⇒ **不启用窗口降级**；窗口内红 29 / 窗口外历史 0 / 已结清 6；必须人工介入 0；`water_far 75 次（浇成 71 / 没成 4；unreachable×4）` |
| `scratch/run9-lead-check.py --smapi logs/run9d-smapi-window.txt` | 1 | 未达标 ❌；SMAPI 8/8/8/8（排除 1 行插件描述行，task-127 规则）；自述 vs 自算 9/9 ✅；`finish code=1 streak=0 actions=827 minutes=38.26` |

⚠️ `run9d` 是 **task-157/158 之前的构建**产出的账本：75 条 `water_far` 里 **71 条没有 `cause` 字段**（无 `water_far_open`/`water_far_blocked` 事件）⇒ 按卡面口径，**cause 与开路面只能记【无法判定】**，形态①②的验证由上面的假世界复现承担；期望 run A/B（0.7.32）账本自带这些字段。

## §3 C 段：对抗矩阵（≥6 组，全部走真代码）

| 组 | 攻击 | 结果 |
| --- | --- | --- |
| C1 | 伪造 `farm.dryCrops=0`，掩盖"还有干苗" | PASS：`verified=False`、`watered_outdoor=True` 但 `ok=0`（窗口仍有 5 格干苗）⇒ 不许变绿 |
| C2 | `farm` 计数不可用 / 畸形（`crops="many"`、`dryCrops=-3`） | PASS：`basis="conservative"`、`reserve=stamina`（60）、不播种、clear/till 停手留痕、不崩 |
| C3 | `cleared_tiles>0` 但该格 `watered=false`，把开路当浇水 | PASS：`wf_ok=[False,False]`、`cause=not_watered`、`watered_tiles=[]` |
| C4 | 开路/重试有界性（不许死循环） | PASS：`opens=2`（=上限）、`water_far` 尝试 2（=上限）、全天 `steps=1` |
| C5 | 与 task-102/149 打架（0 动作不许睡 / 只在预算上不越权） | PASS：`harvest/clear_dead/water_area` 永不被延后；0 动作 + 有活 ⇒ 不以 `no_work` 收尾 |
| C6 | `checks` 键集不许新增可洗白项 | PASS：与 pre-158 逐字相同的 10 键，无 `budget`/`deferred_by_budget`/`stamina_budget` |
| T1 | blocked + `gave_up_dry` 的一天伪造成 VERIFIED（连 `finish.code=0` 一起改） | PASS：`tools/verify-run3.py` CLI **rc=1 / needs_review**（`final_water.dry>0` 与 `watered_outdoor=true` 互斥被抓） |
| T2 | 抹掉 `watered_outdoor`/`final_water`（缺失当通过） | PASS：rc=1，缺失 ⇒ 问题/【无法判定】，绝不当通过 |

> 注：T 段必须走工具 CLI；进程内 `load/build_days/report` 的语义不同（会给真账本也返回 `problems=[]`），这本身是**我探针的用法坑**，已记录在脚本注释里。

## §4 NIT / INFO（都不阻塞放行）

- **NIT-1（结构性，建议 0.7.33）**：`_leftover("plant_area")`（`brain/agentfarm/longrun.py:2587-2592`）**不按 `capacity` 收窄** ⇒ "有种子 + 有空地 + 预算受限"的日子 leftover 恒 >0 ⇒ `no_unmet_stages=False` ⇒ **该日无法 VERIFIED**（新树 B2 实测：day 以 `stuck:同一秒连发 5 次换片都没有目标…` 收尾，`plot_pending` 仍 >0）。是"有界不假绿"，不是洗白通道；但连续高负载天会白烧日。建议把"因预算延后的格"并入 task-134 的诚实上限口径（记 `deferred_tiles`）而不是留在 leftover。
- **NIT-2**：`capacity` 上限在 `_stage_tiles`（`:2536-2541`）里**静默** `min(limit, capacity)` ⇒ 账本里分不出"被容量卡住"与"没有目标"（`deferred_by_budget` 只记 `_budget_defer_reason` 的三个任务）。建议加一条 journal。
- **INFO-1**：pre-158 也已"有干苗不播种"（旧规则）⇒ B2b 的零播种**不是 task-158 的新行为**，新的是 `capacity=0`/`deferred_by_budget`/`stamina_budget` 可核。
- **INFO-2**：run9d 账本是旧构建 ⇒ `cause`/`water_far_open`/`water_far_blocked` 一律【无法判定】；run A/B 才带新字段。
- **INFO-3**：三工具在 run9d 上同向（都判红/未达标），无"两工具相反"情形。

## §5 结论

- **task-157**：PASS（有界开路、开路≠浇水、blocked 留痕、cause 分离、可救形态真浇上；旧树 4 项 FAIL 全部修掉）。
- **task-158**：PASS-WITH-NITS（reserve/capacity 语义成立、无新 `checks` 键、harvest/clear_dead 不延后、保守失败安全；NIT-1/NIT-2 为口径完整性问题）。
- **0.7.32 可否放行**：**可以放行**（本卡无 FAIL 项；全量 2 红是 task-160 的 analyzer 缺桶，与本批无关）。NIT-1 建议随 0.7.33 收，因为它直接影响"高负载日能否达标"的观测量。

## §6 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"
# 新树
$env:T159_ROOT = "D:\Deepseek Harness Workspace\星露谷游戏自动化"; $env:T159_TAG = "post"
& $py -W error::SyntaxWarning scratch\_t159_probe.py
# 旧树（pre-157 = fab1f58 / pre-158 = scratch\_t159_pre）
$env:T159_ROOT = "...\scratch\_t159_pre157"; $env:T159_TAG = "pre157"
& $py -W error::SyntaxWarning scratch\_t159_probe.py
# 工具侧（run9d）
& $py tools\verify-run3.py --journal logs\longrun-3day-llm-run9d.jsonl --days 5
& $py tools\analyze-longrun.py --journal logs\longrun-3day-llm-run9d.jsonl --days 5 --window 5
& $py scratch\run9-lead-check.py --journal logs\longrun-3day-llm-run9d.jsonl --smapi logs\run9d-smapi-window.txt
```

## §7 越界

只写了 `docs/` 与 `scratch/`：`scratch/_t159_probe.py`、`scratch/_t159_dbg.py`、`scratch/_t159_pre_out.txt`、`scratch/_t159_pre157_out.txt`、`scratch/_t159_pre158_out.txt`、`scratch/_t159_post_out.txt`、`scratch/_t159_v_run9d.txt`、`scratch/_t159_a_run9d.txt`、`scratch/_t159_l_run9d.txt`、`scratch/_t159_b3_*.json`、`scratch/_t159_keys_*.json`、`scratch/_t159_j/`，以及两棵快照树 `scratch/_t159_pre`（pre-158）与 `scratch/_t159_pre157`。未改 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs/00-开发日志.md`。
