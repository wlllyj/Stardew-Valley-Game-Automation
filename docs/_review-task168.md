# task-168 独立对抗验收 — 规模取舍（`reduce_scope` / `scope_shed`）

- 验收对象：**task-168 = `e56f2fc`**（3 文件 +841/−8：`brain/agentfarm/longrun.py` +454/−7、`brain/agentfarm/planner.py` +157/−0、`tests/test_longrun.py` +230/−1）；已被 **0.7.35 冻结提交 `630e594`** 吸收，HEAD `30082e0`（`brain/*` 自冻结后未再动）。
- 工具侧配套（Lead 自己改的，非本次验收对象，但构成第四方交叉）：`tools/verify-run3.py` 补 `scope_shed` 口径核对 + 4 条单测（我复核 `Ran 69 tests / OK`）。
- 验收人：deputy-lead（只读 `brain/`/`mod/`/`tools/`/`tests/`，只写 `docs\_review-task168.md` + `scratch\_t185_*`）。

## §0 判定摘要

**判定：PASS-WITH-NITS ⇒ 0.7.35 可以据此冻结**（唯一 NIT 非阻塞，但建议发 A′/B′ 前顺手收，见 §6 NIT-1）。

| 项目 | 读数 |
| --- | --- |
| `py_compile -W error::SyntaxWarning`（longrun/planner/farmwork/bridge） | exit 0 |
| 定向 `tests.test_farmwork tests.test_longrun tests.test_planner` | **Ran 542 / OK**（与 release doc 一致） |
| 全量 `discover -s tests` | **Ran 945 / OK**（0 红，与 release doc 一致） |
| `tests.test_verify_run3`（含 4 条 scope_shed 用例） | **Ran 69 / OK** |
| 我的对抗探针（冻结 post 树） | **50 PASS / 0 FAIL** |
| pre 树（`e56f2fc^`，无该特性） | 11 SKIP（特性不存在）+ 2 FAIL（该树的工具是旧版、无 scope_shed 判据 ⇒ 不可比） |
| 自建变异矩阵 | control **50/0**，**6 变异 6 杀** |
| 作弊通道 | 9 条逐条打，**未发现能把"认输"洗成"当天达标"的通道** |

一句话给 Lead：**task-168 的"认输"在判定、会计、浇水证据三处都没有被动过（只改目标池与守卫理由），上界与留痕经跨进程复核与变异复核都成立；0.7.35 可以冻结。** 唯一要拍板的是 §6 NIT-1（认输被释放后 `day_end` 快照不归零，可能让工具把雨天释放日误判为"认输却自称 VERIFIED"）。

## §1 A 段：范围、越界、读数

- `git show --stat e56f2fc`：3 文件、+841/−8；`--name-only` ⊆ 卡面写盘范围（`brain/agentfarm/longrun.py`、`brain/agentfarm/planner.py`、`tests/test_longrun.py`）。
- 越界扫描（`^mod/|^tools/|manifest.json|bridge.py|^logs/|00-开发日志`）于该提交 **0 命中**；bump 由 Lead 的冻结提交 `630e594` 完成（`bridge.py` 10/1、`manifest.json` 4），**dev-coder 未越权**。
- 我按 `git archive` 冻结两棵树验收（在制工作树会移动）：
  - `scratch/_t185_post` = `e56f2fc` 冻结后内容（480 文件），
  - `scratch/_t185_pre` = `e56f2fc^`（479 文件）。
- **验收对象与冻结内容的等价性（blob 级证明，而不是"看起来一样"）**：`git hash-object` 我的快照文件 vs `git rev-parse` 冻结树 `30082e0`（0.7.35 装机记录提交）：
  - `brain/agentfarm/longrun.py` `60f9d12ce87d` == `60f9d12ce87d`；
  - `brain/agentfarm/planner.py` `2d25b09c0950` == `2d25b09c0950`；
  - `tests/test_longrun.py` `1ccf164e109d` == `1ccf164e109d`。
  ⇒ 本报告验收的就是 0.7.35 冻结内容（`630e594` 冻结 → `30082e0` 装机记录均在我验收期间落地；报告落盘时 HEAD 已推进到 `c67b85f`（task-186/0.7.36），那是**下一批**的改动，不在本次判定范围）。
