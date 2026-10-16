# task-149 独立对抗验收（task-150）

- 验收人：deputy-lead（task-150）
- 对象：`928d3d2` = `0.7.31 task-149: 雨日 0 动作 VERIFIED 的 fail-open 收口`（`brain/agentfarm/longrun.py`、`tests/test_longrun.py`）
- 探针：`scratch/_t150_probe.py`（`T150_ROOT` 切树）；pre 树 `scratch/_t150_pre149`（`git archive`，HEAD=`601dfaa`，`hoeDirt`/`emptyDirt` 命中 0 ⇒ 确为 task-149 之前）
- 原始读数：`scratch/_t150_pre_v4.txt`（5/11）、`scratch/_t150_post_v4.txt`（11/11）、`scratch/_t150_targeted*.txt`、`scratch/_t150_full.txt`

## §1 一句话判定

**PASS-WITH-NITS（无必修项）⇒ 0.7.31 可放行冻结。**
task-149 的 A/B/C 三项修法在 pre 树 11 项检查里 **6 项 FAIL（run9c 那条 fail-open 全复现）**、在 `928d3d2` 上 **11/11 PASS**；我用 `tools/verify-run3.py` 的**独立**在场证据闸门交叉核对（伪造账本抓得住、真账本同向），**未发现本卡引入的新洗白通道**。

## §2 A 段：范围与读数（我亲跑）

| 项 | 读数 |
| --- | --- |
| `git show --numstat 928d3d2` | `brain/agentfarm/longrun.py` **+105/−5**、`tests/test_longrun.py` **+211/−18**（=316 ins/23 del；`--stat` 图显示 110/229，图≠numstat） |
| 越界扫描 `^mod/\|^tools/\|manifest.json\|bridge.py\|^logs/\|00-开发日志` | **0 命中** |
| 工作树 vs 提交 | `928d3d2:brain/agentfarm/longrun.py` blob `12d514f13cb3` == 工作树；`928d3d2:tests/test_longrun.py` blob `a3a94c55afd2` == 工作树 ⇒ 我验的就是提交内容 |
| SHA256 前 16 / 大小 | `longrun.py 86BC4D5CFEF5F58D` 349111 B；`tests/test_longrun.py 2A37C56D118CAB74` 416756 B；`farmwork.py 4A39BC11ABCA3413` 153108 B（两卡未改）；`tools/verify-run3.py B577F980C152D8A2` 81993 B |
| `py_compile -W error::SyntaxWarning` | longrun/farmwork/planner/bridge ⇒ **rc=0** |
| 定向 | `tests.test_farmwork tests.test_longrun` **Ran 364 / OK**；加 `tests.test_planner` **Ran 456 / OK**（与作者/Lead 一致） |
| 全量 | `discover -s tests` **Ran 815 / OK（0 红）**（与 Lead 一致） |

工作树他人在制：` M tools/_note-0731.txt`（非我）、`?? scratch/_t146_d3.py`、`?? scratch/_t150_probe.py`（我的探针）。

## §3 B 段：pre → post 逐条 FAIL→PASS（原文）

| 检查 | pre 树（`_t150_pre149`）原文 | post 树（`928d3d2`）原文 |
| --- | --- | --- |
| **B1** 雨天室内 + farm 有耕地 + 有种子 + 日初被 `ShippingMenu` 挡 | `ended_by='sleep'`、理由 `no_work:确实找不到可做的活（地里的活干完了、也没法/没必要买种子）`、`ok_steps=0`、**`verified=True` `rc=0`**、`goto_farm=2 retry=0 ensure_calls=2` | `ended_by='slept_without_work'`、理由 `stuck:守卫说还有活（farm 口径还有 3 格耕地空着（手上有 2 粒种子）⇒ 该去种）但没有任何作业区拿得出目标`、**`verified=False` `rc=1`**、`goto_farm=3 retry=1 ensure_calls=3` |
| **C1** 旧 Mod 缺 `hoeDirt`/`emptyDirt` ⇒ 必须 fail-closed | `no_work` + `verified=True` `rc=0` | `slept_without_work` + journal `farm_evidence_unavailable` + `verified=False` `rc=1` |
| **C4** 一直回不去（`max_days=3`）0 动作日绝不许 VERIFIED | `days=1`、`rc=0`，1 天 0 动作却 VERIFIED | `days=2`、`rc=1`，0 动作却 VERIFIED = **0**（两天 `slept_without_work` 后 `no_day_progress` 停轮） |
| **C6** farm 说 5 格空地 + 有种子但够不着 ⇒ 有界、不空转、不假绿 | 假绿 `rc=0` | `decision` 轮数 **0**、`slept_without_work`、`verified=False` `rc=1` |
| **C7** 0 动作 VERIFIED 必须"自述证据 + 独立在场证据" | 抓出 **2 天**（`zero_action_evidenced=None`） | 抓出 **0 天** |
| **C9** 日初重试成功 ⇒ 当天照常干活、可 VERIFIED | `retry=0 ok=[] ok_steps=0 verified=True rc=0` | `retry=1 ok=[True] ensure_calls=3 ok_steps=54 verified=True rc=0` |

→ 6 项全部翻转，run9c day 20 的机制（`goto_farm{code:"failed"}` 被旧闸门静默跳过 ⇒ `no_work` + 0 动作 VERIFIED）在 pre 树逐字复现、在 post 树消失。

## §4 C 段：六组进攻（真代码，pre/post 都跑）

