# 0.7.49 对抗验收（deputy-lead · T16）

- 日期：2026-10-19
- 角色：deputy-lead（对抗验收方）。只读生产代码；写范围仅 `docs/_review-*.md` + `scratch/`；不 deploy、不碰游戏、不改任务板。
- 立场：不信作者自述、不信回执。变异**必须**在 `git archive <ref>` 冻结树上实测复跑；缺失 ≠ 通过；判据用独立观测差分。
- 卡：T16（lead m00598）：①冻结树 provenance 双跑 ②变异独立复跑 ③`git show --stat` + `check-release --expect 0.7.49` ④D2 语义复核 ⑤D1 复核 → 产出本文档 + 闸口行。

## 0. 闸口结论（必答行）

**0.7.49 可否用于 A9 与目标1 裁决：放行**（附下述 3 条已知限制；见 §8）。

理由（全部为本会话实测读数，非引用作者）：

1. 冻结树 provenance 可复现，双跑逐字一致（§2）；
2. 8 把变异**全部 KILL（8/8）**，含 D1 口径回退、D2 记账回退、fail-closed 回退、硬编码留痕删除（§3）；
3. D1 三处判定点**全部**改用大障碍口径 `ZONE_BLOCKER_KINDS`，`clumpKind=="unknown"` 仍计 blocker（不 fail-open）（§6）；
4. D2 派发口径为 bool，**双买/重复申请实测被挡**；唯一新引入的是一个"记账漏记"的角落（§5.3），它**不会造假 PASS**、不在 A9 关键路径上，列入已知限制即可。

---

## 0.1 利益冲突声明（按 lead m00493 裁决）

P0 判据批（`0f72f3c`…`bbb6a89`，即 0.7.49 所冻结的 D1/D2 本体）经我审计，**作者身份不可判定、证据指向 deputy-lead 本人**（会话内就地补丁脚本交错 + `63bb3e0` 自述）。
Lead 裁决：保留代码、dev-coder 接管重交付；**独立验收方 = product-observer**；我的角色 = **二审** + 仅对 dev-coder **新增**部分做一审。
⇒ 本文对 D1/D2 **本体**的结论属二审性质，**不得作为唯一放行依据**；与 observer 结论必须逐数对齐（同一读数两边一致才成立）。

---

## 1. 冻结目标与 ref（读数）

| 项 | 读数 |
|---|---|
| 卡面冻结 ref（lead m00598） | `51ef0a7` `release(0.7.49): 冻结 P0 判据批（…bridge MOD_VERSION_EXPECTED + manifest + note）` — 3 files +37/−3 |
| 当前冻结指针（devlog 条目096 / `031c471`） | `daceb48` `docs(longrun): 更正 D2 注释——购买路径原本真的执行，缺陷在记账恒真（版本号 0.7.49）` — 1 file +6/−3 |
| 谱系 | `git merge-base --is-ancestor 51ef0a7 daceb48` → rc=0；`daceb48 -> HEAD` → rc=0（两者均在 `branch-opencode`） |
| 文件数 | `git ls-tree -r 51ef0a7` = **816**；`git ls-tree -r daceb48` = **822**（+6：我的 `9cfc424`、`f43ef30`/`a0f41e3` 两批测试、`607817f` 变异装置、`79ae4cc` 起跑清单） |
| `51ef0a7 → daceb48` 的 brain 差异 | `brain/agentfarm/bridge.py` 11 行、`brain/agentfarm/longrun.py` 9 行 —— **全部是注释/docstring**（逐行见 `git diff 51ef0a7 daceb48 -- brain/`）；`MOD_VERSION_EXPECTED` 两处均为 `"0.7.49"` |
| 字段不变 | `51ef0a7:brain/agentfarm/fields.py` git blob `3ceaa30544a0` == `daceb48:`（同 blob ⇒ §6 D1 读数对两个 ref 都成立） |

