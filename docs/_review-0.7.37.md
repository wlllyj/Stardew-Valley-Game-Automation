# 0.7.37 批次独立对抗验收（task-200）

- 验收人：deputy-lead（独立对抗验收，只读生产码 + 只写 `docs/` 与 `scratch/`）
- 批次卡：task-198（背包满 = 全局阻塞 `no_slot` + 腾格收敛 + 诚实 `inventory_blocked` 收尾）、
  task-199（`readyTiles` 与 `readyCrops` 同源 + 走不到不空转）、task-195（`use_tool` 证据绑目标格 +
  原始技能不静默连带）、task-196（`loot`/`collateral_loot` 分栏 + 附带掉落不进白名单）、
  task-197（自检输出编码护栏）、task-193（analyzer 归因收紧，log-analyst）
- 纪律：**在制工作树只作线索，判定一律在 `git archive <commit>` 冻结树上做**；变异矩阵亲自实测并给
  「自报 vs 实测」两列；不许把"没测到"写成"通过"；不碰游戏/桥/生产码/任务板；本批不 bump。
- 原始读数：`scratch/_t200_post198.txt`、`scratch/_t200_pre198_force.txt`、`scratch/_t200_base198_suite.txt`、
  `scratch/_t200_mut198a.txt`、`scratch/_t200_mut_<变异名>.txt`、`scratch/_t200_198_nit.txt`；
  探针 `scratch/_t200_probe.py`、建树 `scratch/_t200_trees.py`、变异 `scratch/_t200_mutate.py`。

## §1 A 段：范围与读数

- 验收基线 HEAD：`0d076c0`（docs: 0.7.37 进度，task-198 收口）；本批第一个交付提交 = `62e9089`。
- `git show --numstat 62e9089`：**恰 4 文件 +733/−18** —— `brain/agentfarm/farmwork.py` +29/−5、
  `brain/agentfarm/longrun.py` +291/−8、`tests/test_farmwork.py` +61/−2、`tests/test_longrun.py` +352/−3
  （与卡面/作者自报一致，无越界：`mod/`、`tools/`、`manifest.json`、`bridge.py`、`logs/`、`docs/00-开发日志.md` 零命中）。
- 冻结树 `scratch/_t200_post198`（= `62e9089`）关键文件 SHA256 前 16：
  `farmwork.py B5712736683B1FB5`（176260 B）、`longrun.py 2D2AE2AA55B59EF8`（443228 B）、
  `test_farmwork.py E539A1BEFD14D1A9`（159478 B）、`test_longrun.py 15B583FCAFD30D34`（543213 B）、
  `manifest.json A1F83040F6706C82`（53251 B）、`bridge.py 968D1D227A293B1A`（51696 B）。
- 版本：`manifest.json "Version": "0.7.36"`、`bridge.py MOD_VERSION_EXPECTED = "0.7.36"` ⇒ **本批未 bump**（符合要求）。
- `py_compile -W error::SyntaxWarning`（farmwork/longrun/planner/bridge）：exit 0。
- 定向 `tests.test_farmwork tests.test_longrun`：**Ran 484 / OK**（与作者自报一致）。
- 全量 `PYTHONUTF8=1 python -m unittest discover -s tests`：
  - **在 `62e9089`（task-198 交付点）：Ran 986 / FAILED (failures=2)**，唯二红 =
    `tests/test_analyze_longrun.py::TestBagSpaceDeadlock::test_mechanical_enumeration_has_no_unmapped_event`
    与 `TestEventMappingDrift::test_event_buckets_cover_every_brain_journal_name`
    （`inventory_blocked`/`slot_relief`/`slot_relief_noted` 桶漂移）⇒ 交付时已知、归 analyzer 侧；
    该两红也是后续变异实测的**基线 2 条**（`scratch/_t200_base198_suite.txt` 亲测 = 2）。
  - **在 `f2e72e3`（task-202 = analyzer 收录版，冻结树 `scratch/_t200_202`）：Ran 992 / OK（0 红）**
    ⇒ 上述 2 红已由 task-202 消除，**不再构成 0.7.37 的门**；读数 `scratch/_t200_202_suite.txt`。
- A 段不变量：`day_end` 无新键、`checks` 仍 10 键（`slept_by_us/no_blocking_modal/no_hard_failures/
  unreachable_within_bound/refused_within_bound/no_unmet_stages/crops_watered/watered_outdoor/day_justified/
  zero_action_evidenced`）、`JUSTIFIED_END_REASONS = ("night","stamina","no_work")` 未变 ⇒ 未新增可洗白入口。

## §2 task-198：背包满 = 全局阻塞（`no_slot`）

**判定：PASS-WITH-NITS**（无阻塞项）。

### §2.1 冻结树 pre/post（FAIL→PASS）

| 树 | 来源 | marker | 读数 |
|---|---|---|---|
| `scratch/_t200_pre198` | `62e9089^` | `198=0/3` | `PASS=6 / FAIL=15 / SKIP=14`（`T200_FORCE=1`） |
| `scratch/_t200_post198` | `62e9089` | `198=3/3` | `PASS=24 / FAIL=0 / SKIP=4` |

post 树 SKIP=4 是 task-199/195/196 未交付 + task-197 全量套件被 `T200_SKIP_SUITE=1` 跳过（197 在 §6 单列）。

pre 树原文（交付前缺陷，可与 dev-coder 交付前必修项对齐）：