1. **死循环 / 空转**：C6 —— pre 假绿，post 决策轮数 0 + `slept_without_work` + `rc=1`；C4 —— pre 1 天假绿，post 两天有界收尾（`slept_without_work`×2 → `no_day_progress`），**没有"既睡不着又不干活"的僵局**。
2. **字段缺失 ⇒ fail-closed**：C1（`OLD_MOD_FARM`）post 走 `farm_evidence_unavailable` 且当日不 VERIFIED，**没有把缺失当选 0**。
3. **字段说谎**：C2（farm 谎报全 0、但窗口里有活）两树都**照常干 54 步并 VERIFIED** ⇒ 这是"窗口证据优先"的正确行为，**不是洗白通道**；反过来"farm 说 0 而窗口也看不见活"由 C7/工具闸门兜住（§5）。信任边界说明见 NIT-1。
4. **日初重试只许一次**：C3 post `retry=1`、`ensure_calls=3`、`goto_farm=3`（=1 预备 + 1 日初 + 1 重试），无重复轰炸。
5. **与诚实上限不冲突**：C5（`stamina=8` + farm 有耕地）守卫按 `stamina` 放行，但 `_do_sleep(require_work=True)` 因 0 动作 + 未完成 work ⇒ `slept_without_work`、**`verified=False`** ⇒ 诚实上限不再能掩盖"当天没干活"（口径与 task-134 一致）。
6. **与 task-102 不打架**：C9 重试成功后当天照常干活（`ok_steps=54`）并 VERIFIED `rc=0`；**B2 正对照**（`ZERO_FARM` + 回得去 ⇒ 真没活）两树都 `sleep` + `no_work` + `verified=True`（post `zero_ev=True`）⇒ 新理由没有误杀合法空日。
7. **附：0 动作伪证**（卡面第 3 点）：C7 pre 有 2 天 `zero_action_evidenced=None` 却 VERIFIED；post 0 天。

## §5 工具侧独立闸门交叉核对（C8）

- **伪造**：取 post 真跑的那天账本，改成 `verified=true`、`checks` 全 true、`ok_steps=0`、`stages=[]`、`ended_reason=no_work:…`，并抹掉全部在场证据 ⇒ `tools/verify-run3.py` 命中 `[spring 6] 当天 0 个阶段却自称 VERIFIED，且**没有任何户外农场的在场证据**…`（1 条、`verdict=needs_review`）；只补一条成功 `goto_farm{ok:true}` ⇒ **该条命中 0**。⇒ 闸门真实、边界正确（有在场证据才放行）。
- **真账本同向**：`tools/verify-run3.py --journal scratch/_t150_c8_raw.jsonl --days 1` ⇒ `rc=1 needs_review`，problems = `[spring 6] ended_by=slept_without_work（不是我们主动睡过去的）` + `[spring 6] day_end verified=false` ⇒ **工具与脑同一方向，没有假绿**。

## §6 NIT / INFO

- **NIT-1（不阻塞）**：`_farm_plot_work` 依赖的 `hoeDirt`/`emptyDirt` 是 Mod **自述**，与 `dryCrops` 属同一条信任边界；task-149 没有新增字段类别，也没有新增"自述 ⇒ 当天绿"的通路（C2/C8 反证：自述说谎时要么窗口证据优先、要么被工具在场证据闸门判红）⇒ **不构成本卡引入的洗白通道**。
- **NIT-2（不阻塞，run9d 要盯）**：过度拦截面 —— farm 全域 `emptyDirt>0` 且手上有种子、但作业区/窗口拿不出目标时，当天不 VERIFIED（有界、不空转、不假绿），代价是可能白烧一天。run9c 独立观测（summer 21 10:20：`hoeDirt=224`、`emptyDirt=142`、`crops=82`）说明这个面真机存在。建议 run9d 头几天检查 `stage_stop_named` / `slept_without_work` 是否由这条理由触发；若是，可考虑把该理由收窄到"当前作业区内的空耕地"（0.7.32 顺带）。
- **INFO-1（行为变化）**：C5 显示"0 动作 + 体力耗尽"的日不再睡过去（游戏日不推进）⇒ 跑批以 `no_day_progress` **中止**（`rc=1`）。pre 是睡过去 + `verified=True`。这是卡面要的诚实化，但现场表现是"跑批中止"而不是"跑完但不达标"。
- **INFO-2（纯文案）**：`_unfinished_work` 的 docstring 只列 `work_reasons`/dry-ripe/`buy_no_space`，未提新增的 plot work（实际经 `work_reasons` 已覆盖，行为正确）。

## §7 结论：0.7.31 可否放行

**可以放行。** 三项修法都有 pre/post 原文对照、§5 有独立工具闸门交叉、全量 815 OK 0 红、纯脑侧（无 Mod/无 bump）；两条 NIT 均不影响冻结，NIT-2 建议由 run9d 的现场读数裁决。

## §8 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "<repo>\brain"
# 探针两侧
$env:T150_ROOT = "<repo>\scratch\_t150_pre149"; & $py -W error::SyntaxWarning scratch\_t150_probe.py   # 期望 5/11
$env:T150_ROOT = "<repo>";                          & $py -W error::SyntaxWarning scratch\_t150_probe.py   # 期望 11/11
# 读数
& $py -m unittest tests.test_farmwork tests.test_longrun tests.test_planner   # 456 OK
& $py -m unittest discover -s tests                                           # 815 OK
# 工具交叉
& $py tools\verify-run3.py --journal scratch\_t150_c8_raw.jsonl --days 1      # rc=1 needs_review
```

## §9 越界声明

只写 `docs/_review-task149.md` + `scratch/`；未改 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs/00-开发日志.md`，未 bump、未装机、未碰游戏与桥。