- 关键文件 SHA256 前 16（post 树）：`brain/agentfarm/longrun.py D5F8F98D16AC8451`（417566 B）、`brain/agentfarm/planner.py 22FD11BC6E4DF724`（117632 B）、`tests/test_longrun.py F00B40E69DF45F65`（508081 B）、`tools/verify-run3.py 407F726917319B8A`（85529 B）；pre 树 `longrun.py 2C5DEAAA0368B0C1`。
- 特性探测（探针 `has_168()`）：post 树有 `DayReport.scope_shed/scope_shed_tiles`、`LongRun._shed_scope/_scope_load/_scope_flush/_shed_tile_set/_shed_live_crops/_release_scope_if_converged/_zone_live_crops/_work_budget_facts`、`SCOPE_SHED_MAX_PER_DAY=1`、`SCOPE_SHED_MAX_FRACTION=0.34`；pre 树全无。
- 作者用例：`tests/test_longrun.py:9074 class TestTask168ScopeShed`（`Ran 542/945` 全绿）。我只跑读数，对抗面全部自建（见 §3–§4）。

## §2 B 段：卡面三条验收 + FAIL→PASS

### ① 缺口语境下允许认输并如实留痕（A2）
- 世界：200 格未浇活苗 ⇒ `_work_budget_facts` = `live=200 cap=129 deficit=71`；`_shed_scope(z0, obs, rep)` ⇒ **True**。
- journal `scope_shed{zone, tiles=50, live_crops, water_capacity, deficit, target_tiles, harvested_steps, reason, note}`；
- `day_end`：`scope_shed={zone,tiles=50,reason,live_crops,water_capacity,deficit,since_day,harvested_steps}` + `scope_shed_tiles=50` + `rep.notes` 追加"主动认输 …"；
- 该区 30/50 格 ⊆ `_shed_tile_set()`（目标池剔除集）⇒ 认输只作用于"选择哪片地"，**不动会计**。

### ② 认输 ≠ 已浇，当天如实不 VERIFIED（A3/A4）
- `_water_evidence` ⇒ `watered_outdoor=False`、`final_water.dry>0`；`farm.dryCrops` 未被抹掉。
- `_leftover("water_area", …)` **认输前后逐字相同**（200 格全在）⇒ `no_unmet_stages=False` ⇒ 当天不可能 VERIFIED；`checks` 里没有新增 scope/shed 键（无"可写成 true"的新钩子）。

### ③ 上界双保险 + 跨进程（B1/B2/X1）
- 一天只认 1 个区：第二个区被拒 `already_today`，journal `scope_shed` 恰 1 条。
- 单区超 34%：`farm_workable=200 ⇒ cap_tiles=68`，单区 200 格 ⇒ `refused{cap}`。
- **跨进程（F-X1 的正面证据）**：`<journal>-scope.json` 持久化每区格清单，`_scope_load` 把格清单灌回 `shed_zone_tiles` ⇒ loaded=50 / 文件自述=50，`shed_zones` 仍在；此时"已用 50 + 新 50 > cap 68"仍被 `refused{cap}` 拦住 ⇒ **累计上界不是"只在单进程内成立"**。

### 正对照与边界（P1/A7/R1）
- P1：活苗 3 格（deficit=0）⇒ 拒绝 `no_deficit`，不写 `scope_shed` 事件。
- A7：farm 证据不可用（`complete=false`）⇒ `deficit` 必须是 `None`（不许当 0）⇒ 拒绝 `no_farm_evidence`。
- R1：区内无未浇活苗 ⇒ 撤销认输（`scope_released`，`zone_has_no_unwatered_crops`）、剔除集清空 ⇒ "粘但可释放"成立。

### FAIL→PASS 说明
- pre 树没有这些能力（11 条 SKIP）⇒ 卡面三条在 pre 上**不可判**（不是"曾经失败"）。
- 真正的 FAIL→PASS 是我的骨架阶段发现的 **F-X1**（重启后 `shed_zone_tiles` 为空 ⇒ 34% 累计上界归零）：我当时在 WIP 树上复现（`loaded=0 / disk=50`），dev-coder 用 `<journal>-scope.json` + `_scope_load` 灌回修掉；修后 X1 五条全绿（§2 ③），并且我的变异 m185a/m185b 仍能把这两点打红 ⇒ **修复被钉住**。

