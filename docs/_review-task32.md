# task-32 独立验收（deputy-lead）

**判定：PASS-WITH-NITS**（无必修项；NIT 均为 tools/ 侧文案/映射或既有口径，非本卡引入）
对象 = 未提交在制品（HEAD `cf4e89a`「0.7.23 冻结装机 + 脑侧睡觉链路真机 VERIFIED」之上）：
`brain/agentfarm/longrun.py` + `tests/test_longrun.py`，`git diff --stat HEAD` = **190 insertions / 11 deletions**（2 文件）。

## §1 条款 1：读数复核 —— 过

| 项 | 我亲跑读数 |
|---|---|
| `git status --short` | 只有 ` M brain/agentfarm/longrun.py`、` M tests/test_longrun.py`（其余是我自己的 `?? scratch/_t32_*.py`） |
| `brain/agentfarm/longrun.py` SHA256 | `E64453C0AD7AA13DDB538E5456691B12775756E6F1764A204709E71A49BE3525`（= dev-coder 自报逐字一致） |
| `tests/test_longrun.py` SHA256 | `4B37C390BC6F489159FC1A3D0ADFC9B1D9563AB80BB1D9F631E54BD07AFA0EF3`（= 自报逐字一致） |
| `py_compile`（longrun/farmwork/bridge/planner） | exit 0 |
| 全量 `unittest discover -s tests` | **`Ran 313 tests in 2.607s` / `OK`**（309 + 本卡 4 条 = 313，数目自洽） |
| `tests.test_longrun -k Task32`（副本对照跑，见 §6） | `Ran 4 tests` / `OK` |
| `mod/AgentFarm.Bridge/manifest.json:4` | `"Version": "0.7.23"`（**未**因本卡变动） |
| `brain/agentfarm/bridge.py:39` | `MOD_VERSION_EXPECTED = "0.7.23"` |
| 越界 | 见 §7（`docs/00-开发日志.md`、`logs/`、`mod/`、`tools/`、`scratch/` 的 `git diff --numstat HEAD` 全空） |

## §2 条款 2：`no_plot` 双删 —— 过

- 全仓 grep `no_plot`（`brain/`、`tools/`、`tests/`）：`brain/` 命中 **9 处全部是注释/docstring**（`longrun.py:169-172`、`:180`、`:752-753`、`:794`、`:1822`、`:1989`），代码路径 **0 处**；带引号的 `"no_plot"` 只有 `longrun.py:752` 的 docstring（描述旧行为）。
- `_do_sleep(..., "no_plot")` 这类调用**不存在**：`_do_sleep` 的 5 个调用点分别是 `:1547`（`f"{code}:{text}"`，code 来自 `sleep_guard`）、`:1815`（同）、`:1834`（`"no_work"` 或 `"stuck:…"`）、`:1883`（`"no_work:换过 N 片地都没有目标"`）、`:1895`（`"no_work"`）。
- `longrun.py:173` `JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")` ✅（**不含** `no_plot`）。
- `longrun.py:176-185` `is_justified_end()`：`ended_by != "sleep"` ⇒ False；否则取 `ended_reason.split(":", 1)[0]` 查白名单。
- **直接探针**（导入产线模块实测，非引用用例结论）：白名单 `('night','stamina','no_work')`；`('sleep','night:到点了')→True`、`('sleep','stamina:体力低')→True`、`('sleep','no_work:确实没活')→True`、**`('sleep','no_plot:找不到有活的作业区')→False`**、`('sleep','stuck:守卫说还有活')→False`、`('sleep_failed','no_work:…')→False`、`('stuck','no_work:…')→False`、`('pass_out','日期自己变了')→False`、`('sleep','')→False`。
- `sleep_guard`（`:1007-1031`）只会返回 `"night"`（`:1017`）/`"stamina"`（`:1027`）/`"no_work"`（`:1030`）三个前缀（不放行时是 `"keep_working"`，不结束一天）⇒ 守卫路径的 `ended_reason` 前缀恒在白名单里，无"漏加前缀"的洞。

