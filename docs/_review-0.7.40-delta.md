# 0.7.40 delta 独立对抗验收（task-233 / task-232 / 建造预留）

**验收人**：deputy-lead（task-234）｜**日期**：2026-10-18｜**对象**：`git archive 6f9b797`（0.7.40 冻结）
**范围**：`cb1fb05`（task-233 非片区 `no_target`）、`6a7f100`（task-232 空格压力腾格）、`a4cd307`（建造预留增量）、`6f9b797`（版本冻结，无 Mod 代码）
**边界**：只读冻结树 + 只写 `scratch/`；未碰游戏/桥/生产码；未 bump。

## §0 一句话结论

**可以放行 A″/B″**：task-233 的 A1–A4、task-232 的 B1–B6 与建造预留 B4 全部实测通过，作者两个变异脚本复跑**自报 100% 相符**；唯一未判项是真机冒烟 C 段（跑批尚未 `finish`，中局读数已支持同一方向），另有 1 条 NIT（见 §B6-NIT，不阻塞）。

## §A 段：task-233（非片区意图不许裸 `no_target`）

| 项 | 判据 | 实测 | 判定 |
|---|---|---|---|
| A1 | `ship` 卖不出 ⇒ `unknown_evidence`+`unknown_why`，无 `no_target`，带可判证据 | `reasons=={"unknown_evidence":1}`、`unknown_why="non_plot_task"`、`whitelist_count=0/free_slots=8/inventory_full=False/obs_seq=1`、`_intent_coverage_ok=True` | **PASS** |
| A2 | 片区任务取消仍 `no_target` + `evidence.stage_tiles_empty is True` | `run.run()==0`，`harvest` 记录 `reasons={"no_target":1}`、`stage_tiles_empty=True`+`obs_seq`/`counts` | **PASS** |
| A3 | 旧账本 ⇒【无法判定】、不判 `intent_no_target_evidence` 红 | `logs/longrun-3day-llm-run9c.jsonl --days 3` 输出无该红，且给出"无法判定" | **PASS**（INFO：旧账本走无法判定） |
| A4 | analyzer §8.3.7：裸 `no_target` 红、非片区证据不红 | `cat_intent`：裸 ⇒ `missed:intent_no_target_evidence:ship`；带 `unknown_why` ⇒ 无红 | **PASS** |

- 已知边界（INFO，非本卡引入）：`unknown_evidence` 缺 `unknown_why` 时工具**不判红**（§8.3.7 只校验 `no_target` 的证据包；"降级理由是否成立"在账本层不可验证）。brain 侧用例把 `unknown_why` 钉死，账本层属可接受边界。

## §B 段：task-232（空格压力腾格）+ 建造预留

| 项 | 判据 | 实测（冻结树） | 判定 |
|---|---|---|---|
| B1 | 满包+熟作物+有盈余 ⇒ 先 `slot_relief` 再收，`freed>=1`、`sold[]` 非空 | `trigger="space_pressure"`、`sold=[{(O)388,stack 99,tier 2,keep 10}]`、`freed=1`、`ok=True`；卖后空格 ≥1 | **PASS** |
| B2 | 满包+无盈余 ⇒ 如实 `inventory_blocked`，`failed_steps==0` | `ok=False`、`inventory_blocked_today=True`、`sold=[]`、理由含"没有可卖的盈余叠…腾不出格子"、`failed_steps=0` | **PASS** |
| B3 | 工具/武器/种子/升级锭/表外物品一件不卖 | 12+7 行混合背包：白名单只有 `(O)388`；`(T)Pickaxe/(O)334/(O)338/(O)787/(O)999/(O)207 Hay/(O)472` 全部排除 | **PASS** |
| B4a | `(O)378` 铜矿 30 件只卖 5 留 25 | 叠 5+叠 25：卖 `stack=5, keep=25, reserved=True` ⇒ 卖后仍 25 | **PASS** |
| B4b | `(O)390` 石头 28 件一件不卖 | `slots=[]`、`skipReason="剩下的可卖叠都是建造预留材料…宁可不腾格"` | **PASS** |
| B4c | `(O)378` 单叠 30 不许整叠卖空 | `slots=[]`+同款 skipReason（预留叠永不进"整叠卖空"回退） | **PASS** |
| B5 | 有界：≤3 轮/天、≤5 叠/天 | 连续 8 次 `_slot_relief`：`stacks_today=...≤5`、`slot_relief_today≤3`、`sell` 调用 ≤5 | **PASS** |
| B6a | 回执 ok 但背包行数没减 ⇒ 不判成功、`failed=true`、如实 blocked | `failed=True`、`blocked_reason="卖了 1 叠但背包行数没减少（11→11）…"`、`inventory_blocked_today=True` | **PASS** |
| B6b | 卖时脑侧给自己加钱 ⇒ 红线被抓 | `failed=True`、`blocked_reason="钱数变了（1977→2076）：钱只能由游戏的下一次 NewDay 结算…"` | **PASS** |