## §3 C 段：作弊通道逐条对抗（9 条）

| # | 通道 | 构造 | 实测 | 结论 |
| --- | --- | --- | --- | --- |
| C-a | 认输区被当"已浇" ⇒ 假绿 | 认输后取 `_water_evidence` / `farm.dryCrops` | `watered_outdoor=False`、`dry>0`、`dryCrops` 未抹 | **不通** |
| C-b | 认输变"免罚额度"（会计被扣） | 认输前后比 `_leftover` | 200 格逐字相同、认输格仍在 leftover | **不通**（m185c 可打红） |
| C-b2 | 一次把守卫"还有活"扣光 | `live_crops_at_shed=1e9` + 人回室内 | 变异后 farm 级理由消失（我的 A6b 抓住）；生产版仍报"还有 150 格干作物" | **不通** |
| C-c | 没有缺口也认输 | 活苗 3 格 | `no_deficit` 拒绝、无事件 | **不通** |
| C-d | 上界被绕过 | 上界按区数算 / 单区超限 / 重启 | `cap` 拒绝；跨进程仍拒绝 | **不通** |
| C-e | 认输却自称 VERIFIED | 脑侧：leftover 仍在 ⇒ `no_unmet_stages=False`；工具侧：T3d | 工具 problem「认输 N 格却自称 VERIFIED」 | **不通** |
| C-f | 证据不可用当"没有活" | `complete=false` | `deficit=None` ⇒ `no_farm_evidence`，绝不认输 | **不通** |
| C-g | `day_end` 快照漏字段 | 变异去掉 `tiles` | A2 两条红（快照必须带 tiles） | **不通** |
| C-h | 认输永久粘死 | 区内浇好 | `scope_released` 撤销、剔除集清空 | **不通**（粘性跨进程由 X1 覆盖） |

一句话结论：**未发现新洗白通道**。认输只改"选择哪片地/怎么解释还剩多少活"，判定（`checks`/`verified`）、会计（`_leftover`/`assigned_undone`/`plot_pending`）、浇水证据（`watered_outdoor`/`final_water`）三处都没被触碰。

## §4 变异矩阵（自建，`scratch\_t185_mutate.py`）

做法：把冻结 post 树拷到 `scratch/_t185_mut/<case>`，只对 `brain/agentfarm/longrun.py` 做纯文本变异，再用 `T185_ROOT` 指向拷贝跑同一套探针。

| 变异 | 改动 | 红了哪几条 |
| --- | --- | --- |
| control | 无 | 无（**50 PASS / 0 FAIL**） |
| m185a_no_hydration | `_scope_load` 不灌回格清单 | X1 灌回（loaded=0 disk=50） |
| m185b_cap_counts_zones | 上界 `already` 按区数算 | X1 上界生效 + X1 理由=cap |
| m185c_leftover_subtracts | `_leftover` 扣掉认输格 | A4 逐字相同 + A4 认输格仍在 leftover |
| m185d_shed_deducts_everything | `live_crops_at_shed=1e9` | A6b 农场级理由仍在 + A6b 格数=150 |
| m185e_no_deficit_gate | 去掉 `deficit<=0` 门闸 | P1 理由=no_deficit |
| m185f_snapshot_no_tiles | `day_end.scope_shed` 去掉 `tiles` | A2 快照带 tiles + A2 认输格数 |

⇒ **6/6 被杀**（作者删除的变异脚本由我重建；m185d 是我第一版探针漏掉的通道，靠给 A6 加"农场级理由必须仍存在"的断言才补上，见 §6 INFO-2）。

## §5 工具侧第四方交叉（`tools/verify-run3.py`）

