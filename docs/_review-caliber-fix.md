# 复验：task-86 FAIL 的修复（日标签注入 ⇒ 假 VERIFIED）是否真关上

- 验收人：deputy-lead（task-90，2026-10-15 20:5x）
- 被验对象：**`c6d2a7a`**（`tools/verify-run3.py` +44/−5、`tests/test_verify_run3.py` +55、`docs/_run6-criteria.md` +2），父链 `9681859` / `c062f86`
- 依据：我自己的 task-86 报告 `docs\_review-caliber-2026-10-15.md`（判定 **FAIL**，打穿通道 = `p[1:].split("]", 1)[0]` 按首个 `]` 截断日标签）
- 纪律：只读生产代码与账本、只写 `docs/` 与自己的 `scratch/`；未碰游戏/桥；未改任何生产代码

## §1 判定：**PASS-WITH-NITS**

修复**确实把 B19 关上**，且我用三副本给出"同一输入、判决相反"的证据；新增用例在带洞副本上**真的会红**（非空转）；同类洞普查干净（全工具只剩 1 处按分隔符截断，且对工具自产问题不可达）。两条 NIT（不阻塞）：**B22 标签重名只会保守多报**、**NIT-5 存档比账本新 1 天的处置建议**。

## §2 对象与三副本

| 副本（`scratch/`，`_t90_freeze.py` 用 `git show <rev>:tools/verify-run3.py` 重生成） | 来源 | 行数 | sha256（前 16） |
| --- | --- | --- | --- |
| `_t90_tool_old.py` | `7c4ff68^`（口径变更之前） | 1109 | `7532E7836F75417E` |
| `_t90_tool_buggy.py` | `7c4ff68`（尾部窗口口径，带 B19 洞） | 1139 | `3573A39700B9BDD3` |
| `_t90_tool_fixed.py` | `c6d2a7a`（修复版；与仓库现行 `tools/verify-run3.py` **逐字节相同**） | 1173 | `636FD5018C08F297` |

修复要点（逐行核对 `git show c6d2a7a -- tools/verify-run3.py`）：`_clean_label()` 净化 `[`/`]`/`\n`/`\r`/`\t` 且空串归 `"?"`（`:85-99`）并接入 `day_key()`（`:101-113`）；新增 `problem_day(text, known)`（`:115-128`）= 先按 `sorted(known, key=len, reverse=True)` 做**最长前缀匹配**，匹配不到才退回朴素截断；降级条件改为 `if head and head in known_names and head not in tail_names`（`:940-951`）⇒ **head 不属于任何已知日 ⇒ 一律 fatal**。

## §3 同输入三判决（`scratch/_t90_replay.py`）

A4b = 3 天尾部窗口 + 中间那天"自称达标但账目自相矛盾"（`stage leftover=2` 而 `checks.no_unmet_stages=true`）+ 该日 `day_start.day[1] = "spring]x"`。

| 账本 | old | buggy | fixed |
| --- | --- | --- | --- |
| `review-t86-a4b-inwindow-contradiction-injected-key.jsonl` | rc 1 / 1 problem / 0 history | **rc 0 / VERIFIED / 0 problem / 1 history（洞）** | **rc 1 / needs_review / 1 problem / 0 history（关上）** |
| `review-t86-a4a-…-normal-key.jsonl`（对照） | rc 1 / 1 / 0 | rc 1 / 1 / 0 | rc 1 / 1 / 0 |
| A2 窗口内中间日矛盾 | rc 1 / 1 / 0 | rc 1 / 1 / 0 | rc 1 / 1 / 0 |
| A3 停在坏的一天 | rc 1 / 6 / 0（streak 0） | rc 1 / 6 / 0 | rc 1 / 6 / 0 |
| A1 / A5 / A6（窗口外降级 = 设计行为） | 见 limits §11 | buggy == fixed 逐字相同 | 同左 |