### B6-NIT（不阻塞，建议 0.7.41 跟进）

- **现象（真机冒烟实测）**：`logs/longrun-smoke-0740.jsonl` 第 1 天第 1 轮 `slot_relief` 卖出了 1 件 Wheat（`sell` 回执 `ok=true`、"背包 11→10"、`shipping_bin=1`），但同一轮双差分读到 **rows 12→12 ⇒ `failed=true`**，当天随即 `inventory_blocked` 收尾（`verified=false`，诚实但**白耗一天**）。同一天后续轮次与第 2 天同类卖出 `freed=1` 正常（中局 `slot_relief` 3 次 / `freed` 合计 2 / `sold` 4 件）。
- **推断**：`_slot_relief` 在卖出后只 `_snap_or(obs)` 一次；若该次再观测拿到的是卖出前的快照（桥瞬断/快照滞后），`rows_after` 就与 `rows_before` 相同 ⇒ 双差分误判"没生效"。属**保守误判**（不会洗白），但会牺牲达标日，直接伤害 A″/B″ 的"连续达标"目标。
- **建议**：①`_snap_or` 之后再补一次 `observe`（或把 `rows` 差分与 `sell` 回执里该 qid 的 `count` 下降做"或"判定，仍保留钱不变红线）；②当日若 `failed=true` 但 `sell` 回执 ok，journal 里保留回执便于事后归因。归 **0.7.41（或作为 A″/B″ 期间的观察项）**。

### 附加观测（INFO）

- 累计 `slot_relief_sold` 参与双差分：第二轮"卖无可卖"时会用第 1 轮的累计 `sold` 去比本轮 rows ⇒ 会误报 `failed=true`。实测已复现（`rows 12→12` 的同类文案）。后果仅是把一个本来就要 `inventory_blocked` 的日子标成"卖出没生效"，**不改判定、不洗白**；建议与上条一并修（改用本轮 `sold`）。

## §C 段：真机冒烟只读对账 —— 【无法判定】（跑批未 finish）

- 产物现状（12:14 中局）：`logs/longrun-smoke-0740.jsonl` 101 行、**`day_end` 1 条**（`inventory_blocked`，`verified=false`）、`slot_relief` 3 次（`freed` 合计 2、`sold` 4 件）、无 `finish`；`docs/_smoke-0740.md` 尚未生成。
- 已有方向性证据：空格压力通道在真机上**确实卖出并腾出格子**（第 2 天 `freed=1`、`sold` 明细可核）；第 1 天那次 `failed=true` 即 §B6-NIT。
- 待 `finish` 后需要补判的三条（届时我出 delta 一句）：
  1. 日报告不全为 `inventory_blocked`（当前 1/1，样本不足）；
  2. `slot_relief.freed>0` 且 `sold[]` 可核（**已满足**）；
  3. `docs/_smoke-0740.md` 中无 `missed:intent_no_target_evidence:ship`、A2 证据链（`kind_trace`/`use_tool_calls`）齐全。
- 冒烟期间我只读，未碰游戏/桥。

## §D 段：作弊通道对抗