## §3 条款 3：软上限语义 —— 过（有一处语义变化要在 NIT 里说明）

- `longrun.py:744-786 _ensure_plot`：①当前 `self.plot` 有活 ⇒ 直接保持（`:756-757`）；②否则按候选顺序找第一个有活的区：**配额未满** ⇒ 计数 + `rep.plots.append`（`:773-783`）；**配额已满** ⇒ `self.plot = cand` + 播报一次 `plots_capped`（`:761-772`）并 `return self.plot`，**不**增 `plots_today`、**不**进 `rep.plots`。
- **不会"同一区反复被当成新作业区"**：一旦进入触顶分支 `self.plot = cand`，下一轮由 `:756-757` 直接保持，只有该区**真的没活了**才会再走触顶分支 ⇒ 每次都是真实换片，不存在原地自旋。
- **`plots_capped` 每天最多一次**：`self.plots_capped_noted` 在 `:428` 初始化、在 `:1754`（与 `self.plots_today = 0` 同一日重置块）复位；`:764-771` 只在未播报时记 note/journal。用例 `tests/test_longrun.py:2042`（`max_plots_per_day=0` ⇒ 每次换片都会命中触顶分支）实测 `len(events("plots_capped")) == 1` ⇒ 复位时机正确。
- **`rep.plots == []` 的成立条件**：`plots_today` 与 `rep.plots` **只在一起增减**（`:775` 与 `:776-779`），所以不变式是 `len(rep.plots) == plots_today`。`rep.plots == []` 只在 `plots_today == 0` 时成立 —— 这正是用例的场景（`max_plots_per_day=0`）。默认 `max=10` 时触顶当天 `rep.plots` 会有 10 条、触顶区**不入账**（由 `plots_capped` journal 留痕）⇒ 设计如此，不是洞。
- **`max_plots_per_day` 是否彻底失效**：作为"当天使用过几片地的上限"——**是**（触顶后可以无限换片）；作为"计入记账的新开区数"与"换片重试预算"——仍然生效（`:1881 if recovered > self.max_plots_per_day` ⇒ 不再无限换片，收敛到收工）。⇒ 语义从"一天最多用几片地"变成"一天最多**记账**几片地 + 换片预算"。这本身是本卡的意图，但两处面向用户的文案没跟上（NIT-1）。

## §4 条款 4：不许死循环 —— 过

- `plot is None` 分支（`:1818-1839`）：`spot = self._work_spot_plot(obs) or self._near_player_plot(obs)`；`spot is None` ⇒ 组 `why`（守卫说没活 ⇒ `"no_work"`；守卫说还有活却拿不出目标 ⇒ `"stuck:守卫说还有活（…）但没有任何作业区拿得出目标"`）⇒ `_do_sleep` 后 **`break`**（单次、不空转）。
- `spot` 非空 ⇒ `plot = spot`：`_work_spot_plot`（`:799-803`）与 `_plot_has_work`（`:731-734`）对"有活"的判据同源（`crop` 且（未浇水 或 已成熟））⇒ 不会出现"兜底区拿得出、下一轮 `_ensure_plot` 又说没活"的乒乓。
- 其余有界性兜底（都在本卡之外、未被改动）：`recovered > max_plots_per_day` ⇒ `_do_sleep` + `break`（`:1881-1885`）；`idle_rounds >= 3` ⇒ `ended_by="stuck"` + `break`（`:1912-1916`）；`sleep_guard` 放行（夜里/体力/没活）与 `time_limit`/`budget`（`:1788`）也会收工。
- **`_do_sleep` 文案与前缀一致性**：`:1056-1071` 成功时 `return "sleep", why`（`ended_reason` **逐字等于** why）⇒ `stuck:…` 的 `ended_reason` 前缀就是 `stuck`（`day_justified=False`）、`no_work` 前缀就是 `no_work`；失败时 `return "sleep_failed", st.reason`（`ended_by != "sleep"` ⇒ 一律不 justified）。无"文案说 stuck、记账说 sleep"的错位。