> 本报告两处 ref 都报：**`51ef0a7` = 卡面冻结树**；**`daceb48` = devlog 重指的当前冻结指针**。除注释外代码一致，故下述 D1/D2 结论对两者同样有效；变异与 provenance 以 `daceb48` 为准（我另在 `51ef0a7` 上复跑过一遍，读数见 §2/§3 注）。

---

## 2. ① 冻结树 provenance 双跑

**命令原文：**

```powershell
$env:PYTHONUTF8="1"; & C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe scratch\_t16_accept.py daceb48
```

（装置 `scratch/_t16_accept.py`：`git archive <ref>` → 解出临时树 → 记文件数 + 关键 blob SHA256 → 把 gitignored 的 `scratch/_ledger_*.jsonl` fixture 同步进导出树 → `cd <dest>/tests && python -m unittest discover -p "test_*.py"` 跑**两次**；判定只看 `Ran N / OK`。）

**读数：**

```
[provenance] git ls-tree -r 文件数 = 822 / [provenance] 解出文件数 = 822
[blob] brain/agentfarm/fields.py                git=3ceaa30544a0 sha256=5C8F0EA1B32341EF4AC28C2D110334609D8FDF6C28E38BE8B431E89EC126F45F
[blob] brain/agentfarm/longrun.py               git=3a9a7b178531 sha256=9A92BB9938352381BC240FD00F8D1FA968692B4A134BFF7CDB00DFAD1555C2B7
[blob] brain/agentfarm/bridge.py                git=edd178ed2963 sha256=8A3764333CA51C5B18DCF2176839703D99ABC14DAE6FC6134AD21BD04B48255C
[blob] tests/test_fields.py                     git=3452f354d580 sha256=5C261E0EE127CBE9D9FB95ABBAB4C0E8072F256D0FD6B2DF9BB045A9CB21F0BF
[blob] tests/test_longrun.py                    git=373703802606 sha256=C804E1A9EE5D1016B5D1C25F0FC9FB0008BA9D72558C0E94470478DD471A20FC
[blob] tools/verify-zone-retention.py           git=a962b250e03e sha256=7D12FF16B22327190916F8C32777B85433DB7C87732C2DBB631D6CD958C049FB
[blob] tools/_note-0749.txt                     git=b0daa5896c08 sha256=57511279D21B697B1E8E46F7E27919A849ADA37ACDD0FD5E4F39FFB048BBB32E
[blob] mod/AgentFarm.Bridge/manifest.json       git=25513981a340 sha256=66202D9F4CCBBCE5D4D37E89C9D80B6A50C5D1DC471B5652FCBFDA5DA2EFA694
```

**全量单测（冻结树，两次逐字一致）：**

```
[full#1] Ran 1396 / failures+errors=8 / OK=False / tail='FAILED (failures=2, errors=6, skipped=13)'
[full#2] Ran 1396 / failures+errors=8 / OK=False / tail='FAILED (failures=2, errors=6, skipped=13)'
```

8 条红**逐条归因（非产品问题，均为已知）**：

| # | 测试 | 类型 | 归因 |
|---|---|---|---|
| 1 | `test_analyze_longrun.TestSyntheticLedgers.test_fallback_ledger_is_flagged` | ERROR | gitignored fixture `scratch/_ledger_fallback.jsonl` 缺失 |
| 2 | `test_analyze_longrun.TestSyntheticLedgers.test_green_day_reports_nothing` | ERROR | `scratch/_ledger_green.jsonl` 缺失 |
| 3 | `test_analyze_longrun.TestSyntheticLedgers.test_leftover_but_verified_is_flagged` | ERROR | `scratch/_ledger_leftover_verified.jsonl` 缺失 |
| 4 | `test_analyze_longrun.TestTask17Probes.test_a8_old_ledger_guard_count_undecidable` | ERROR | `logs/longrun-runA8-0743.jsonl` 缺失 |
| 5 | `test_analyze_longrun.TestTask24ProbesAndRealLedgers.test_a8_new_aggregates_undecidable` | ERROR | `logs/longrun-runA8-0743.jsonl` 缺失 |
| 6 | `test_analyze_longrun.TestTask24ProbesAndRealLedgers.test_smoke_0744_new_aggregates_undecidable` | ERROR | `logs/longrun-smoke-0744.jsonl` 缺失 |
| 7 | `test_analyze_longrun.TestCliContract.test_json_mode_is_parseable` | FAIL | `AssertionError: 2 != 0`（#2 的 `scratch/_ledger_green.jsonl` 缺失 → CLI 退码 2） |
| 8 | `test_longrun.TestTask182ClumpRulesBehaviour.test_csharp_rules_self_test_passes` | FAIL | C# 自检码页假红（lead 卡面已声明：不带 `chcp 65001` 时假红） |

