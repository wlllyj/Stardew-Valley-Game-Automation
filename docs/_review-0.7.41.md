# 0.7.41 批次（task-236 / task-237 / task-238）独立对抗验收

> 状态：**草稿（worktree 线索）**。正式判定必须等 Lead 发 0.7.41 冻结 hash，届时用
> `git archive <hash>` 冻结树重跑 A/B/B6/C/D/E 并在本文件 §10 记录 provenance 与最终结论。
> 判定人：deputy-lead（只读生产代码；只写 `docs/_review-*.md` + `scratch/`）。

## §0 一句话结论（草稿，待冻结树）

- **task-236**：PASS-WITH-NITS（收尾清模态 + SMAPI 日切落盘判据；B-6 检查器终审 10/10 PASS，
  两条保守性 GAP 已被 Lead 修复并复验关闭）。
- **task-237**：PASS（需求驱动腾格；作者 4 条变异自报 2/2/1/1，我独立复跑逐条一致）。
- **task-238**：**未交付**（worktree marker `finalize_fallback`=false）⇒ 无法判定。
- ⇒ **0.7.41 暂不可据此冻结放行 A″/B″**；等 238 交付（Lead 亲核后再冻结）+ 冻结 hash 重跑正式判定。

## §1 对象、读数与 provenance（worktree，线索）

| 项 | 值 |
|---|---|
| HEAD | 见 `git log -1 --oneline`（验收期内工作树含 dev-coder 在制，正式判定用冻结树） |
| 236 提交 | `bbf7b4a`（5 文件：`longrun.py` / `test_longrun.py` / `verify-run3.py` / `test_verify_run3.py` / `scratch/_t236_mutate.py`） |
| 237 提交 | `a60d53b`（`farmwork.py` / `longrun.py` / 测试 / `scratch/_t237_mutate.py`） |
| 检查器/冒烟骨架 | `744d993`（`scratch/save-chain-check.py` + `scratch/smoke-0741.py`），后续 `e615416` 修 GAP-236B-4/5 |
| 版本 | `manifest.json`=0.7.40 / `bridge.py:39 MOD_VERSION_EXPECTED`=0.7.40（未 bump，符合"冻结提交才 bump"） |
| marker | 236=True 237=True **238=False** |
| 读数（worktree） | `py_compile -W error::SyntaxWarning` **rc=0**；定向 `tests.test_farmwork tests.test_longrun tests.test_planner` **Ran 726 / OK**；全量 `discover -s tests` **Ran 1199 / OK（0 红）**；`dotnet build --no-incremental` **0 警 0 错**；C# 自检 **`OK 85 断言全部通过`** |

> 读数脚本：`python scratch/_t239_probe.py --only A --readings`（原始输出 `scratch/_t239_probe_worktree.txt`）。

## §2 A 段：范围 / 越界 / 未 bump（冻结树待办）

- A1 对象文件齐全 ✅；A2 逐文件 SHA16 已记（`scratch/_t239_probe_worktree.txt` 的 INFO 行）。
- A3 **checks 键集未被 236/237 扩键** ✅（`rep.checks = {...}` 块 2473 字符，无 `cleanup*`/`harvest_demand`）。
- A4 版本仍 0.7.40（未 bump）✅（冻结提交自己会只改 `manifest.json` + `bridge.py` 版本行，届时重核）。
- A5 marker：236/237 真、238 假。
- **provenance 待冻结树补**：`git hash-object` 我的快照 vs `git rev-parse <hash>:<path>` 逐文件对照，
  并写进 §10。

## §3 B 段：真机读数离线复算（task-236）

真机形态（0.7.40 七步冒烟，窗口 12:08:39–12:20:43，3309 行；抢救后 3333 行）：