## §5 条款 5：`day_justified` 不误伤合法收工 —— 过

- `longrun.py:1991` `"day_justified": is_justified_end(rep.ended_by, rep.ended_reason)`；`:1992` `rep.verified = all(rep.checks.values())` ⇒ `day_justified=False` 必然把当天压成 `verified=False`（不会被别的 check 顶掉）。
- 直接探针（§2）证明：夜里/体力/`no_work` ⇒ True；`no_plot` / `stuck` / `sleep_failed` / `pass_out` / 空 reason ⇒ False。
- 与 `tools\verify-run3.py` 口径**不冲突**：全仓 grep `day_justified` 在 `tools/` 只有 `analyze-longrun.py:74` 一句**说明文字**，`verify-run3.py` **不读**这个字段；它靠 `verified=false`（:360-361）、`ended_by != "sleep"`（:301-302）、以及"0 步 VERIFIED 的豁免前缀 `no_work/night/stamina`"（:393-397）判 ⇒ 与本卡白名单同源，没有第二套口径。（文案滞后见 NIT-1。）

## §6 条款 6：4 条新用例能证伪 —— 过（3 条独立变异，且都在副本里做）

手法：`scratch\_t32_mutate.py` 把整个 `brain/agentfarm` 复制到 `scratch\_t32_mut\agentfarm`，只在**副本**注入一处错误；`scratch\_t32_falsify.py` 先 import 副本的 `agentfarm.longrun` 占住 `sys.modules` 再加载测试（`tests/test_longrun.py` 会自己把 `brain/` 插到 `sys.path[0]`，光设 `PYTHONPATH` 无效）。生产文件全程只读。

| 变异 | 注入点 | 结果 |
|---|---|---|
| 对照（未注入） | — | **`Ran 4 tests` / `OK`**（跑了两次，第二次用于确认可复现） |
| `m32a_no_plot_whitelisted` | `longrun.py:173` 白名单加回 `"no_plot"` | ✅ 红：`test_no_plot_is_not_a_justified_reason` —— `AssertionError: 'no_plot' unexpectedly found in ('night','stamina','no_work','no_plot')` |
| `m32b_cap_returns_none` | `longrun.py:761-772` 触顶分支换回旧行为（`return self.plot if … else None`） | ✅ 红：`test_capped_with_work_in_zone_keeps_the_day_going` —— `AssertionError: 0 != 1 : []`（`plots_capped` 事件 0 条，期望 1 条） |
| `m32c_no_work_spot` | `longrun.py:800-801` 把 `_work_spot_plot` 的 tiles 置空 | ✅ 红：`test_work_outside_any_zone_is_done_instead_of_sleeping_no_plot` —— `AssertionError: unexpectedly None` |

- 变异后生产两支哈希复算**仍是 §1 的值**（`E64453…`、`4B37C3…`）⇒ 未碰生产文件。
- 4 条用例位置：`tests/test_longrun.py:2030 class TestTask32PlotsCap`，:`2042`（触顶但区内有活 ⇒ 当天干完 + `plots_capped` 恰 1 条 + `rep.plots == []` + 非 `no_plot` 前缀 + `verified`）、:`2068`（触顶 + 真没活 ⇒ 仍能正当收工 `no_work`）、`:2088`（活落在任何区之外 ⇒ 收尾作业区浇掉、`work_spot` 留痕、**不许** `no_plot`）、`:2116`（白名单/函数直判）。
- **过程失误记录**（避免后人重踩）：`_t32_falsify.py` 的入参会被拼成 `tests.test_longrun.<arg>`，第一轮我传了裸方法名 ⇒ 三条都报 `unittest.loader._FailedTest ... AttributeError: module 'tests.test_longrun' has no attribute '<name>'`，**exit code 也是 1，看着像"变异成功"**。必须传 `TestTask32PlotsCap.test_xxx`；"哪条用例红了"永远要看 `FAIL:` 行，不能只看退出码。
- 未验的第 4 条（`test_capped_and_no_work_anywhere_still_sleeps_no_work`）未做变异：它断言的是"触顶 + 守卫放行 ⇒ `no_work` 前缀"，与 `m32a`/`m32b` 的注入面重叠（白名单/触顶分支任一改错它也会受牵连），收益低于上述三条。

