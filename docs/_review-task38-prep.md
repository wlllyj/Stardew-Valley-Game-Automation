# task-38 / 0.7.48 对抗验收预置骨架（deputy-lead）

> 状态：**骨架 ONLY**。0.7.48 尚未冻结；**不要**对未存在的冻结 commit 编造读数。
> 立场：不信作者自述、不信回执。变异必须**实测**（作者自报的杀数不算证据，必须能在 `git archive` 冻结树上复跑出来）；缺失 ≠ 通过；判据一律用独立观测差分。

- 撰写：deputy-lead（只写 `docs/_review-*.md`、`scratch/`）
- 参考：`docs/_review-task32.md`、`docs/_review-task143-144.md`（对抗验收写法）
- 相关：`docs/_release-0.7.47.md` §7、`docs/_smoke-0746.md`、`tools/_note-0741.txt`、`scratch/smoke-0742.py:680`

## 1. 目的

为 task-38（slot_relief 字段奇偶补齐：task-237 要求 `demand/demand_basis/target_free/reached` 四字段齐全，尤其 clear_gate 分支漏写 `reached`）预置对抗验收骨架。含：

1. `git archive` 冻结树双跑 provenance（文件数 / 关键 blob / 全量单测）
2. **四把伪造判据**（C1–C4）及扩展测量（C4d–C6），记录**修前红/绿**（当前工作树，dev-coder 修复+测试均为未提交在制改动），待 0.7.48 冻结后在**冻结树**上重跑同一清单。每把都要能被 dev-coder 新增的定向单测判红，否则是该测试的漏洞。
3. “自报 vs 实测”两列模板。

## 2. 5.3 provenance 现状（摘要，不是读数）

- HEAD：`430b3cb` `test(review): task-37 0.7.47 增量验收探针与变异脚本`
- 冻结 commit（0.7.47）：`a03a564`（`chore(release): 冻结 0.7.47`）
- `git diff --stat a03a564 HEAD`：仅 docs + scratch（6 files, 1250 insertions）；`git diff a03a564 HEAD -- mod/`：空（mod/ 与 a03a564 一致）
- 安装 dll（游戏 Mods）：`D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Mods\AgentFarm.Bridge\AgentFarm.Bridge.dll`  
  大小 293888B，SHA256 `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A`
- 仓库构建产物：`mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` 同大小/同 SHA256；`mod/AgentFarm.Bridge/AgentFarm.Bridge.dll` 仓库内不存在（a03a564 中该路径为 0 bytes） ⇒ dll 是构建产物，不进入 git
- manifest：版本 0.7.47 三方一致；工作树 `mod/AgentFarm.Bridge/manifest.json` 76849B (CRLF) vs a03a564 blob 76839B (LF)——仅行结束差异
- 结论（现状核对）：repo（a03a564 树）/ 安装 dll / bin/Release 三方一致性**基本确认**（细节见 b5 摘要）；如需绝对一致性，可在冻结后从冻结树独立 dotnet 重建验证。

## 3. 5.2.1 `git archive` 冻结树双跑 provenance（计划）

> **骨架**：列出必须记录的项，不填数值（0.7.48 未冻结）。

### 3.1 目标 ref（冻结后）
- `FROZEN_REF = <0.7.48 freeze commit SHA>`（待 lead/仓库标定）

### 3.2 导出方式（不可变基线）
使用 `git archive --format=tar` 将 `FROZEN_REF` 导出到临时目录 `TMP/frozen-0.7.48/`，在该**只读导出树**上完成所有测量（避免工作树污染）。对比基线：可选再导出 `a03a564` 或 `HEAD` 做对照。

### 3.3 必须记录的指标