`51ef0a7` 另跑一遍：`Ran 1391 / failures+errors=7`（#8 偶发不出现——该码页假红**不稳定**，两次结果在 7/8 之间摆动），**同样是逐字双跑一致**。#8 是否出现不改变任何产品判据：它是 `Ran` 之外的码页问题，非业务断言。

**对照：主工作树**（含 logs/ fixtures，`cd tests && python -m unittest discover -p "test_*.py"`）：

```
Ran 1410 tests  →  FAILED (failures=1)
```

**结论**：冻结树缺 fixture 的 14 条在工作树上可跑（1396 + 14 = 1410）；工作树那 1 条红 = #8（码页假红）。**冻结树缺 fixture 属 `git archive` 的固有特性，不是产品缺陷**；但**验收以冻结树为准**，故 §8 把"fixture 未入库"列作已知限制（与 0.7.47/0.7.48 同口径）。

---

## 3. ② 变异独立复跑（我自己的实测）

### 3.1 我的装置（`scratch/_t16_accept.py`，MUTANTS 表逐字复制自作者 `scratch/_p0_d1d2_mutate.py`）

**基线：**

```
[baseline] 定向 Ran 18 / failed=0 / OK=True
```

**变异实测：**

```
[M1_f1_d1_zblocker_revert]                    KILL  Ran=13 failed=10
[M2_d2_buy_dict_truthiness]                   KILL  Ran=5  failed=1
[M3_zone_blockers_total_failclosed_returns_zero] KILL Ran=13 failed=3
[M4_upgrade_tool_journal_drop_hardcoded_axe]   KILL  Ran=5  failed=1
杀数 = 4 / 4
```

### 3.2 作者装置 `scratch/_patch3_mutate.py`（我独立复跑，不引用 Lead 读数）

```powershell
$env:PYTHONUTF8="1"; & <DSH python> scratch\_patch3_mutate.py
```

```
[tree] …\p3mut_u3gku88l\tree
[baseline] Ran 18 / failed=0 / OK=True
[M5_f1_zblocker_revert_new_shape]   KILL  Ran=10 failed=9
[M6_zone_total_truncated_not_failclosed] KILL Ran=13 failed=3
[M7_buy_plantable_early_return_removed]  KILL Ran=5 failed=1
[M8_buy_daily_cap_off_by_one]            KILL Ran=5 failed=1
杀数 = 4 / 4
```

> 注：卡面写的文件名 `scratch/_p0_d1d2_mutate.py` **在仓库中不存在**；真实存在的两台装置是 `scratch/_t16_accept.py`（我的，接受 `ref` 参数）与 `scratch/_patch3_mutate.py`（作者的，**硬编码 `git archive HEAD`**，见该文件 `:84`）。后者因此跑的是 HEAD 树 = `031c471`，其 `brain/` 与 `daceb48` 仅注释之差，不影响变异判定。

### 3.3 自报 vs 实测（两列）