fixed 上 A4b 的问题原文：`[springx 11] checks.no_unmet_stages=True 与自算不一致（… leftover=5 格 … 期望 False）`（标签被 `_clean_label` 净化为 `springx 11`，属已知日且是窗口内那天 ⇒ 留 fatal）。

## §4 用例非空转（`scratch/_t90_nonvacuous.py`）

做法：测试模块把工具绑在全局 `vr` 上（`tests/test_verify_run3.py:18-21`），把 `vr` 换成冻结副本再跑那两条新用例。

| 副本 | `test_bracket_in_day_label_cannot_hide_an_in_window_problem` | `test_unknown_problem_day_label_is_never_demoted` |
| --- | --- | --- |
| old | FAIL（`KeyError: 'history_problems'`） | FAIL（无 `problem_day`） |
| buggy | **FAIL：`AssertionError: True is not false : 窗口内的问题带 \`]\` 标签也必须 fatal`** | FAIL |
| fixed | PASS | PASS |

⇒ 第一条用例**确实会抓住这条回归**（在带洞副本上必红、在修复版上必绿），第二条把 `day_key`/`problem_day` 的期望值直接钉住（含 `[spring]x 11]`、`[summer 99]`、无前缀三种不属已知日的情形）。

## §5 同类洞普查（重点，`scratch/_t90_survey.py`）

1. **分隔符截断只剩 1 处**：`grep` 全工具的 `split(` / `[1:]` / `rsplit(` 只有 `problem_day()` 的 fallback（`tools/verify-run3.py:127`）；工具内**无任何正则**（`re.` 零命中）。
2. **该 fallback 对工具自产问题不可达**（间谍统计）：跑 `scratch/*.jsonl` + `logs/*.jsonl` 共 **85 本 / 170 次 `report()`**（`--days 1/3`）⇒ `problem_day` 调用 **609 次**：最长前缀命中 **606**、走 fallback **0**、其余 3 次是不带 `[` 的全局问题（`head=""` ⇒ fatal）。理由：问题前缀恒为 `name = d["key"]`，而 `key` 已被 `_clean_label` 净化、必属 `known_names`。
3. **脏标签矩阵**（窗口内那天换各种脏标签，其余不变）：`spring` / `spring]x` / `spring\n14` / `sp[ring\t14` / `""` ⇒ 全部 **rc 1 / 1 problem / 15 history**（窗口外那 15 条照旧降级、窗口内这条降不下去）。
4. **重名方向性（B22）**：谓词级 `[spring 15]`（标签与窗口内某天同名）⇒ 降级=False（保守留 fatal）；把窗口外坏日的日号改成窗口内那天的日号（真同名）⇒ `rc 1`、`#problem=6`、`#history=10` ⇒ **只多报、不漏报**。
5. 其余"从文本解析结构化字段"的站点逐条看过：`tools/verify-run3.py:221` / `:765` / `:787` 对 `ended_reason`/`reason` 做 `startswith("no_work"/"night"/"stamina"/"no_water")` 白名单、`:321` 拼 `reason/note/tile/tiles` 后按 `_UNREACH_MARKS` 子串计数、`:1016` 数非空行 ⇒ 都属**信任账本自述**类（B11/B16/B20 一线），不是解析 bug，本卡不动。

## §6 回归读数（task-90 当时主树，HEAD `da1b30c`）