| 项目 | 如何测量 | 预期用途 |
|---|---|---|
| **导出文件数** | `find TMP/frozen -type f \| wc -l`（或 Python） | 证明冻结树完整导出，无遗漏文件 |
| **关键 blob 一致性** | 针对关键文件（`brain/agentfarm/longrun.py`、`tests/test_longrun.py`、`brain/agentfarm/bridge.py`、`mod/AgentFarm.Bridge/manifest.json`）计算 SHA256 | 证明“冻结树 = 该 commit 的内容树”（排除工作区改动/CRLF 干扰说明） |
| **关键路径清单** | 列出影响 task-38 的 4 个 slot_relief 写入点文件版本（longrun.py 的 `_note_clear_area_bag_gate`、`_note_slot_pressure_stuck`、`_slot_relief` 主通道、buy_full 分支）及其在冻结树内的行范围 | 锚点版本化（mutation anchors 必须在冻结树版本上生效） |
| **全量单测（冻结树）** | `cd TMP/frozen && PYTHONUTF8=1 PYTHONPATH=brain python -m unittest discover -s tests 2>&1 \| tail -5` | 记录 `Ran N tests / OK`（按 AGENTS §2：只看该行）。**不得**凭 stderr exit code 判失败。 |
| **定向单测（冻结树）** | `cd TMP/frozen && PYTHONUTF8=1 PYTHONPATH=brain python -m unittest tests.test_longrun.TestTask38SlotReliefFieldParity -v 2>&1 \| tail -2` | 0.7.48 冻结后必须是 `Ran 4 tests / OK`（基线工作树已是 OK） |
| **双跑自洽** | 对同一 `FROZEN_REF` 做两次独立 `git archive` → 导出到不同 temp → 对关键文件 SHA256 全等；对全量单测结论（Ran/OK）一致 | 排除导出/环境抖动 |

> 注：`scratch/_t5_prov.py` 已具备 `prov <ref> [--tests]` 子命令骨架（见 b5 摘要），可复用于 3.3 的自动化记录。

## 4. 5.2.2 四把伪造判据 + 扩展测量（C1–C6）

### 4.1 测试对象（oracle）

- **A. 探针口径（字段存在性）**：AST 扫描 `brain/agentfarm/longrun.py` 所有 `_journal("slot_relief", ...)` 调用，检查 `TASK237 = ("demand","demand_basis","target_free","reached")` 是否齐全。等价于 `scratch/smoke-0742.py:680` 的字面量子串校验（`f'"{k}"' not in json.dumps(r)`）。
- **B. 定向单测口径**：`tests.test_longrun.TestTask38SlotReliefFieldParity`（dev-coder 新增，未提交）。杀数判定：单测输出含 `FAILED` ⇒ **KILL**，否则 **SURVIVE**。

脚本：`scratch/_t38_mutate.py`（只写 scratch/；不改生产代码）。用法：`PYTHONUTF8=1 python scratch/_t38_mutate.py`（当前工作树基线）或 `--ref <FROZEN_REF>`（冻结树基线）。

### 4.2 修前实测（当前工作树，2026-10-18）

基线（无变异）：探针 **PASS**（slot_relief 调用 4 处）；定向单测 **SURVIVE**（`Ran 4 tests in 0.003s | OK`）。

| 用例 | 说明 | 探针预期 | 探针实测 | 单测预期 | 单测实测 | 判红测试 |
|---|---|---|---|---|---|---|
| **C1_drop_reached_arg** | 删掉 clear_gate 的 `reached` 参数（原始缺口复现） | FAIL | **FAIL** | KILL | **KILL** | `FAIL:`（test_clear_gate_channel_carries_task237_fields） |
| **C2_reached_always_true** | clear_gate 的 `reached` 语义改错（恒 True） | PASS | **PASS** | KILL | **KILL** | `FAIL:`（clear_gate assertIs(False) 被击破） |
| **C2b_main_reached_true** | 主通道 `reached` 语义改错（恒 True） | PASS | **PASS** | KILL | **SURVIVE** | `-` |
| **C3a_drop_reached_other_site_pressure** | 漏修其它写入点：压力卡死（`_note_slot_pressure_stuck`, ~6296）丢 `reached` | FAIL | **FAIL** | KILL | **KILL** | `FAIL:`（test_pressure_stuck_channel_carries_task237_fields） |
| **C3b_drop_reached_other_site_buy_full** | 漏修其它写入点：buy_full（~7455）丢 `reached` | FAIL | **FAIL** | KILL | **KILL** | `FAIL:`（test_buy_full_channel_carries_task237_fields） |
| **C4a_demand_basis_buy_full_changed** | 改 buy_full 点的 `demand_basis` 值（buy_full→space_pressure） | PASS | **PASS** | KILL | **KILL** | `FAIL:`（13818 assertEqual buy_full） |
| **C4b_demand_basis_clear_gate_changed** | 改 clear_gate 点的 `demand_basis` 值（space_pressure→buy_full） | PASS | **PASS** | **?** | **SURVIVE** | `-` |
| **C4c_demand_basis_main_changed** | 改主通道的 `demand_basis` 值（变量→"WRONG"） | PASS | **PASS** | **?** | **SURVIVE** | `-` |
| **C4d_demand_basis_pressure_changed** | 改压力卡死点的 `demand_basis` 值（space_pressure→buy_full） | PASS | **PASS** | **?** | **SURVIVE** | `-` |
| **C5_target_free_value_wrong** | clear_gate 的 `target_free` 写错（`SLOT_RELIEF_TARGET_FREE`→`99`） | PASS | **PASS** | **?** | **KILL** | `FAIL:`（13835 assertEqual target_free） |
| **C6_reached_int_zero** | clear_gate 的 `reached` 写成 `int 0`（非 `False` singleton） | PASS | **PASS** | **?** | **KILL** | `FAIL:`（13833 assertIs(False)） |