| 通道 | 结果 |
|---|---|
| ①`ship` 裸 `no_target` | 被 analyzer 判红（A4 实测 `missed:intent_no_target_evidence:ship`） |
| ②`unknown_evidence` 掩盖真失败 | 缺 `unknown_why` 时工具不判红（账本层不可验证）⇒ 记为已知边界（见 §A INFO）；brain 用例钉住字段 |
| ③`slot_relief` 卖工具/种子/建造材料 | B3/B4 实测全排除；`NEVER_SELL_IDS`+三档白名单+表外 fail-closed |
| ④整叠卖空破坏 reserve | B4c 实测：预留叠永不进整叠卖空回退，宁可 `skipReason` |
| ⑤自己加钱 | B6b 实测被抓；D5 静态扫描：脑侧无写 `player.money` 的代码（仅写 `facts["money"]` 证据字段） |
| ⑥双差分被绕过 | B6a/B6b 实测；另见 NIT（滞后导致**保守误判**，方向安全） |
| ⑦键集漂移 | D7：`checks` 仍 10 键、无新事件名（`sell` 复用 strategy/why 字段）；全量 1171 红 0 |

## §变异：作者自报 vs 实测（两列）

在冻结树内复跑作者脚本（`python scratch/_t233_mutate.py` / `python scratch/_t232_mutate.py`，基线均 0 红）：

| 变异 | 自报杀 | 实测杀 | 一致 |
|---|---|---|---|
| m233a ship 退回裸 `no_target` | 1 | **1** | ✅ |
| m233b `_no_target_evidence` 恒 None | 1 | **1** | ✅ |
| m232a 关空格压力通道 | 2 | **2** | ✅ |
| m232b 去掉每 qid 留 K | 4 | **4** | ✅ |
| m232c 表外也卖 | 3 | **3** | ✅ |
| m232d 关建造预留覆盖 | 3 | **3** | ✅ |
| **合计** | 14 | **14** | ✅ 100% 相符 |

- 作者脚本自带 `ROOT=__file__.parents[1]`、拷 `brain`+`tests` 到临时目录、`PYTHONUTF8=1`、只跑本卡用例类 ⇒ 在冻结树里可直接复跑（无 GAP）。
- 我的独立探针（`scratch/_t234_probe.py`，`T234_ROOT` 切树）：冻结树 **PASS=42 / FAIL=0 / INFO=5**；README 输出 `scratch/_t234_probe_out.txt`。

## §越界

- 三个提交的 `--name-only` 只含声明范围（`brain/agentfarm/{longrun,farmwork}.py`、`tests/{test_longrun,test_farmwork}.py`、`scratch/_t23{2,3}_mutate.py`）；`mod/`、`tools/`、`manifest.json`、`logs/`、`docs/00-开发日志.md` 在本批（`cb1fb05`/`6a7f100`/`a4cd307`）**零命中**；版本冻结提交 `6f9b797` 只改 `bridge.py` 版本行 + `manifest.json`。
- 我又写的文件只有 `scratch/_t234_probe.py` 与 `scratch/_t234_probe_out.txt`。

## §读数（冻结树 `6f9b797`，我亲跑）

- `py_compile -W error::SyntaxWarning`（longrun/farmwork/planner/bridge）**rc=0**
- 定向 `tests.test_farmwork tests.test_planner tests.test_longrun` **Ran 707 / OK**
- 全量 `python -m unittest discover -s tests` **Ran 1171 / OK**（与 Lead 报数一致）
- `dotnet build --nologo --no-incremental` **0 警 0 错**
- C# 自检 `OK 85 断言全部通过`
- 版本：`manifest 0.7.40` / `LR.MOD_VERSION_EXPECTED="0.7.40"`

## §末句：还缺哪几条、归哪张卡

1. **C 段（真机冒烟）**：等 `logs/longrun-smoke-0740.jsonl` 出 `finish` + `docs/_smoke-0740.md` 落地，我补 delta 一句（属本卡收尾，不新开卡）。
2. **B6-NIT（双差分偶发保守误判 / 累计 `sold` 参与双差分）**：建议归 **0.7.41 的 task-232 后续**（另一张卡）；修法见 §B6-NIT，**不阻塞** 0.7.40 放行 A″/B″。
3. 其余 A/B/D 判据与变异两列**已全部闭合**，0.7.40 可据此起跑 A″/B″。