## §7 条款 7：越界检查 —— 过

- `git diff --numstat HEAD -- "docs/00-开发日志.md" logs mod tools scratch` ⇒ **空**（`mod/` 未动 ⇒ `manifest.json` 仍 0.7.23 且非本卡所改；`tools/`、`logs/`、`scratch/`、开发日志均未被碰）。
- `git status --short` 只有 §1 的两个 ` M` 文件；新增文件只有我自己的 `scratch/_t32_falsify.py`、`scratch/_t32_mutate.py`（+ 副本目录 `scratch/_t32_mut/`）。
- 未 deploy、未 bump、未跑真机、未碰游戏/桥（Lead 正在跑 0.7.23 彩排）。

## §8 NIT 清单（均不阻塞；NIT-1/2 属 `tools/`，是 Lead 的写范围）

| 编号 | 位置 | 现象 | 建议 | 阻塞? |
|---|---|---|---|---|
| NIT-1 | `tools/analyze-longrun.py:74`、`:750`、`tools/run-longrun.py:57` | 文案滞后于本卡：`day_justified` 说明仍写"（night/stamina/no_work/**no_plot**）"、`sleep_at` 提示仍提 `no_plot`、`--max-plots` help 仍写"一天最多开几片地（默认 10）" | 改成"夜里/体力/没活（`no_plot` 不再算）"；help 改为"一天最多**计入记账**的开区数（触顶后仍在有活的区继续干）" | 否（文字；判据本身是数据驱动） |
| NIT-2 | `tools/analyze-longrun.py:142-174 EVENT_BUCKETS` + `:308-310` | 新事件 `plots_capped` / `work_spot` 未入桶 ⇒ 未映射事件被**静默忽略**（不报错，只是分析报告里看不到"作业区触顶/收尾活"这一形态，run3 复盘会缺一角） | 加两个桶 + 一行说明；`verify-run3.py` 不消费事件清单，可不动 | 否 |
| NIT-3 | `brain/agentfarm/longrun.py:1881-1885` | 既有口径（**本卡未改**）：换过 >`max_plots_per_day` 片地都没目标时用 `no_work:…` 前缀收工 ⇒ `day_justified=True` 可能判 VERIFIED，而此刻守卫仍在说"还有活" —— 与"`no_plot` 不许洗白"属同一类风险（"换 11 片地都没目标"≠"没活可做"） | 后续立卡：该出口改用 `stuck:` 前缀（或要求 `recovered` 收敛时给出"确定没活"的更强证据） | 否（未变坏，但建议排 run3 之后） |
| INFO | `tests/test_longrun.py:2042` 等 3 条用例 | `max_plots_per_day=0` 是把"触顶"推到极限的写法（等价"一片新地都不许记账"），不是生产默认值 | 已知；默认 10 时触顶当天 `rep.plots` 有 10 条（不变式 `len(rep.plots)==plots_today`） | 否 |

## §9 结论

条款 1–7 全部通过：读数与自报逐字一致、`no_plot` 在 `brain/` 代码路径已被双删（白名单 + 调用点）、软上限"触顶仍在区内继续、一天只播报一次、不入换区记账"与"`plots_capped`/`work_spot` 留痕"都成立且**有界**（单次 `break` + `recovered`/`idle_rounds` 双兜底）、`day_justified` 只认"睡觉成功 + 夜里/体力/没活"、4 条新用例中 3 条已被独立变异证明**能证伪**。唯一需要跟的是 tools/ 侧三处文案滞后与新事件未入桶（NIT-1/2，非本卡、非阻塞）和一条既有口径（NIT-3，建议后续立卡）。⇒ **PASS-WITH-NITS，无必修项**。