### 4.3 洞（漏洞）分析

以下 4 把在**修前**未被定向单测判红（SURVIVE）——**是 dev-coder 新增的定向单测本身的覆盖漏洞**，而非实现漏洞：

1. **C2b_main_reached_true（主通道 reached 恒 True）——SURVIVE**  
   `test_main_slot_relief_channel_carries_task237_fields`（13783-13793）仅用 `_full_with_surplus()` 一种 fixture，断言 `reached == (freeSlots_after >= target_free)`。当该 fixture 的 `freeSlots_after >= target_free` 为 **True** 时，常量 `True` 也能通过等值断言 ⇒ **无法区分“动态计算”与“谎报恒 True”**。建议：在主通道测试中补充**至少一个场景**使 `freeSlots_after < target_free`（reached 理应为 False），以便 `reached=True` 恒定值被判红。

2. **C4b_demand_basis_clear_gate_changed（clear_gate demand_basis 值被篡改）——SURVIVE**  
   `test_clear_gate_channel_carries_task237_fields`（13823-13835）未断言 `gate[0]["demand_basis"]` 的**具体值**（只靠 `_assert_task237` 保证“键存在”+探针子串存在）。篡改为 `"buy_full"` 后键仍在、子串 `"demand_basis"` 仍在 ⇒ 探针口径（存在性）PASS，但**语义值**未被校验。建议补充：`self.assertEqual(gate[0]["demand_basis"], "space_pressure")`。

3. **C4c_demand_basis_main_changed（主通道 demand_basis 值被篡改）——SURVIVE**  
   主通道测试 13790 只调用 `_assert_task237`（存在性），未断言 `demand_basis` 的取值（主通道应为 `"space_pressure"`）。建议补充值断言。

4. **C4d_demand_basis_pressure_changed（压力卡死点 demand_basis 值被篡改）——SURVIVE**  
   压力通道测试 13805-13807 未断言 `demand_basis` 值（应为 `"space_pressure"`）。建议补充值断言。

> 注：C5（target_free 值错）在 clear_gate 测试 13835 已被断言值 ⇒ **KILL**。C6（reached 写成 `0` 而非 `False`）被 `assertIs(ev[0]["reached"], False)` 击破 ⇒ **KILL**。C2（clear_gate 恒 True）被同一 `assertIs(..., False)` 击破 ⇒ **KILL**。C1/C3a/C3b 靠 `_assert_task237` 的“键存在”击破 ⇒ **KILL**。C4a（buy_full 点值错）被 13818 的 `assertEqual(ev[0]["demand_basis"], "buy_full")` 击破 ⇒ **KILL**。

### 4.4 修复后的预期（冻结树，待测）

待 0.7.48 **冻结**后：
1. 在冻结树（`git archive FROZEN_REF` 导出树）上重跑 `scratch/_t38_mutate.py --ref FROZEN_REF`。
2. **预期**：C1,C2,C3a,C3b,C4a,C5,C6 维持 **KILL**；C2b,C4b,C4c,C4d 是否依旧 **SURVIVE** 取决于 dev-coder 是否在冻结前补强了定向单测的值断言/场景覆盖。**若冻结树上的定向单测未补强而上述 4 把仍 SURVIVE，则该漏洞必须在验收结论中如实记录（不许掩盖）**。
3. 同时在冻结树上跑 `TestTask38SlotReliefFieldParity` 基线：必须 `Ran 4 tests / OK`。

### 4.5 冻结树实测结果（2026-10-19 补录；FROZEN_REF=`e2b69d9`）

**已实测（`scratch/_t38_mutate.py --ref e2b69d9`，输出 `scratch/_t38_mutate_out_freeze_e2b69d9.txt`）：** 与 §4.2 修前工作树读数**完全一致** —— 基线探针 `PASS ['slot_relief 调用 4 处']`、定向单测 `Ran 4 tests / OK`；**KILL 7 把**（C1,C2,C3a,C3b,C4a,C5,C6），**SURVIVE 4 把**（C2b,C4b,C4c,C4d）。⇒ 4 个覆盖漏洞在冻结树上**依然存在**（dev-coder 未在冻结前补强值断言/场景）；已按纪律记入 `docs/_review-0.7.48.md §3.3` 与 0.7.48 已知限制。