- `py_compile -W error::SyntaxWarning tools\verify-run3.py tests\test_verify_run3.py` ⇒ **exit 0**。
- `python -m unittest tests.test_verify_run3` ⇒ **Ran 46 / OK**（与 Lead 报数一致）。
- `python -m unittest discover -s tests` ⇒ **Ran 550 / FAILED (failures=1)**；唯一红 = `tests/test_analyze_longrun.py::TestEventMappingDrift::test_event_buckets_cover_every_brain_journal_name`，差异 `['day_end','day_start','finish','surplus_sell','surplus_sell_skip'] != ['day_end','day_start','finish']` —— `brain/agentfarm/farmwork.py:67`（`surplus_sell_plan`）与 `:810`（`surplus_sell_skip`）已在工作树（dev-coder task-55 在制），`tools/analyze-longrun.py` 的 `EVENT_BUCKETS` 尚未跟上（log-analyst task-88 在制）⇒ **归属 task-55/task-88 的跨卡集成缺口，不计入本卡**。
- **85 本三副本并排**（`scratch/_t90_side.py 3` → `scratch/_t90_side_d3.txt`）：`buggy`↔`fixed` **只有 B19 那 1 本不同**；`old`↔`buggy` 不同 5 本 = run7（口径变更的设计行为）+ 我自造的 A1/A4b/A5/A6（同一口径变更）。**run7 在 buggy/fixed 上逐字相同**（rc 0 / 0 problem / 9 history / streak 3 / VERIFIED）⇒ 修复没有改动任何真实账本的判决。

## §7 顺带①：`docs/_run6-criteria.md` §2 是否堵住"用窗口口径掩盖系统性缺陷"

§2 第 60-66 行现在写明：①达标的定义就是"尾部连续 N 天"；②窗口内问题 + 无 `[day]` 前缀的全局问题才 fatal；③`streak < --days` 不降级；④**取舍写死**并给三条留痕义务 —— `_runN-evidence.md` §4 必须**逐条抄出 `history_problems`** 并写清"过的是哪 N 天、窗口外还有 N 条"；**系统性**缺陷（例 A6 形态）必须**单独点出、明说只是不落在验收窗口内**；严格口径要**并列旧整本结论**作为第二判决；⑤task-86 的修复说明。

评估：**作为"流程约束"够用**（把"窗口外不计"从默认沉默变成显式义务，且给了第二判决的具体做法）。但要如实说明两点残余：**(a)** 这些是**文档义务**，工具本身仍只输出 `VERIFIED`（唯一的机器提示是"历史问题…共 N 条"这段标题），执行强度取决于写 evidence 的人；**(b)** 严格判决需要人工跑旧口径（或"临时关掉降级"），没有一条命令。低成本的补法（本卡不改，报 Lead）：人类输出在 `history_problems` 非空时多打一行"严格口径请并列 `--strict` / 旧整本结论"，或直接加一个 `--strict` 开关打印第二结论。

## §8 顺带②：NIT-5（存档比账本收尾新 1 天）建议

**建议：账本带 `finish` 时降 info，无 `finish` 或相差 ≥2 天时判 problem。**
理由：run7 的存档链（SMAPI 在 `23:18:27`、`23:33:11` 还各有 NewDay+Save，而 journal 在 `23:18:29` 已 `finish` 停写）证明这是"**跑批窗口短于游戏会话**"的常见产物，与账本真伪无关；真正需要人工确认的是**没有 `finish`**（跑批被中断/崩溃）或**存档落后/领先 ≥2 天**。落地位置：`tools/verify-run3.py` 存档比对段（`if d.get("finish")` + gap 判断）；**本卡不改工具**，交 Lead 定。

## §9 结论与复现

**PASS-WITH-NITS**：B19 已关闭（同输入判决相反、用例非空转、85 本并排只有该负例改变）；B20/B21/B11/B16/B17 一律保留开放；新增 B22（重名只多报）与 NIT-5 建议。

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
& $py scratch\_t90_freeze.py        # 三副本 → scratch/_t90_tool_{old,buggy,fixed}.py
& $py scratch\_t90_replay.py        # 7 本伪造账本 × 三副本 → scratch\_t90_replay.txt
& $py scratch\_t90_nonvacuous.py    # 测试的 vr 换成三副本 → scratch\_t90_nonvacuous.txt
& $py scratch\_t90_survey.py        # 脏标签 / 重名 / fallback 普查 → scratch\_t90_survey.txt
& $py scratch\_t90_side.py 3        # 85 本三副本并排 → scratch\_t90_side_d3.txt
& $py -m unittest tests.test_verify_run3   # Ran 46 / OK
```