- T1：工具认 `scope_shed`/`scope_shed_tiles`（day_end 白名单）；`tools/analyze-longrun.py` 无缺桶（新事件全部有桶）。
- T3a：账本自称认输 7 格、journal 无事件 ⇒ **problem**（认输量对不上）。
- T3b：journal 有 `scope_shed`、账本没写 `scope_shed_tiles` ⇒ **problem**（缺失 ≠ 通过）。
- T3c：自述与 journal 一致 ⇒ 只 info，判决与基准同码。
- T3d：认输 5 格 + 当天 `verified=true` ⇒ **problem**（自相矛盾）。
- T3e：a/b/d 判红、c 与基准同码 ⇒ **与脑侧同向，无反向判据**。
- 我另跑真账本：`tools\verify-run3.py --journal logs\longrun-3day-llm-run9c.jsonl --days 3` ⇒ rc=1、`结论：needs_review`（4 条**窗口外历史**问题，与 `scope_shed` 无关；该账本生成于 task-168 之前，无该字段）。

## §6 NIT / INFO / 残余

- **NIT-1（非阻塞，建议 A′/B′ 前一行收，请 Lead 拍板）**：`_release_zone` 撤销认输时**不重置** `rep.scope_shed`/`rep.scope_shed_tiles`（`brain/agentfarm/longrun.py:1153-1161`），R1 已断言"释放后 `rep.scope_shed_tiles>0` 而实时剔除集为空"。工具对「`scope_shed_tiles>0` + `verified=true`」一律判 problem ⇒ **雨天"先认输、后来雨把该区浇好并释放、当天其余活都做完"的诚实日会被误判为 needs_review**。修法二选一：脑侧释放时同步扣减快照；或工具侧把同日 `scope_released` 认作对冲。**不影响本次冻结**（正常跑批不触发；触发时是"诚实日被误判"，不是"坏日变好日"）。
- INFO-1：`day_end.scope_shed` 只记**当天那一次**认输；跨日粘住的区只在 `<journal>-scope.json` +journal `scope_loaded` 里（作者注释已说明，符合卡面字面）。复核历史账本时要同时看 scope 文件，否则会以为"累计上界只有 1 个区"。
- INFO-2：探针第一版 A6 只断言"守卫还有理由"，被 `live_crops_at_shed=1e9` 变异绕过 ⇒ 已加 A6b（人回室内后 farm 级干作物理由必须仍报"150 格"）。教训：**"理由非空"太弱，要断言"理由里那个数字对得上"**。
- INFO-3：`_harvest_zone`（`:1163`）在认输前先把该区成熟作物收掉（一轮有界、用 task-181 的 `tile_ready` 口径）⇒ 卡面未要求，属"不拔苗、不让收成烂在地里"的加分设计；我确认它不改判定与会计。
- 未判定项：**无**。卡面三条验收 + 九条通道 + 跨进程 + 工具侧全部可判。

## §7 复跑命令与原始读数

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"; Set-Location <repo>
# ① 冻结 post 树（= e56f2fc / 被 630e594 吸收）
$env:T185_ROOT = "<repo>\scratch\_t185_post"; & $py -W error::SyntaxWarning scratch\_t185_probe.py
# ② pre 树（无该特性 ⇒ 11 SKIP；该树工具为旧版 ⇒ T3 不可比）
$env:T185_ROOT = "<repo>\scratch\_t185_pre";  & $py -W error::SyntaxWarning scratch\_t185_probe.py
# ③ 变异矩阵（自建：拷冻结树 + 文本变异 + 同一套探针）
& $py -W error::SyntaxWarning scratch\_t185_mutate.py
# ④ 工具单测 / 全量
& $py -m unittest tests.test_verify_run3
& $py -W error::SyntaxWarning -m unittest discover -s tests
```

- `scratch\_t185_post_out.txt` ⇒ `PASS=50 FAIL=0 SKIP=0`。
- `scratch\_t185_pre_out.txt` ⇒ `PASS=3 FAIL=2 SKIP=11`（FAIL 为旧版工具的 T3a/T3b）。
- `scratch\_t185_mut_out.txt` ⇒ control `PASS=50 FAIL=0`，6 变异全杀。
- 探针 journal 与 scope 文件：`scratch\_t185_j\*`；变异树：`scratch\_t185_mut\<case>\`（每个 case 另存 `<case>.out.txt`）。

## §8 越界声明

本轮只写 `docs\_review-task168.md` 与 `scratch\_t185_*`；**未改** `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs\00-开发日志.md`、任务板；未跑真机、未装机、未 bump 版本；未使用网络。