## 5. 5.2.3 “自报 vs 实测”两列模板

| 用例 | 作者自报杀数（claim） | 实测杀数（measured，冻结树） | 一致（Y/N） | 备注 |
|---|---|---|---|---|
| C1_drop_reached_arg | 未单独自报（作者只报 4/4 定向单测 OK） | **KILL**（冻结树 `e2b69d9`） | — | probe FAIL + 单测 KILL |
| C2_reached_always_true | 同上 | **KILL** | — | 单测 KILL（assertIs False） |
| C2b_main_reached_true | 同上 | **SURVIVE** | — | **覆盖漏洞（冻结树仍 SURVIVE）** |
| C3a_drop_reached_other_site_pressure | 同上 | **KILL** | — | KILL |
| C3b_drop_reached_other_site_buy_full | 同上 | **KILL** | — | KILL |
| C4a_demand_basis_buy_full_changed | 同上 | **KILL** | — | KILL（值断言） |
| C4b_demand_basis_clear_gate_changed | 同上 | **SURVIVE** | — | **覆盖漏洞（缺值断言）** |
| C4c_demand_basis_main_changed | 同上 | **SURVIVE** | — | **覆盖漏洞（缺值断言）** |
| C4d_demand_basis_pressure_changed | 同上 | **SURVIVE** | — | **覆盖漏洞（缺值断言）** |
| C5_target_free_value_wrong | 同上 | **KILL** | — | KILL（值断言） |
| C6_reached_int_zero | 同上 | **KILL** | — | KILL（assertIs False） |

> 原则：**作者自报的杀数不算证据**。以上“实测杀数”必须能在 `git archive` 导出的**冻结树**上**原封不动**复跑出来，并把完整输出原文附入验收报告。

## 6. 结论与待办（0.7.48 冻结后待跑项）

**待办（冻结后立即执行）：**
1. 确定 `FROZEN_REF`（0.7.48 freeze commit）
2. 运行 `scratch/_t5_prov.py prov <FROZEN_REF> --tests`，记录文件数、关键 blob SHA256、全量单测 `Ran/OK`（双跑自洽）
3. 运行 `scratch/_t38_mutate.py --ref <FROZEN_REF>`，将结果写入 `scratch/_t38_mutate_out_freeze_<FROZEN_REF>.txt`，填充 §5 表格的“实测杀数”列
4. 对照 §4.3 洞清单：如 C2b/C4b/C4c/C4d 在冻结树仍 **SURVIVE**，在验收报告中**如实列为“定向单测覆盖漏洞”**（不得改结论掩盖）
5. 按 deputy-lead 报告格式（含 文件:行号 + 命令原文 + 读数）将上述证据整理进 `docs/_review-0.7.48.md`（正式增量验收）

**备注（本骨架结论）：**修前测量显示 C1/C2/C3a/C3b/C4a/C5/C6 **可被现有定向单测判红**；C2b、C4b、C4c、C4d **当前未被判红（测试覆盖漏洞）**。本文件仅为预置骨架，不对冻结树做结论性判定。

> **【2026-10-19 收尾补录】** 上述待办 1–5 **已全部执行**：`FROZEN_REF=e2b69d9`（前置 `d9f7032`）；provenance 双跑（791 文件 / `Ran 1378`，两跑同）；变异实测（KILL 7 / SURVIVE 4，与修前一致）；正式结论见 **`docs/_review-0.7.48.md`**（含「**A9 可否放行：放行**」一行）。本骨架 §3/§4.4/§5 的「待跑」表述由该报告取代。

## 7. 附件

- `scratch/_t38_mutate.py` —— 变异跑器（A. AST 探针口径 + B. 定向单测口径）
- `scratch/_t38_mutate_out.txt` —— **修前实测输出原文**（当前工作树）
- `scratch/_t5_prov.py` —— `git archive` 冻结树 provenance（compare-journals / prov 子命令）
- `scratch/_t5_cmp_out.txt`、`scratch/_t5_journals.json` —— 六本旧账本 rc/红数前后对比（证明改动不影响既有账本结论）
- `scratch/_t5_smoke_analyze.json`、`scratch/_t5_smoke_verify.txt` —— smoke-0746 analyze/verify 重现证据

> **纪律提醒（AGENTS.md §4）：**判据一律用独立观测差分；缺失 ≠ 通过；变异必须实测（作者自报杀数不算证据）；骨架/探针自己的 bug 与产品 bug 分开判；沙箱限制不许当理由。