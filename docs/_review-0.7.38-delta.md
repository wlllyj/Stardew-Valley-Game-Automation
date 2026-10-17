# 0.7.38 delta 独立复核（F3 修复 + 通道⑤ + GAP-1/GAP-2）

- 验收人：deputy-lead（只读生产码 / 只写 `docs/` 与 `scratch/`；未碰游戏、桥、任务板）
- 对象：**`git archive 2ca6dc8`（0.7.38 冻结件）** → 冻结树 `scratch/_t238`（570 文件 + 夹具 99）
- 对照树：`scratch/_t200_frozen` = `063351d`（0.7.37 冻结：含 task-205、无 task-216 修复）
- 卡面：Lead m09084（task-216 = `fd1b88d`；0.7.38 冻结 `2ca6dc8`）

## §1 指纹与范围

| 文件 | 归档树 SHA256(12) | Lead 给的 | 判定 |
|---|---|---|---|
| `brain/agentfarm/longrun.py` | `AAFD0CC1C93B` | `AAFD0CC1…` | ✅ |
| `brain/agentfarm/farmwork.py` | `B0C719E23D4D` | `B0C719E2…` | ✅ |
| `brain/agentfarm/bridge.py` | `BBAE61454E80` | `BBAE6145…` | ✅ |
| `mod/AgentFarm.Bridge/manifest.json` | `47EA061229B9` | `63B7D82C…` | ⚠ 口径差 |
| `…/bin/Release/AgentFarm.Bridge.dll` | 不在归档（`bin/` gitignored） | `16FA5D16…` | 未核 |

- manifest 口径差已定位：**工作树版本 SHA256 = `63B7D82C944D`（= Lead 值）**，归档版本 = `47EA061229B9`
  ⇒ 差异只是 **CRLF(工作树) / LF(git archive)**，内容同一，不是问题。
- dll 未在归档、也未在我可读的装机路径找到 ⇒ 记「未核」，不写成「通过」。
- 冻结提交 `2ca6dc8`：`bridge.py` +14/−1、`manifest.json` +2/−2、`tools/_note-0738.txt` +7；其父 `fd1b88d` = task-216 本体。
- 版本：`manifest "Version": "0.7.38"`、`MOD_VERSION_EXPECTED = "0.7.38"`。
- 批次读数（我亲跑）：`py_compile -W error::SyntaxWarning` **exit 0**；定向（farmwork+longrun+planner）**OK**；
  全量 `PYTHONUTF8=1 discover -s tests` **Ran 1055 / OK（0 红）**；`dotnet build --no-incremental` **0 警 0 错**；
  C# 自检 **`OK 76 断言全部通过`**（0.7.37 为 60，新增 `t216_longtask_is_subset_of_executable` 等）。

## §2 四项逐条判定与证据锚点

### §2.1 F3 delta（取回不被"紧急农活"挡死）—— **通过**

冻结树代码（`brain/agentfarm/longrun.py`）：
- `_tool_upgrade_due`（`:4656-4682`）：`if action == "pickup": return True   # 【F3】取回一律放行`（`:4680-4681`）；
  `upgrade` 才走 `return not self._urgent_farm_work(obs, self._tool_suspended_stages(obs))`（`:4682`）。
- `_urgent_farm_work`（`:4636-4654`）：`if "water_area" not in suspended:` 才算"未浇活苗"（修法②：排除被暂停阶段）。
- `_maybe_tool_upgrade`（`:4575-4616`）+ 主循环 `:6429` **无条件调用**（注释写明 `due=False` 也留痕）。

我的主循环级探针 `scratch/_t238_probe.py`（`make_run` + `FakeClient`/`FakeWorker` + `run.run()`）：

| 用例 | pre 树（0.7.37 `063351d`） | post 树（0.7.38 `2ca6dc8`） |
|---|---|---|
| P1 壶在途 days=0 + 2 格未浇活苗 | `pickup_calls=0`、`ended_by=slept_without_work`、reason `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：field_nw还有地要清/开/种）` | `pickup_calls=1`、`pickup_tool{ok}`、`ended_by=sleep`（非 stuck）、`verified=True` |
| P4 钱/材料够 + 有未浇活苗 | 无 skipped 留痕、`upgrade_idx=8` | `skipped_idx=3`（"先干紧急农活：有 1 格作物没浇水"）在 `upgrade_idx=9` 之前 |

主循环级用例（作者）：`tests/test_longrun.py:10422 test_a_day_with_the_can_in_clint_goes_and_picks_it_up`
（`make_run(w, target_days=1, max_days=1)` → `run.run()` → `assertEqual(w.pickup_calls, 1)`、
`assertNotIn("stuck", str(days[0].ended_by))`）⇒ **不是直调函数，满足 Lead 要求**。

### §2.2 通道⑤（`due=False` 的等待日必须留痕）—— **通过（含 1 条 NIT）**

| 用例（主循环级） | pre 树 | post 树 |
|---|---|---|
| P2 axe 在途 days=2（wait） | `tool_upgrade_skipped` **0 条** | 恰 **1 条**，`which="wait"`，`reason="wait：还在升级：daysLeft=2"` |
| P3 背包 12/12 + axe 在途 days=0（need_slot，当天有活） | **0 条** | 恰 **1 条**，`which="need_slot"`，且 `pickup_calls=0`（没有空格 ⇒ 一步不发） |

- **NIT（不阻塞）**：纯"无活"日（`sleep_guard=no_work` 在 `longrun.py:6401` 早退睡掉，到不了 `:6429`）
  仍然一条 skipped 都没有（P3e 实测 = 0）。留痕只覆盖"当天还有活"的日；建议 0.7.39 把留痕点前移
  或早退前补一条（不影响 F3 与本次放行）。

