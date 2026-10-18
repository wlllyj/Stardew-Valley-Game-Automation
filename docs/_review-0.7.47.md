# 0.7.47 增量对抗验收（task-37，deputy-lead）

> 对象：冻结提交 `a03a564`（父 `7657239` = task-35 快修；`git archive a03a564` 冻结树）
> 对照基线：`737c4a5`（0.7.46 冻结）
> 判定：**PASS-WITH-NITS**（代码面，A/B/C/D/E 全绿）
> 放行结论：**0.7.47 的 task-35 增量自身未发现新洗白通道**；A9 是否放行不由本报告单独决定 —— smoke-0746 门禁证据（`59eb3f4`/`d58c1a0`）已由 Lead 裁决：5 PASS + 门禁②未触发【无法判定】+ 步 7 字段缺口 FAIL ⇒ **A9 暂不放行**，待 0.7.48 快修（task-38）。
> 边界：离线只读验收；未跑真机、未改任务板/开发日志/生产代码；作者自报数只作对照列，实测一律冻结树副本重跑。

## §0 判定摘要

| 项 | 读数 |
|---|---|
| 冻结树 provenance | tracked 785 / present 785 / missing 0 / mismatch 0（eol 归一 6） |
| 关键 blob | A0b 9/9（longrun/farmwork/bridge/test_longrun/manifest/_mutate_t*gate* 等） |
| delta 范围（737c4a5→a03a564） | 7 文件 400+/13-：longrun.py、bridge.py、manifest.json、tests/test_longrun.py、tests/_mutate_t35_backpack.py、tools/run-longrun.py、tools/_note-0747.txt |
| 版本载体 | bridge `MOD_VERSION_EXPECTED="0.7.47"`、manifest `Version=0.7.47`、note 首行 v0.7.47 |
| dll | 293888B `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A`（与 0.7.46 逐字节相同） |
| 探针合计 | **PASS=51 / FAIL=0 / SKIP=0 / INFO=2**（A 18P+2I、B 14P、C 14P、D 4P、E 3P） |
| 作者变异 | 自报 3/3；冻结副本实测 **3/3 killed**（红 3/2/2） |
| 我方变异 | **6/6 killed**（未杀 0 / 异常 0） |
| 全量单测（冻结树，补夹具后） | `Ran 1382 tests / OK` |
| 判定 | PASS-WITH-NITS；NIT 5 条（§6） |

## §1 A 段：provenance 与 delta 范围（18 PASS + 2 INFO）

- **A0**：`git ls-tree -r a03a564` 全量 785 blob 与冻结树逐文件对照 —— 0 缺失 / 0 不符；eol 归一 6 个（`.ps1/.bat/.cmd` 及 CRLF 文本）。**A0b**：INFO —— 冻结树另有 23 个夹具/缓存文件（我拷入的 `scratch/_ledger*` 与 `logs/` 账本，非追踪）。
- **A1**：delta 文件集合恰为 7 个，无额外文件、无缺文件。
- **A2 逐文件语义范围**（AST 级）：
  - `longrun.py` 只改 `LongRun.__init__` / `_backpack_skip` / `_maybe_buy_backpack_upgrade`；
  - `tools/run-longrun.py` 只增 `BACKPACK_UPGRADE_ENV` / `BACKPACK_ENV_TRUTHY` / `import os` / `backpack_upgrade_enabled_from_env` / `build_parser` / `main`；
  - `tests/test_longrun.py` 只新增 `TestTask35BackpackGate`（11 个新符号）+ `TestTask25BackpackUpgrade._run` 一行显式开启（task-35 测试口径，允许并单列）；
  - `bridge.py` 只改 `MOD_VERSION_EXPECTED` 赋值（注释随版本）；
  - `manifest.json` 只改 `Version` + `Description`（仓库口径：Description 即版本 changelog，属版本载体，非功能变更）。