| 计数 | NewDay | before save | Save called | completed | after save |
|---|---|---|---|---|---|
| 抢救前（跑尾声） | **3**（L1209/2308/**3304**） | 2（L1219/2325） | **2**（L1220/2326） | 2 | 2 |
| 抢救后窗口 | 3 | 3 | 3（原始 4，L16 插件描述行 1 条） | 3 | 3 |

- 根因：第 3 次跨日后进程退出，`ShippingMenu`（前一天有出货 ⇒ 保存推迟）没人关 ⇒ 该次 NewDay 的存档从未开始；
  抢救（12:23:51 一次 dismiss）后补齐 5 行保存链，主档 4464675/12:18:23 → 3104089/12:23:54。
- **参考判据**（我方独立实现 `count_six/judge_smapi`，只验夹具方向）：真形态判红
  （`NewDay=3 > Save called=2`）；绿窗口不判红。
- **产品判据**：`verify-run3.py --smapi` 对真形态判红（`日切落盘链不完整` + `日切顺序颠倒` 3304/2326），
  对抢救后绿窗口无 problem。checker 输出 `counts`/`raw_counts` 与我的复算逐字一致。

### §3.1 B-6：`scratch/save-chain-check.py` 终审（10/10 PASS）

| # | 检查 | 结果 |
|---|---|---|
| B6-1 | `--selftest` 8 夹具 | rc=0，`SELFTEST PASS` |
| B6-2 | 真实绿窗口 | rc=0 / PASS / counts 3/3/3/3/3 |
| B6-3 | 真实红窗口 | rc=1 / FAIL / `末次 NewDay 行号 3304 晚于最后一次 Save called 行号 2326` |
| B6-4 | 0.7.40 型红窗口 | 仍 FAIL rc=1（未被完整性闸门吃掉） |
| B6-5 | GAP-236B-4 已闭 | 缺 `before save` ⇒ **rc=2 无法判定**（缺失≠通过） |
| B6-6 | GAP-236B-5 已闭 | 缺 task 链但顺序正常 ⇒ PASS + `checked_without_task=true` |
| B6-7 | 同上 | 缺 task 链 + 链内逆序 ⇒ FAIL 带行号 |
| B6-8 | save_task 完整 | `use_task_chain=true`、非 without_task |
| B6-9 | save_task 部分缺失（2<3） | rc=2 无法判定 |
| B6-10 | 消费端 `smoke-0741.py::step6` | 只读 `payload["verdict"]/counts`，不自己数六串 ✅ |

- NIT（非阻塞）：`count_six()`（检查器 :475 一带）定义仍在但全文件无调用 = 死代码，machine-runner 顺手清。
- 结论：**检查器可作步 6 唯一判据来源**（与 Lead 终审结论一致）。

## §4 C 段：作弊通道（worktree 读数 16 PASS / 0 FAIL / 2 SKIP / 3 INFO）

| 通道 | 判据与构造 | 结果 |
|---|---|---|
| C1 不关框就退出 | 真形态（含 L16 插件行）⇒ 参考判据 + 产品判据都必须判红 | PASS |
| C2 关框后立刻退出（保存链半截） | 去掉末次 completed/after save ⇒ 两种判据都判红 | PASS |
| C3 Mod 兜底 | `ModalDismiss.cs` 对 `ShippingMenu`/存档菜单 `wait_only` 拒绝 | PASS |
| C4 手写 demand | `HARVEST_DEMAND_CAP=12` + clamp 存在；`_harvest_demand` 读可收格数 | PASS |
| C5/C6 238 兜底 | 空 reasons 不许一律填 `unknown_evidence`；兜底不许改 `executed_steps` | **SKIP（238 未交付）** |
| C7 伪造 after save | 只补 after save 行不得洗绿 | PASS |
| **C8（我自想）收尾清理不可逆模态** | ①源码静态：eventUp/LevelUpMenu/professionsToChoose/MODAL_WAIT_ONLY/cleanup_skipped 全在；②动态假世界：职业弹窗挂着 ⇒ `skipped=profession_pending`、dismiss **0**；③`eventUp=true` ⇒ `skipped=event_up`、dismiss **0**；④存档菜单 ⇒ **只等不关**（dismiss 0、未 stuck）；⑤`_finish` 真调用并进 summary/journal | PASS ×5 |
| **C9（我自想）237 字段自洽** | `_slot_relief` 记 `harvest_demand`/`target_free`/`reached` 且 demand 来自引擎 | PASS |
| **C10（我自想）工具不看 cleanup 自述** | `cleanup_modal_stuck=true` + `code=0` 的矛盾账本，verify-run3/analyzer 都不判 ⇒ 记 **GAP-236-6（防御性、不阻塞，SMAPI 六串兜住）** | INFO |

> C8 是"作者单测 + 我方动态探针"的**双覆盖**（Lead 认可算我的验收点）；若动态探针不通过即为真发现。

## §5 D 段：变异矩阵（自报 vs 实测）

作者脚本可复跑（自包含，`PYTHONUTF8=1`；原始输出 `scratch/_t239_author_t236.txt` / `_t237.txt`）：

| 卡 | 变异 | 自报 | 我方实测 |
|---|---|---|---|
| 236 | m236a 去掉 `_finish` 清理调用 | 1 | **1** |
| 236 | m236b 插件描述行当判据 | 1 | **1** |
| 236 | m236c 去掉顺序判据 | 1 | **1** |
| 236 | m236d 收尾关职业选择弹窗 | 1 | **1** |
| 237 | m237a target 退回 reserve+1 | 2 | **2** |
| 237 | m237b demand cap 改 3 | 2 | **2** |
| 237 | m237c 忽略 prefer_qids | 1 | **1** |
| 237 | m237d 消费轮次不写来源 | 1 | **1** |

**自报 vs 实测 100% 一致（4 条 / 6 条）**。我方另建 5 条变异（`scratch/_t239_mutate.py`，
锚点 `--check-anchors` 0 坏；control 0 杀）：m236a_no_cleanup_call / m236b_no_event_guard /
m236c_no_profession_guard / m236d_wait_only_dismiss / m237a_no_demand_clamp，**各杀 1（5/5 全杀）**。
238 的变异待其交付后补。

## §6 E 段：逐卡判定（草稿）

- **task-236 = PASS-WITH-NITS**：cleanup 守卫 4 条不可逆模态规则逐条实证；SMAPI 六串/L16/顺序判据三处
  都经"检查器终审 + verify-run3 实测"双证；NIT-1 `count_six` 死代码；NIT-2 `cleanup` 卡住不上抬
  `finish.code`（design、SMAPI 兜底）。
- **task-237 = PASS**：demand 来自可收格数并 clamp 12；作者 4 条变异复跑一致；C9 字段自洽。
- **task-238 = 待判**（未交付）。
- **0.7.41 可否冻结放行 A″/B″**：**暂不可**（238 缺失）；238 交付且冻结树重跑无红后给最终结论。

## §7 已知 NIT / GAP

| # | 类型 | 内容 | 阻塞? |
|---|---|---|---|
| NIT-1 | 死代码 | 检查器 `count_six()` 无调用 | 否 |
| NIT-2 | design | `cleanup` 卡住只运行级记账、不上抬 finish.code（SMAPI 六串为权威） | 否 |
| GAP-236-6 | 防御性 | 工具不判 `cleanup_modal_stuck=true × code=0` 矛盾账本（需手改账本；底层落盘由六串兜住） | 否 |
| GAP-236-7 | design | 同 NIT-2（分栏记录） | 否 |
| NIT-3 | 流程 | 我方探针曾被一次性补丁脚本 `write_text(newline="\\n")` 截断为 0 B（`open('w')` 先截断后异常）⇒ 已重建并提交 `aceafa3`；教训：改探针只用编辑工具/整文件重写 | 否 |

## §8 复跑命令（冻结树就绪后照抄）

```powershell
$py = 'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$env:PYTHONUTF8 = '1'
git archive --format=tar -o "$env:TEMP\t239.tar" <冻结hash>; tar -xf "$env:TEMP\t239.tar" -C "$env:TEMP\t239_frozen"
& $py scratch\_t239_probe.py --tree "$env:TEMP\t239_frozen" --only A,B,B6,C,D,E --readings
& $py scratch\_t239_mutate.py --base "$env:TEMP\t239_frozen" --check-anchors
& $py scratch\_t239_mutate.py --base "$env:TEMP\t239_frozen" --all
# 作者变异（在冻结树根跑）：
& $py scratch\_t236_mutate.py ; & $py scratch\_t237_mutate.py ; & $py scratch\_t238_mutate.py
```

## §9 边界

- 只读生产代码；只写 `docs/_review-*.md` + `scratch/`；不碰游戏/桥、不 deploy、不 bump、不改板面。
- worktree 上的读数只作线索；正式判定一律以 `git archive` 冻结树为准，并记 provenance。
- 本文件在冻结树判定后补 §10（provenance + 最终读数 + 一句话结论）。

## §10 冻结树 provenance 与最终判定（待补）

（冻结 hash：____；文件 SHA16 对照：____；最终读数：____；结论：____）
