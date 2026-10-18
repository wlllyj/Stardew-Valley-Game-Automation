# 0.7.41 批次（task-236 / task-237 / task-238）独立对抗验收

> 状态：**正式判定（冻结树 `7e6bf55`）**。判定人：deputy-lead（只读生产代码；只写 `docs/_review-*.md` + `scratch/`）。
> 验收对象用 `git archive 7e6bf55` 冻结树（`%TEMP%\t239_frozen`，775 文件，含从真仓库拷入的 `logs/` 夹具 115 个），
> provenance 见 §10（8/8 blob 与冻结提交逐字节一致）。

## §0 一句话结论

- **task-236**：PASS-WITH-NITS（收尾清模态 + SMAPI 日切落盘判据；B-6 检查器终审 10/10 PASS）。
- **task-237**：PASS（需求驱动腾格；作者 4 条变异实测 2/2/1/1，与自报逐条一致）。
- **task-238**：PASS（日终兜底回填闭合原因码；映射表 10 例全对、只补 0 步空原因记录、不动 `executed_steps`/`checks`/`verified`；作者 2 条变异实测 3/2 与自报一致；我补 C5a–C5f 六条通道全 PASS）。
- ⇒ **0.7.41 可据此冻结，并放行 A″/B″**（无阻塞必修；NIT/GAP 见 §7，均为防御性或设计取舍）。

## §1 对象、读数与 provenance

| 项 | 值 |
|---|---|
| 冻结提交 | **`7e6bf55`** "chore(release): 冻结 0.7.41（落盘守卫 + 腾格力度 + §8 兜底）"，父 `a5de06f` |
| 冻结提交内容 | `git diff --numstat 7e6bf55^ 7e6bf55` = `brain/agentfarm/bridge.py` 18/1（版本常量 + 变更说明注释）、`mod/AgentFarm.Bridge/manifest.json` 2/2（Version+Description）、`tools/_note-0741.txt` 9/0 ⇒ **只 bump 版本 + 说明，无源码改动** |
| 236 提交 | `bbf7b4a`（5 文件：`longrun.py` / `test_longrun.py` / `verify-run3.py` / `test_verify_run3.py` / `scratch/_t236_mutate.py`） |
| 237 提交 | `a60d53b`（`farmwork.py` / `longrun.py` / 测试 / `scratch/_t237_mutate.py`） |
| 238 提交 | `056b585`（4 文件 +219/−0：`longrun.py` +37 / `docs/_run10-criteria.md` +2 / `scratch/_t238_finalize_mutate.py` +79 / `tests/test_longrun.py` +101） |
| 检查器/冒烟骨架 | `744d993`（`scratch/save-chain-check.py` + `scratch/smoke-0741.py`），GAP-236B-4/5 由 `e615416` 修 |
| 版本 | `manifest.json`=**0.7.41** / `bridge.py:39 MOD_VERSION_EXPECTED`=**0.7.41** |
| marker（冻结树） | 236=True 237=True 238=True |
| 读数（冻结树亲跑） | `py_compile -W error::SyntaxWarning` **rc=0**（`-W` 在 `-m` 之前）；定向 `tests.test_farmwork tests.test_longrun tests.test_planner` **Ran 726 / OK**；全量 `discover -s tests` **Ran 1199 / OK（0 红）**；`dotnet build --no-incremental` **0 警 0 错**；C# 自检 **`OK 85 断言全部通过`** |

SHA16（冻结树，provenance 见 §10）：`longrun A728888FEF02ED17` / `farmwork 7DA3D549E2379820` /
`planner A6033FB8C3CCD2A5` / `bridge 6AED9E257E0DD697` / `verify-run3 2D9DB563C382943E` /
`test_verify_run3 40B493EF6601BFBE` / `test_longrun 6D07F73E08406EB6` / `ModalDismiss 571B77E4D5DAF33C`。

## §2 A 段：范围 / 越界 / 版本