- **A3**：6 关键文件 `git hash-object` 与冻结 blob 6/6 相等。
- **A4**：版本三载体一致 0.7.47；**A4b**：本地 `mod/AgentFarm.Bridge/bin/Release/*.dll` 293888B 与 0.7.46 逐字节同（大小写归一比较），Mod 源码 diff 为空可交叉印证。
- **A5 checks 未动**（核心红线）：
  - `rep.checks = {…}` 10 键字面与 0.7.46 **逐字相同**（len 2973=2973）；键集合 = `CHECKS_BASELINE`；
  - `no_unmet_stages` 公式逐字未动；journal 事件名 added=[] removed=[]；`DayReport` 字段 0 增删；
  - `unreachable_bound` 仍是 `max(5, int(0.2 * bound_basis_steps))`，护栏 B `cleared_tiles` 未动。
- **A6 默认关闭源码形态**：`backpack_upgrade_enabled` 是 **kwonly** 且默认 `False`（AST `kwonlyargs/kw_defaults` 实测）；关闭分支位于 `ensure_location`/`_backpack_talk_once` 之前（disabled@340 < goto@1046 < talk@1610）；env 真值表字面 `("1","true","yes","on")` 且按集合精确匹配。

## §2 B 段：默认关闭 / opt-in / checks / 旧账本（14 PASS）

| 编号 | 结论 | 实测 |
|---|---|---|
| B1 | 默认关闭**零请求** | `_maybe_buy_backpack_upgrade` 返回 False；`talk_calls=0`；`buy` 事件 1 条 `status=skipped, code=disabled` |
| B1b | 日终只读 skip，不加 notes | `day_end.backpack_upgrade_skip="disabled"`、`notes=[]`、`attempts=0` |
| B1c | 每天最多 1 条 skipped 留痕 | buy 事件数=1（重复调用不累加） |
| B2 | 显式开启后成功须双差分 | money 3264→1264（−2000）、capacity 12→24、`backpack_upgrade_ok=True` |
| B2b | 三种失败码不得认成功 | money_unchanged ⇒ `money_not_deducted`、capacity_unchanged ⇒ `capacity_not_changed`、dismiss_new_day ⇒ `money_diff_ambiguous`；三者钱/容量未动或仅单边动，均返回 False |
| B2c | gate 跳过且零请求 | `already_upgraded` / `cannot_afford` / `talk_unavailable` 均 `talk=0` |
| B2d | 同一天失败后不重试 | talk 调用数 1→1 |
| B3 | `is_justified_end` 边界未变 | malformed 否决仍最先；`resume_exhausted` 仍需 `pending_executable==0`；`stuck:` 永不认 |
| B4 | 旧账本回归 | 对 smoke-0745 / A8 跑 `_t0746_prep_replay.py`：rc=0、`FAIL=0`、27 条判红命中 0 |

## §3 C 段：对抗通道（14 PASS，≥6 要求）

自检 C0a–C0g 先验判据三态，然后逐通道：

| 通道 | 对抗动作 | 结果 |
|---|---|---|
| C1 | 默认值改回 True（源码+动态双证） | 探针判红；源码 False、运行时 False |
| C2 | 删关闭分支 ⇒ 关闭时照发 talk | 动态 raise 证明零调用：ret=False、talk=0、attempts=0 |
| C3 | 开启后丢双差分（信回执 applied） | 失败必须 False 且账本无 `status=ok` 的 buy；两模式实测均 false/0 |
| C4 | skipped 冒领购买 | 只计 `status=="ok" and ok is True`；skipped 不计 |
| C5 | env 解析放宽 | 独立重实现真值表：truth 6 值全 True、falsy 9 值全 False，mismatch=[] |
| C6 | 版本不一致 | bridge=manifest=0.7.47 判绿；n/a 不一致路径自检 C0g 判红 |
| C7 | 新字段污染 checks | 只查字面键名；10 键无 `backpack_/loot_lost/relief_/bag_evidence/pending_` 前缀键 |
| C8 | dll 与冻结产物不一致 | 293888B / 哈希一致 |

## §4 D 段：变异两列（副本跑，未碰冻结树/仓库）