| 变异 | 作者自报 | 我实测（冻结树） | 一致 |
|---|---|---|---|
| M1 ZONE_BLOCKER 回退 | killed | KILL Ran=13 failed=10 | ✅ |
| M2 buy dict 真值 | killed | KILL Ran=5 failed=1 | ✅ |
| M3 fail-closed → 0 | killed | KILL Ran=13 failed=3 | ✅ |
| M4 删硬编码留痕 | killed | KILL Ran=5 failed=1 | ✅ |
| M5 ZONE_BLOCKER（新形态） | killed | KILL Ran=10 failed=9 | ✅ |
| M6 total 截断不 fail-closed | killed | KILL Ran=13 failed=3 | ✅ |
| M7 plantable 早退删除 | killed | KILL Ran=5 failed=1 | ✅ |
| M8 每日上限 off-by-one | killed | KILL Ran=5 failed=1 | ✅ |
| 基线 | `Ran 13 failed=0`（Lead） | **`Ran 18 failed=0`** | ❌ 见下 |

**基线差异说明**：Lead 的 `Ran 13` 是在 `51ef0a7` 时刻测的；`f43ef30`(+3 fields) / `a0f41e3`(+2 longrun) 之后定向面变成 **18**。两台装置今天在冻结树/HEAD 树上都读到 **18**，故以 **18** 为准。**8/8 KILL 与 Lead 的 4/4 KILL 不冲突**（Lead 只跑了 M1–M4）。

---

## 4. ③ `git show --stat` + check-release 复核

```powershell
git show --stat --format="%H %s" 51ef0a7
```

```
51ef0a7ba4ca9d8f374eac337c5cfd22f93a011b release(0.7.49): 冻结 P0 判据批（D1 zone 大障碍口径 + D2 buy 派发真值 + 测试/变异；bridge MOD_VERSION_EXPECTED + manifest + note）
 brain/agentfarm/bridge.py          | 26 +++++++++++++++++++++++++-
 mod/AgentFarm.Bridge/manifest.json |  4 ++--
 tools/_note-0749.txt               | 10 ++++++++++
 3 files changed, 37 insertions(+), 3 deletions(-)
```

```powershell
$env:PYTHONUTF8="1"; & <DSH python> tools\check-release.py --expect 0.7.49
```

```
✅ manifest Version == brain MOD_VERSION_EXPECTED —— manifest=0.7.49 / brain=0.7.49
✅ 版本 == 期望值 0.7.49
✅ dll 不比源码旧 —— dll=09:29:00 / 最新源码=Skills.cs 20:26:30
✅ py_compile（35 个文件）
❌ 全量单测（Ran 1410 tests） —— FAILED (failures=1)
❌ 工作树干净（要提交的不能被漏掉） —— 12 项未提交：?? scratch/_patch_analyzer.py; ?? scratch/_t16_accept.py; …
结论：❌ 有红项，不要装机/不要起跑
RC=1
```

**逐条判读（缺失 ≠ 通过）：**

- ✅ manifest==brain==0.7.49 / py_compile / dll 时序：**通过**（可复跑）。
- ❌ 全量单测 `failures=1`：**是码页假红**（#8 `test_csharp_rules_self_test_passes`），冻结树双跑里它在 7/8 之间摆动 ⇒ 非产品红。**不能把"有红项"当作产品红，也不能把它当通过**：如实记为"需 `chcp 65001` 后复跑"。
- ❌ 工作树干净 12 项：**分属三个人**——`_patch_analyzer.py`=log-analyst 在制；`_t16_*`+`_t17dl_*`=我的；`_t17_*`=dev-coder 在制。**与 0.7.49 产品代码无关**，本卡收尾时我按路径提交我那部分。

---

## 5. ④ D2 语义复核（重点，独立复算）

### 5.1 现行代码（冻结树 + 工作树同 blob）