### §2.3 GAP-2（`ToolUpgradeRules.Select` 的 tier/唯一性有行为断言）—— **已闭**

- 断言在库（`mod/AgentFarm.Bridge.Tests/Program.cs`）：`t205_unique_offer_is_selected`（:191）、
  `t205_wrong_tier_fails_closed`（:196）、`t205_duplicate_offers_fail_closed`（:203）、`t205_kind_normalization`（:299）；
  且 0.7.38 新增 `t216_tier_must_be_exactly_plus_one`、`t216_exact_tier_wins_among_several`。
- 我的变异 `m238c_tier_not_enforced`（`if (offers[i].Tier != tierBefore + 1) continue;` → `if (false) continue;`）
  实测 **杀 3**（含上面两条 t216 断言）⇒ 自检真能杀 tier 判据回归（上次 `>=` 0 杀的问题已消失）。

### §2.4 GAP-1（task-205 的变异定义/脚本）—— **已闭**

- `scratch/_t205_mutate.py` 已在库：含 `m205a`–`m205d` 定义、字节级备份/还原、跑完校验四处文件与备份一致。
- 说明：该脚本会**就地**改工作树再还原；我未运行它（只读纪律），改用自建 `scratch/_t200_mutate.py`
  在冻结树副本上跑等价变异（见 §3）。

## §3 变异「自报 vs 实测」两列

base = `scratch/_t238`（0.7.38 冻结树；全量基线 **0 红**）；锚点校验 30 条、坏 0。

### §3.1 task-216（本卡，自建）

| 变异 | 自报 | 实测 | 判定 |
|---|---|---|---|
| m238a 去掉 `pickup` 一律放行 | 卡面未给（我建的） | **1**（`test_pickup_outranks_other_urgent_work`） | 通道灵敏 |
| m238b 去掉 `due=False` 留痕块 | 卡面未给（我建的） | **3**（`wait` / `need_slot` / `new_upgrade_still_yields`） | 通道灵敏 |
| m238c `Select` tier 判据失效 | 卡面未给（我建的） | **3**（C# 自检） | GAP-2 闭合 |
| m238d 紧急农活不再排除暂停阶段 | 卡面未给（我建的） | **1**（`test_urgent_farm_work_ignores_suspended_stages…`） | 修法②有独立用例 |

### §3.2 重跑 task-200 矩阵（基线迁移：0.7.37 是 2 红 → 0.7.38 是 0 红）

| 卡 | 自报 | 0.7.37 实测(净) | 0.7.38 实测 | 判定 |
|---|---|---|---|---|
| 198（7 条） | 10/4/2/1/2/3/1 | 10/4/2/1/2/3/1 | **10/4/2/1/2/3/1** | 完全一致（不再有 +2 基线偏移） |
| 192（2 条） | 卡面未给 | 5 / 3 | 5 / 3 | 一致 |
| 202（2 条） | 卡面未给 | 3 / 0 | 3 / 0 | 一致 |
| 208（2 条） | 卡面未给 | 1 / 0 | 1 / 0 | 一致 |
| 213（3 条） | 卡面未给 | 1 / 0 / 0 | 1 / 0 / 0 | 一致 |
| 199（7 条） | 6/1/1/1（无脚本=GAP） | 5/0/2/1/1 | 5/0/2/1/1 | 4 条不符（task-200 已知 GAP-1，本批无新增、同址性不可证） |

- `_t200_probe.py` 在 `_t238` 上：**45 PASS / 0 FAIL / 3 SKIP**（与 0.7.37 冻结树相同 ⇒ task-216 未扰动 198/199 通道）。
- 备注：199 的 4 条"不符"来自「作者没有交变异脚本、我按描述重建」，不是本次 delta 的回归。

## §4 结论

**一句话：0.7.38 可以放行 A″/B″（PASS-WITH-NITS，无阻塞项）。**

- F3 修复在主循环级实测有效（pre 复现 `pickup_calls=0` + `stuck`，post `pickup_calls=1` 且非 stuck）；
  两条修法各有独立主循环级/单测用例钉住，我的变异分别杀 1 / 1。
- 通道⑤ 在"当天还有活"的 wait/need_slot 日已如实留痕（pre 0 → post 1，字段 `which`/`reason` 正确）。
- GAP-2 与 GAP-1 均闭合（C# 新增 t216 断言实测杀 3；`_t205_mutate.py` 在库）。
- 冻结树读数：1055/OK、build 0/0、C# 76 断言；task-200 的 198/199 通道与全部变异无回归。
- **剩余阻塞项：无。** 剩余非阻塞项：
  - NIT-1：纯"无活"日仍不留 `tool_upgrade_skipped`（早退点早于工具升级块）⇒ 建议 0.7.39；
  - NIT-2：`manifest.json`/`dll` 的指纹口径（CRLF/归档、dll 不在归档且未找到装机路径）⇒ 已注明，不影响判定；
  - NIT-3（沿用 task-200）：task-199 的作者变异仍无脚本，4 条重建不符只能记 GAP。

## §5 边界

- 只读生产码；未修改 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs/00-开发日志.md`；未碰游戏/桥/任务板。
- 未装机、未 bump、未起跑批；变异全部在 `scratch/_t200_mut/` 副本上做并跑完即删。
- 原始读数：`scratch/_t238_probe_post.txt`、`scratch/_t238_probe_pre.txt`、`scratch/_t238_full.txt`、
  `scratch/_t238_mut216.txt`、`scratch/_t238_mut_all.txt`、`scratch/_t238_probe200.txt`。