作者脚本 `tests/_mutate_t35_backpack.py`（`--from-worktree`，ROOT=冻结树；目标 `TestTask35BackpackGate` + `TestTask25BackpackUpgrade`，baseline Ran 16 OK）：

| # | 变异 | 作者自报 | 我方实测（副本） |
|---|---|---|---|
| m1 | 默认值改回 True | 3/3（合计） | killed（红 3 条） |
| m2 | 开启后丢双差分（信 `talk.applied`） | 同上 | killed（红 2 条） |
| m3 | 删关闭分支 | 同上 | killed（红 2 条） |
| 合计 | | **3/3** | **3/3，存活无** |

我方自建变异 `scratch/_t0747b_mutate.py`（`--check-anchors` 6/6 恰 1 次，`--all`）：

| # | 变异（锚点） | 杀器 | 结果 |
|---|---|---|---|
| m37a | `backpack_upgrade_enabled: bool = True` | probe FAIL×4 + unittest 红 3 | KILLED |
| m37b | 关闭分支 `if False:` | probe FAIL×3 + unittest 红 2 | KILLED |
| m37c | `if money_ok and cap_ok:`→`if talk.get("applied"):` | probe FAIL×3 + unittest 红 2 | KILLED |
| m37d | 关闭时不留 `buy{skipped}` 痕迹 | probe FAIL×3 + unittest 红 1 | KILLED |
| m37e | env 真值表加 `"2"` | probe FAIL×1（C5） | KILLED |
| m37f | `MOD_VERSION_EXPECTED="0.7.46"` | probe FAIL×1（C6） | KILLED |
| 合计 | | | **6/6 被杀；未杀 0；异常 0** |

## §5 E 段：读数

- E1 `python -W error::SyntaxWarning -m py_compile`（longrun.py / bridge.py / run-longrun.py）rc=0。
- E2 定向：`TestTask35BackpackGate` + `TestTask25BackpackUpgrade` = **Ran 16 / OK**。
- E3 冻结树全量（先补 `scratch/_ledger*` 夹具 + `logs/longrun-*.jsonl`）：**Ran 1382 / OK**。
- 与 Lead 装机自报 1388 差 6 ⇒【无法判定】（与 0.7.46 期 1383 vs 1377 同一形态；冻结 archive 不含工作树未提交测试，差额不归因）。

## §6 NIT（单列，均不阻塞 0.7.47 增量代码面判定）

1. **NIT-1**：A2 把 `manifest.json` 的 `Description` 归入版本载体（仓库惯例：Description 内嵌 changelog 随版本更新）。若冻结口径要求"manifest 只许 Version 变"，需 Lead 明确；本报告按版本载体接受并记录。
2. **NIT-2**：冻结树全量 1382 vs 装机自报 1388 差 6【无法判定】（同 NIT-2 历史形态）。
3. **NIT-3**：dll 比对来自本地 `bin/Release`（git 不追踪、冻结树无 bin）。哈希与冻结产物一致 + Mod 源码 delta 为空可交叉印证，但严格 provenance 只能证明"本地构建产物与冻结产物同"，不能证明"冻结时 dll 与实际部署件同一文件"。
4. **NIT-4**：作者自报 3/3 无独立出处（脚本 docstring 只声明条数与目标类），本报告"自报"列取运行输出；实测列独立重跑。
5. **NIT-5**：task-35 测试为 `TestTask25BackpackUpgrade._run` 补 `run.backpack_upgrade_enabled = True`（属 opt-in 测试口径调整，A2 已按允许集单列；不是产品语义变更）。

## §7 边界声明

- 本报告只评审 `a03a564` 冻结树的 task-35 增量（默认关闭/opt-in）；不重新判定 0.7.46 及其前序卡，也不替代 smoke-0746 门禁判定。
- A9 放行口径不变：需 smoke-0746/0747 真机门禁全绿 + 步 7 字段缺口修复；`resume_budget_exhausted` 仍不得进 `is_justified_end` 白名单；A9 判读 `already/attempted_ok` 与 `ok` 双列。
- 未跑真机、未 deploy、未改任务板/开发日志/生产代码；工作树只提交本报告与探针/变异脚本。