| 位置 | 原文 |
|---|---|
| `brain/agentfarm/longrun.py:429` | `MAX_BUY_TRIES_PER_DAY = 3` |
| `:7379` | `def _preconditions(self, obs, rep) -> dict[str, Any]`（返回**观测 dict**） |
| `:7393` | `if self._preconditions_apply(obs, rep):` ⇒ `_preconditions` **内部已调** `_preconditions_apply` |
| `:7402` | `def _preconditions_apply(self, obs, rep) -> bool` —— 返回"有没有真的改动世界" |
| `:7415` | `changed = False` |
| `:7422-7425` | `season_state = self._seed_season_state(obs)` / `plantable = int(season_state["plantable"]) if season_state["metadata"] else seeds_total` / `if plantable > 0: return False` |
| `:7492-7495` | `if self.buy_attempts_today >= MAX_BUY_TRIES_PER_DAY: rep.notes.append(…); return changed` |
| `:7539-7540` | 探测成功：`if st is not None and st.ok: return True` |
| `:7514` / `:7550` | 货架选中：`return changed or bool(st is not None and st.ok)` |
| `:9054` | **`changed = self._preconditions_apply(obs, rep)`** ← D2 修复点 |
| `:9060-9063` | `executed_steps=1 if changed else 0` / `reasons={} if changed else {"unknown_evidence": 1}` |
| `:9064` | `acted = changed or acted` |
| `:9835` | `obs = self._preconditions(obs, rep)`（主循环，卡面写的 `:9817` 是注释行） |
| `:7586` | `self.buy_attempts_today += 1`（两处门闸**共享同一计数器**） |

### 5.2 重复申请（双买）**真被修掉**？—— 是

实测（我的探针，见 §5.4）：

- 顺序 B（派发先买 → 主循环再调）：`buy_calls = 1`，不双买；
- 顺序 A（主循环先买 → 派发再调）：`buy_calls after main=1, after dispatch=1`，**仍不双买**；
- 6 轮强制派发后：`buy_attempts_today ≤ MAX_BUY_TRIES_PER_DAY(3)`。

机制：`:7424-7425` 的 `plantable > 0` 早退 + `:7492` 的共享每日上限。**两条门闸都共享 `buy_attempts_today`**，故两处调用点不会互相突破上限。作者新测试 `tests/test_longrun.py:15107 test_buy_dispatch_and_main_loop_do_not_double_order` 与 `:15130 test_buy_daily_cap_is_a_hard_stop` 正好钉这两条 —— 且 **M7（删 `plantable` 早退）/ M8（上限 off-by-one）均被杀**，证明该测试确有杀力（不是摆设）。

### 5.3 **引入新的假阴性？—— 是，1 处（新、实测、未被任何测试覆盖）**

**反序探针** `scratch/_t17dl_probe_mainloop_first.py`（作者的 `:15107` 只覆盖"派发先 → 主循环后"，我补测"主循环先 → 派发后"）：

```powershell
$env:PYTHONUTF8="1"; & <DSH python> scratch\_t17dl_probe_mainloop_first.py daceb48     # 修后
$env:PYTHONUTF8="1"; & <DSH python> scratch\_t17dl_probe_mainloop_first.py 93a71dc     # 修前（ee6bcc3^）
```

| 读数 | 修前 `93a71dc`（`changed = self._preconditions(obs, rep)`） | 修后 `daceb48` |
|---|---|---|
| 顺序 A `buy_calls after main / after dispatch` | `1 / 1` | `1 / 1` |
| 顺序 A buy 意图 `executed_steps` | **`1`** | **`0`** |
| 顺序 A `reasons` | **`{}`** | **`{'unknown_evidence': 1}`** |
| 顺序 A `_execute` 返回的 `acted` | **观测 dict（非 bool，恒真）** | `False` |
| 顺序 B `acted` | dict（恒真） | `True` |

**判读：**