- `198a-1`：`code=failed status='' no_slot=None`（满包失败和普通失败不可区分）
- `198a-2`：`env_block=False statuses=('no_save','ui_modal','world_fading','busy')`
- `198a-3`：`tile_attempts` `{}` → `{(61,11):1}`（no_slot 吃每格配额、会封格）
- `198a-4`：`harvest_gave_up=[(61,11)]`（no_slot 吃 gave_up 上限）
- `198b-1`：`failed_steps=4`、`stages=[('harvest',2,0),('harvest',2,0)]`、`no_hard_failures=False`
- `198b-3` / `198f-2` / `198f-8`：收尾 = `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：农场口径还有 1 格熟作物（当前窗口没盖到，别处还有活），先去收）`
- `198f-1`：`freed=0 relief=[]`；`198f-3`：`failed_steps=14`；`198f-4`：`no_work:确实找不到可做的活（…）`（假绿形态）
- `198c-1`：`relief=[]` + `AttributeError: 'LongRun' object has no attribute '_slot_relief'`（pre 树无该接口，属预期）

### §2.2 A′ 原型复现通道（Lead m08246 的正式冻结判据）

照 `logs/longrun-runA3-0736.jsonl` day13 的真实形态（满包 + 多格熟作物）构造假世界，判据见
`docs/_release-0.7.37.md` §3。post 树 8 条全绿（`198f-1..8`）：满包 + 8 熟 + 可腾 ⇒ `slot_relief.freed>=1`；
满包且腾不出 ⇒ `inventory_blocked` 收尾；低水位（1 空格 + 8 熟）⇒ 不再白撞 `no_slot`；三种形态下
**均不出现** `stuck:…守卫仍说还有活`，且 `failed_steps=0`、`verified=False`、不洗 VERIFIED。

### §2.3 变异实测（自报 vs 实测）

净杀数 = 实测 `FAIL:`/`ERROR:` 行数 − 基线 2（analyzer 桶漂移）。全部 kind=`suite`（全量套件），
在 `scratch/_t200_post198` 的副本上打文本变异后跑。

| 变异（dev-coder 原文） | 自报 | 实测(净) | 判定 |
|---|---|---|---|
| m198a 腾格回路失效（`_bag_state` 后 `if True: return False`） | 10 | **10** | 相符 |
| m198b `failed_any` 去掉 `no_slot` 过滤 | 4 | **4** | 相符 |
| m198c 守卫熟作物条件去掉 `and not bag_blocked` | 2 | **2** | 相符 |
| m198d `_count_attempts` 的 no_slot 分支改 `if False:` | 1 | **1** | 相符 |
| m198e 低水位退回 `free_slots <= 0` | 2 | **2** | 相符 |
| m198f 守卫 `inventory_blocked` 分支改 `if False:` | 3 | **3** | 相符 |
| m198g `day_justified` 加 `or rep.ended_by == "inventory_blocked"` | 1 | **1** | 相符 |

我另加 2 条自建变异（probe kind，验 A′ 通道灵敏度）：`env_block` 摘除 ⇒ **1 杀**（`198a-2`）；
满包判定失效 ⇒ **2 杀**（`198a-1`/`198a-2`）⇒ A′ 通道不是空转。

### §2.4 NIT / 观察项

- **NIT-1（不阻塞，已知归口）**：全量 2 红是 analyzer 桶漂移（`inventory_blocked`/`slot_relief`/`slot_relief_noted`），
  归 task-193；本批交付后 analyzer 未同步 ⇒ **在 task-193 落地前，全量不是 0 红**。
- **NIT-2（不阻塞，语义提醒）**：`inventory_blocked` 日 `stages[].env_block` 会把同一轮的 `no_slot` 步数全部累计
  （我实测 N1 = 21、N2 = 24），`stage.leftover` 如实保留（7/8 格），`_leftover("harvest")` 亲测非空、
  `checks.no_unmet_stages=False`、`failed_steps=0`、`verified=False` ⇒ **没有洗白**；但 `env_block` 计数容易被误读成
  "环境挡路 N 次"，建议后续在 journal 里区分 `no_slot` 与其它 env 挡路（非本批卡面要求）。
- **INFO-1**：`inventory_blocked` 是"背包堵住，不是没活/不是 stuck"的诚实收尾（原文见 §2.4 之外读数）；
  `slept_by_us` 仍 True、`day_justified=False`。

## §3 task-199：`readyTiles` 与 `readyCrops` 同源 + 走不到不空转（待交付）

（占位，交付后补 pre/post + 变异 + 判定）

## §4 task-195 / task-196：`use_tool` 证据绑目标格 / 附带掉落分栏（待交付）

（占位，交付后补）

## §5 task-193：analyzer 白名单归因收紧（待交付）

（占位，交付后补；本批全量 2 红即该项）

## §6 task-197：自检输出编码护栏（待正式判定）

- 已冻结 `scratch/_t200_base`（`0dd5465`）基线读数：**197a 带 `PYTHONUTF8=1` ⇒ `Ran 970 / OK`**；
  **197b 不带 ⇒ 唯一红 = `test_csharp_rules_self_test_passes`**（pre 病态已复现）；197c 注入 cp1252 ⇒ 同一红；
  197d（只看该用例方法体内是否 `SELFTEST_OK`/`encoding="utf-8"`）⇒ PASS。
- 待 task-197 交付后在 `git archive` 冻结树复跑 a/b/c 三形态。

## §7 结论（待全批交付后落）

- 当前：task-198 = PASS-WITH-NITS；其余卡未交付。**0.7.37 可否冻结：待定**。