- A1 8 个对象文件齐全 ✅；A3 **checks 键集未被三卡扩键** ✅（`rep.checks` 块 2473 字符，无 `cleanup*`/`harvest_demand`）。
- A4 版本 0.7.41（`bridge.py` 与 `manifest.json` 一致）✅；A5 marker 236/237/238 **全 True** ✅。
- 冻结提交未混入源码改动（见 §1 numstat）✅。

## §3 B 段：真机读数离线复算（task-236）

真机形态（0.7.40 七步冒烟，窗口 12:08:39–12:20:43，3309 行；抢救后 3333 行）：

| 计数 | NewDay | before save | Save called | completed | after save |
|---|---|---|---|---|---|
| 抢救前（跑尾声） | **3**（L1209/2308/**3304**） | 2（L1219/2325） | **2**（L1220/2326） | 2 | 2 |
| 抢救后窗口 | 3 | 3 | 3（原始 4，L16 插件描述行 1 条） | 3 | 3 |

- 根因：第 3 次跨日后进程退出，`ShippingMenu`（前一天有出货 ⇒ 保存推迟）没人关 ⇒ 该次 NewDay 的存档从未开始；
  抢救（12:23:51 一次 dismiss）后补齐 5 行保存链，主档 4464675/12:18:23 → 3104089/12:23:54。
- **B1–B5 全 PASS**：参考判据真形态判红（`NewDay=3 > Save called=2`）；`verify-run3 --smapi` 对真形态判 problem、
  对抢救后绿窗口无 problem；绿窗口 PASS 且 L16 只进原始计数（raw=4 corrected=3 excluded=1）。

### §3.1 B-6：`scratch/save-chain-check.py` 终审（冻结树 10/10 PASS）

| # | 检查 | 结果 |
|---|---|---|
| B6-1 | `--selftest` 8 夹具 | rc=0，`SELFTEST PASS` |
| B6-2 | 真实绿窗口 | rc=0 / PASS / counts 3/3/3/3/3（raw save_called=4） |
| B6-3 | 真实红窗口 | rc=1 / FAIL / `末次 NewDay 行号 3304 晚于最后一次 Save called 行号 2326` |
| B6-4 | 0.7.40 型红窗口 | 仍 FAIL rc=1（未被完整性闸门吃掉） |
| B6-5 | GAP-236B-4 已闭 | 缺 `before save` ⇒ **rc=2 无法判定**（缺失≠通过） |
| B6-6 | GAP-236B-5 已闭 | 缺 task 链但顺序正常 ⇒ PASS + `checked_without_task=true` |
| B6-7 | 同上 | 缺 task 链 + 链内逆序 ⇒ FAIL 带行号 |
| B6-8 | save_task 完整 | `use_task_chain=true`、非 without_task |
| B6-9 | save_task 部分缺失（2<3） | rc=2 无法判定 |
| B6-10 | 消费端 `smoke-0741.py::step6` | 只读 `payload["verdict"]/counts`，不自己数六串 ✅ |

- 结论：**检查器可作步 6 唯一判据来源**（与 Lead 终审一致）。NIT：`count_six()` 死代码（§7 NIT-1）。

## §4 C 段：作弊通道（冻结树 23 PASS / 0 FAIL / 0 SKIP / 3 INFO）

| 通道 | 判据与构造 | 结果 |
|---|---|---|
| C1 不关框就退出 | 真形态（含 L16 插件行）⇒ 参考判据 + 产品判据都判红 | PASS |
| C2 关框后立刻退出（保存链半截） | 去掉末次 completed/after save ⇒ 两种判据都判红 | PASS |
| C3 Mod 兜底 | `ModalDismiss.cs` 对 `ShippingMenu`/存档菜单 `wait_only` 拒绝 | PASS（C3b） |
| C4 手写 demand | `HARVEST_DEMAND_CAP=12` + clamp 存在；`_harvest_demand` 读可收格数 | PASS ×3 |
| **C5 238 兜底（我补）** | C5a 映射表 10 例全对（inventory_blocked→no_slot / modal / event / stuck* / bridge_down·sleep_failed→world_stuck / 夜与体力→gated / 未知→unknown_evidence）；C5b 只补「0 步且空原因」；C5c 回填码 ∈ 闭合集 + `evidence.why="finalize_fallback"`；C5d 不改 `executed_steps`/`checks`/`verified`；C5e `reasons_are_intent_level` 按 `requested_tiles==0` 推导；C5f 码 ∈ 12 码闭合集 | PASS ×6 |
| C6 兜底不许改步数 | 兜底代码块内无 `executed_steps` 写入 | PASS |
| C7 伪造 after save | 只补 after save 行不得洗绿 | PASS |
| **C8（我自想）收尾清理不可逆模态** | ①源码静态：eventUp/LevelUpMenu/professionsToChoose/MODAL_WAIT_ONLY/cleanup_skipped 全在；②职业弹窗 ⇒ `skipped=profession_pending`、dismiss **0**；③`eventUp=true` ⇒ `skipped=event_up`、dismiss **0**；④存档菜单 ⇒ **只等不关**（dismiss 0、未 stuck）；⑤`_finish` 真调用并进 summary/journal | PASS ×5 |
| **C9（我自想）237 字段自洽** | `_slot_relief` 记 `harvest_demand`/`target_free`/`reached` 且 demand 来自引擎 | PASS |
| **C10（我自想）工具不看 cleanup 自述** | `cleanup_modal_stuck=true` + `code=0` 的矛盾账本，verify-run3/analyzer 都不判 ⇒ **GAP-236-6（防御性、不阻塞，SMAPI 六串兜住）** | INFO |
| C3a/C3c | 同上（GAP-236-6/7 防御性 + 脑侧只运行级记账） | INFO |

> C5 是我在 238 落地后补的通道（probe 改动随本报告一并入库）；C8 是"作者单测 + 我方动态探针"双覆盖（Lead 认可算我的验收点）。

## §5 D 段：变异矩阵（自报 vs 实测，冻结树复跑）

作者脚本自包含、在冻结树根直接复跑（`PYTHONUTF8=1`；原始输出
`scratch/_t239_author_t236_frozen.txt` / `_t237_frozen.txt` / `_t238_frozen.txt`）：

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
| 238 | m238a 关回填 | 3 | **3** |
| 238 | m238b 一律 unknown_evidence | 2 | **2** |

**自报 vs 实测 100% 一致（236=4 / 237=6 / 238=5）**。我方另建 5 条变异（`scratch/_t239_mutate.py`，
锚点 `--check-anchors` 0 坏；control 0 杀）：m236a_no_cleanup_call / m236b_no_event_guard /
m236c_no_profession_guard / m236d_wait_only_dismiss / m237a_no_demand_clamp，**各杀 1（5/5 全杀）**
（输出 `scratch/_t239_mut_frozen.txt`）。

## §6 E 段：逐卡判定

- **task-236 = PASS-WITH-NITS**：cleanup 守卫 4 条不可逆模态规则逐条实证；SMAPI 六串/L16/顺序判据三处
  都经"检查器终审 + verify-run3 实测"双证；NIT-1 `count_six` 死代码；NIT-2 `cleanup` 卡住不上抬
  `finish.code`（design、SMAPI 兜底）。
- **task-237 = PASS**：demand 来自可收格数并 clamp 12；作者 4 条变异实测 2/2/1/1 一致；C9 字段自洽。
- **task-238 = PASS**：兜底只补原因码、不动步数与判定；映射表 10 例全对；C5a–C5f + C6 全 PASS；
  作者 2 条变异实测 3/2 一致；全量 1199 OK（0 红）。
- **0.7.41 可否冻结并放行 A″/B″**：**可以**（无阻塞必修项；NIT/GAP 均防御性/设计取舍）。

## §7 已知 NIT / GAP

| # | 类型 | 内容 | 阻塞? |
|---|---|---|---|
| NIT-1 | 死代码 | 检查器 `count_six()` 无调用 | 否 |
| NIT-2 | design | `cleanup` 卡住只运行级记账、不上抬 finish.code（SMAPI 六串为权威） | 否 |
| GAP-236-6 | 防御性 | 工具不判 `cleanup_modal_stuck=true × code=0` 矛盾账本（需手改账本；底层落盘由六串兜住） | 否 |
| GAP-236-7 | design | 同 NIT-2（分栏记录） | 否 |
| NIT-3 | 流程 | 我方探针曾被一次性补丁脚本 `write_text(newline="\\n")` 截断为 0 B（`open('w')` 先截断后异常）⇒ 已重建并提交；教训：改探针只用编辑工具/整文件重写 | 否 |
| NIT-4 | 流程 | 238 落地前 C5/C6 是 SKIP；238 交付后我补了 C5a–C5f（本报告与探针同批提交） | 否 |

## §8 复跑命令（冻结树）

```powershell
$py = 'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$env:PYTHONUTF8 = '1'
git archive --format=tar -o "$env:TEMP\t239.tar" 7e6bf55
New-Item -ItemType Directory -Force "$env:TEMP\t239_frozen" | Out-Null
tar -xf "$env:TEMP\t239.tar" -C "$env:TEMP\t239_frozen"
# 探针（夹具从真仓库 logs/ 派生，无需拷进树）
& $py scratch\_t239_probe.py --tree "$env:TEMP\t239_frozen" --only A,B,B6,C,D,E --readings
# 我方变异
& $py scratch\_t239_mutate.py --base "$env:TEMP\t239_frozen" --check-anchors
& $py scratch\_t239_mutate.py --base "$env:TEMP\t239_frozen" --all
# 作者变异（在冻结树根跑）
Push-Location "$env:TEMP\t239_frozen"
& $py scratch\_t236_mutate.py ; & $py scratch\_t237_mutate.py ; & $py scratch\_t238_finalize_mutate.py
Pop-Location
```

## §9 边界

- 只读生产代码；只写 `docs/_review-*.md` + `scratch/`；不碰游戏/桥、不 deploy、不 bump、不改板面。
- worktree 读数只作线索；正式判定一律以 `git archive` 冻结树为准，并记 provenance（§10）。
- 未提交任何生产代码；工作树只留 `scratch/` 产物。

## §10 冻结树 provenance 与最终判定

| 文件 | 冻结树 blob | `git rev-parse 7e6bf55:<path>` | 一致? |
|---|---|---|---|
| `brain/agentfarm/longrun.py` | `ef78d94ffb07…` | `ef78d94ffb07…` | ✅ |
| `brain/agentfarm/farmwork.py` | `d6c3ea2d6467…` | `d6c3ea2d6467…` | ✅ |
| `brain/agentfarm/planner.py` | `6da5317b1fe3…` | `6da5317b1fe3…` | ✅ |
| `brain/agentfarm/bridge.py` | `c042d059136a…` | `c042d059136a…` | ✅ |
| `tools/verify-run3.py` | `bc21ae2e87fe…` | `bc21ae2e87fe…` | ✅ |
| `scratch/save-chain-check.py` | `6511a5f276bc…` | `6511a5f276bc…` | ✅ |
| `mod/AgentFarm.Bridge/ModalDismiss.cs` | `6090cc4cca5b…` | `6090cc4cca5b…` | ✅ |
| `tests/test_longrun.py` | `ba8db705ba61…` | `ba8db705ba61…` | ✅ |

- 探针冻结树正式读数：**PASS=45 / FAIL=0 / SKIP=2（D3 变异两列、E1 结论——本文件已填）/ INFO=17**
  （`scratch/_t239_formal_frozen.txt`）；C 段单跑 **23 PASS / 0 FAIL / 0 SKIP / 3 INFO**。
- 最终判定：**PASS-WITH-NITS；0.7.41 可据此冻结并放行 A″/B″。**