1. 顺序 A 下**钱真的花了**（`money 5000 → 4800`，库存 `Parship Seeds ×10` 到手，`buy_calls=1`），但派发这一条 buy 意图被记 **`executed_steps=0` + `unknown_evidence` + `acted=False`** —— **新引入的记账漏记（under-credit）**。修前记 `1`（这一格上恰好"碰对"）。
2. 修前更糟且是类型错：`_execute` 返回的是**观测 dict**，`acted` 不是 bool（`acted = changed or acted` 里 `changed` 是 dict）⇒ 整个 `_execute` 的返回值在 buy 分支上恒真。**D2 顺带修掉了这个类型错**（修后是真 bool）。
3. **该假阴性不会造出假 PASS**：它是"漏记动作"而非"凭空记动作"；最坏后果是"真买了东西的那一天"在账上被记成 `unknown_evidence`，可能把"有进展"洗成"看起来没进展"，方向与旧 bug 相反、幅度更小。
4. **可达成性存疑**：生产主循环 `:9835` 在 `decide` **之前**买 ⇒ 决策层看到的是**买入后**的观测，通常不会再要 buy 意图 ⇒ 顺序 A 在全链路里未必跑得到。**但没有测试覆盖它**，故不能宣称"不可能"。
5. **`:7424-7425` 早退与 D2 是否矛盾**：不矛盾——它正是去重的实现；但它是"早退分不清『本轮已买』与『本来就有种子』"的**同一个原因**，即 §5.3 漏记的来源。
6. **`:9835` 冗余 `_preconditions` 是否矛盾**：不矛盾（task-143 硬性要求返回改动后观测）；但它是**第二个买入口**，其发生的购买**不归属任何 intent** —— D2 只修了派发路径的记账，主循环路径的 buy 目前**无人记账**。

> ⇒ 归入**已知限制 + 后续 dev 批次**（不返修、不重新冻结），建议补 1 条测试钉"主循环先买 → 派发不再下单也不误报 unknown_evidence"，或让主循环 buy 记一条 journal 归属 day 而非 intent。

### 5.4 无新的"该下单却被挡住"的假阴性（钱够的正常路径）

我的探针 `scratch/_t16_probe_d2.py`（对冻结树，rc=0）此前实测：

- A 钱够：`money 5000 → 4800`、`buy_calls=1`、`acted=True`、`steps=1`、`reasons={}` ⇒ **该下单的照下**；
- B 钱不够：`money 1 → 1`、`buy_calls=0`、`acted=False`、`steps=0`、`reasons={'unknown_evidence':1}` ⇒ **如实记账**；
- C 等价性：修前 `bool(_preconditions(...))` 与修后 `_preconditions_apply` **都只调 apply 一次** ⇒ 买侧副作用**逐字节等价**，差别的唯一来源是"记账"。

⇒ **没有引入"本该下单的 buy 现在被挡住"**（唯一挡住的是 `plantable>0`/钱不够/每日上限这三条**原有**门闸）。

---

## 6. ⑤ D1 复核（三处判定点 + unknown 口径）

`brain/agentfarm/fields.py`（`51ef0a7` 与 `daceb48` 同 blob `3ceaa30544a0`，读数通用）：

| 行 | 原文 |
|---|---|
| `:58` | `BLOCKER_KINDS = {weed, stone, twig, tree, bush}` |
| `:74` | `CLUMP_KIND = "clump"` |
| `:79` | `CLUMP_SUBKINDS = frozenset({"stump","log","boulder","rockPile","greenRain","unknown"})`（**只**用于可读原因） |
| `:83` | `ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS \| {CLUMP_KIND})` |
| `:379-380` | `if loc.get("tilesTruncated"): return None`（fail-closed） |

**三处判定点是否全部改用大障碍口径：**

| # | 判定点 | 行 | 原文 | 通过 |
|---|---|---|---|---|
| 1 | `zones_from_observe` 区内计数 | `:344` | `if tv.get("kind") in ZONE_BLOCKER_KINDS:` | ✅ |
| 2 | `zone_blockers_total` | `:386` | `if tv.get("kind") in ZONE_BLOCKER_KINDS:` | ✅ |
| 3 | `plot_in_zone` | `:529` | 同上口径 | ✅ |

**三处全部**用 `ZONE_BLOCKER_KINDS`（不是只有 `:386`）⇒ 通过。

**`clumpKind=="unknown"` 是否仍计 blocker（不许 fail-open）？—— 是。**

计数按 `kind` 值判，不按 `clumpKind` 判：Mod 给 tile 的 `kind` 恒为字面量 `"clump"`（`mod/AgentFarm.Bridge/WorldSnapshot.cs:807`；`Contracts.cs:590` 列 `clump`、`:598` 只有 `kind=="clump"` 才填 clump* 元数据），而 `ClumpMeta.cs:39-73` 的 `KindOf` **永不返回** `"clump"`、只给子类型（含 `"unknown"`）。⇒ 无论 `clumpKind` 是什么（含 `unknown`），tile 都因 `kind=="clump"` 落进 `ZONE_BLOCKER_KINDS` ⇒ **无 fail-open 路径**。

**独立复算装置** `scratch/_p0_blk_recount.py`（此前实测 rc=0）：175 份含 tiles 的 observe、388 条按区断言、**不符 = 0**、fail-closed(`None`) = 344、过期夹具文件 = 1 ⇒ 证明"新口径 − 旧口径"恰等于 clump 数（不是碰巧相等）。

---

## 7. 三方一致性（repo / bin / 装机）

```powershell
foreach ($p in @("mod\AgentFarm.Bridge\manifest.json",
                 "mod\AgentFarm.Bridge\bin\Release\manifest.json",
                 "<game>\Mods\AgentFarm.Bridge\manifest.json")) { … }
```

| 位置 | 大小 | Version | SHA256 |
|---|---|---|---|
| 仓库工作树 `mod/AgentFarm.Bridge/manifest.json` | **82951 B** | **0.7.49** | `FC2B02DE1F2146F079FAFF1A90FD9457D2DFD41337315BB41FA4283B27292BA9` |
| `mod/AgentFarm.Bridge/bin/Release/manifest.json` | **82951 B** | **0.7.49** | `FC2B02DE…292BA9`（**与仓库工作树逐字节一致**） |
| 已提交 blob（`HEAD` / `51ef0a7` / `daceb48` 同） | 82937 B(LF) | 0.7.49 | git `25513981a340`（工作树 CRLF 之差，同 0.7.47 的 10 B 现象） |
| **装机** `…\Stardew Valley\Mods\AgentFarm.Bridge\manifest.json` | **79305 B** | **0.7.48** | `45B27C848910C8F860F842E5AB1424CD207AEC83F833C6B7D3452713E4F69071` |

| DLL | 大小 | SHA256 |
|---|---|---|
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | **293888 B** | `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A` |
| **装机** `…\Mods\AgentFarm.Bridge\AgentFarm.Bridge.dll` | **293888 B** | `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A` |

**判读（如实）：**

1. **DLL 三方一致**：bin/Release == 装机，且与 0.7.47 / 0.7.48 记录的同一哈希**逐字节相同**（本批改动全在 Python 侧，dll 未重编或重编出同哈希产物）。
2. **manifest 二方一致、一方滞后**：仓库 == bin/Release == `0.7.49`；**装机仍是 `0.7.48`** ⇒ **`--expect 0.7.49` 的 preflight 对装机目录会失败，这是"尚未部署"的预期状态，不是缺陷**；但也**不能**写成"装机已就绪"。部署时只需把 `manifest.json`（82951 B）随同 dll 一并拷过去。
3. `check-release --expect 0.7.49` 的 ✅/❌ 只覆盖**仓库**，不看装机目录 ⇒ 不得把它的 ✅ 当作"装机一致"的证据。

---

## 8. 已知限制与缺口（如实，不得当通过）

| # | 项 | 性质 | 影响 | 处置 |
|---|---|---|---|---|
| L1 | 顺序 A 记账漏记：主循环先买 → 派发 buy 记 `executed_steps=0` / `unknown_evidence` / `acted=False`（§5.3，实测 `1→0`） | **新**（D2 引入） | 不造假 PASS；可能把"真买了的一天"记成无动作 | 后续 dev 批次 + 补测试；本轮不返修 |
| L2 | 主循环 `:9835` 的 buy **不归属任何 intent**（无人记账） | 旧有 | 账本上缺一条 day 级 buy 归属 | 与 L1 同批处理 |
| L3 | `upgrade_tool` 工具种类**硬编码 `"axe"`**（`longrun.py:9066-9085`） | 已声明限制 | 铜斧链之外的升级不可用 | 0.7.48/0.7.49 已知限制，本轮不改 |
| L4 | 冻结树 `git archive` 缺 14 条 fixture 依赖测试 ⇒ `Ran 1396 / FAILED(7~8)` | 工具/入库问题 | 冻结树**不能**读成"全绿" | 如实记录；验收看归因（§2 表） |
| L5 | C# 自检码页假红 `test_csharp_rules_self_test_passes` **不稳定**（`51ef0a7` 双跑 7 条、`daceb48` 双跑 8 条） | 环境 | `check-release` 固定报 `failures=1` ⇒ rc=1 | 需 `chcp 65001` 后复跑；不得据此判产品红或产品绿 |
| L6 | `check-release` ❌ 工作树干净（12 项未提交） | 制度 | 分属 log-analyst / 我 / dev-coder，非产品代码 | 本卡收尾我按路径提交我的 6 个文件 |
| L7 | `tools/_note-0749.txt:4` 自报"测试 +11 条（fields +8 / longrun +3）/ 全量 Ran 1405"，**实测 +13（fields +10 / longrun +3）** | 自报不准（偏少） | 无害（实际测试更多） | 记录；note 属 lead 文档，我只读不改 |
| L8 | 我对 P0 本体存在利益冲突（§0.1） | 制度 | 不得独占放行 | 需 observer 独立验收对数 |

---

## 9. 闸口与待办

- **0.7.49 可否用于 A9 与目标1 裁决：放行**（L1/L2 记入已知限制；L5/L6 需在起跑前按 §9 清掉；L8 需 observer 对数）。
- **起跑前必须满足**（否则 `check-release` 仍 rc=1）：
  1. 工作树按路径提交各人自己的产物（我提交 6 个：`docs/_review-0.7.49.md`、`scratch/_t16_accept.py`、`scratch/_t16_cmp.py`、`scratch/_t16_diff_ids.py`、`scratch/_t16_probe_d2.py`、`scratch/_t17dl_probe_mainloop_first.py`）；`_patch_analyzer.py`(log-analyst)、`_t17_*`(dev-coder) 不动。
  2. `chcp 65001` 后复跑 `check-release --expect 0.7.49`，确认全量单测那条红仅剩 fixture 类。
  3. 装机 manifest 需从 `0.7.48` 更新到 `0.7.49`（82951 B）；dll 无需改（哈希同）。
- **冻结后待跑项**：本文 §2/§3 的所有读数均在 `51ef0a7` / `daceb48` 冻结树上完成；若 `brain/` 或 `tests/` 再变，**须整体重跑**（`scratch/_t16_accept.py <new-ref>` + `scratch/_patch3_mutate.py`）。

---

## 附：本卡新增产物

| 文件 | 用途 |
|---|---|
| `scratch/_t16_accept.py` | 冻结树 provenance 双跑 + M1–M4 变异（接受 ref 参数） |
| `scratch/_t16_cmp.py` | archive 与工作树全量单测输出对照 |
| `scratch/_t16_diff_ids.py` | archive / 工作树测试 ID 差集 |
| `scratch/_t16_probe_d2.py` | D2 真买等价探针（钱够/钱不够/等价） |
| `scratch/_t17dl_probe_mainloop_first.py` | **D2 反序（主循环先买）对抗探针** —— 修前/修后对照 |
| `docs/_review-0.7.49.md` | 本文档 |
