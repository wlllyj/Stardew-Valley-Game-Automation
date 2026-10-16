# task-125 独立对抗验收：0.7.29 批次（task-121 / 122 / 123 / 124）

- 验收人：deputy-lead（独立验收，只读生产代码，只写 `docs/` + `scratch/`）
- 日期：2026-10-16
- 对象：`9a4da64`（task-121 复盘预算）、`affa7c8`（task-122 教训覆盖）、**task-123 未交付**、`08a2ae0`（task-124 review-only 兜底）
- HEAD：`be7f2d4`（我上一张卡 task-128 的收尾提交；开工时 `git status --short` 干净）
- 探针：`scratch/_t125_probe.py`；post 树读数 `scratch/_t125_probe_post.txt`（**40/40 PASS**，exit 0）；pre 树读数 `scratch/_t125_probe_pre.txt`（**22/34 PASS**，exit 1）
- pre 树：`git archive 9a4da64^`（=`c775817`，0.7.29 发布计划）→ `scratch/_t125_pre/`（376 文件），`brain/agentfarm/planner.py` SHA256 前 16 = `B69382C1EBD19D35`；已确认缺三特性（`REVIEW_RETRY_MAX_TOKENS` / `_review_only_fallback` / `stuck_with_leftover` 全 0 命中）

---

## §1 一句话判定

**0.7.29 不可放行冻结。**

- task-121（复盘预算阶梯）、task-122（教训覆盖两种新 kind）、task-124（review-only 兜底）三段 **PASS-WITH-NITS，无必修项**：探针在 post 树 40/40 PASS，且三个特性在 pre 树上逐条 FAIL→post 树 PASS（§4）。
- **task-123（部分购买）FAIL / 阻塞：根本没有交付**（§3.3）——`brain/agentfarm` 全文 `buy_partial` 0 命中，板面仍是 `pending`，而 `docs/_release-0.7.29.md` §1 当时把它标成 ✅（Lead 已用 `ad1f51d` 更正为 ❌）。
- 另有 **task-129（P0 落盘修复）未落地**，两者都是 0.7.29 的硬闸门 ⇒ 交付后再做 delta 复验。

---

## §2 A 段 范围与读数（我亲跑）

三提交的 `git show --stat`（越界扫描正则 `^mod/|^tools/|manifest.json|bridge.py|^logs/|00-开发日志` 全部 **0 命中**）：

| 提交 | 文件数 | 增删 | 明细 |
|---|---|---|---|
| `9a4da64` task-121 | 4 | +168/−47 | `brain/agentfarm/longrun.py` +10、`brain/agentfarm/planner.py` +116、`tests/test_longrun.py` +48、`tests/test_planner.py` +41 |
| `affa7c8` task-122 | 3 | +161/−0 | `brain/agentfarm/longrun.py` +31、`brain/agentfarm/planner.py` +4、`tests/test_longrun.py` +126 |
| `08a2ae0` task-124 | 2 | +357/−1 | `brain/agentfarm/longrun.py` +172、`tests/test_longrun.py` +186/−1 |

SHA256 前 16（作者未自报这三个值，以下是我的读数）：

```
brain/agentfarm/planner.py    ED710CA671CD4A02
brain/agentfarm/longrun.py    45C6298010A3AB23
tests/test_longrun.py         D91AB36C4ACD2820
tests/test_planner.py         A242AB7CA6450C39
```

读数：

- `python -W error::SyntaxWarning -m py_compile brain/agentfarm/planner.py brain/agentfarm/longrun.py brain/agentfarm/farmwork.py brain/agentfarm/bridge.py` ⇒ **exit 0**（注意 `-W` 必须在 `-m py_compile` 之前）
- `python -m unittest tests.test_farmwork tests.test_longrun tests.test_planner` ⇒ **Ran 407 tests / OK**（与 Lead 的 407 一致）
- 全量 `python -m unittest discover -s tests` ⇒ **Ran 707 tests / FAILED (failures=2)**，两条红都在 `tests/test_analyze_longrun.py`：`TestBagSpaceDeadlock.test_mechanical_enumeration_has_no_unmapped_event`、`TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name`（task-124 的 4 个新事件未进桶，归 log-analyst 的 **task-130**）⇒ **与本批次无关的已知红，我没有把它算成批次 FAIL，但全量不是绿的**。原文：`scratch/_t125_targeted.txt`、`scratch/_t125_full.txt`
- `scratch/_t45_run_matrix.py` 的 `pos-G-one-day-no-save` 期望已按 task-128 新口径由 `0` 改为 `1`（提交 `be7f2d4`），矩阵复跑 **exit 0 / 10 例全部符合期望**（`scratch/_t128_after_matrix2.txt`）

---

## §3 A 段 逐条对账

### 3.1 task-121 复盘预算阶梯 — **PASS-WITH-NITS**

- `REVIEW_MAX_TOKENS = 4096`（`brain/agentfarm/planner.py:417`）、`REVIEW_RETRY_MAX_TOKENS = 8192`（`:419`），预算阶梯实现 `:1728-1752`：只当异常 `status == "truncated"` 且还有更大预算时才 `continue`（`:1745-1746`），最多 2 次；返回字典带 `attempts` / `max_tokens`。
- 实测（B3a/B3b/B3c）：截断 ⇒ **2 次调用、budgets `[4096, 8192]`**、journal `review_llm` 带 `attempts=2 / max_tokens=8192`；网络异常 ⇒ **1 次调用**，只记 `review_llm_failed`；两次截断 ⇒ 2 次调用后放弃，note"复盘失败无害：睡觉与跨日照常"。
- NIT：无必修项（见 §6 N2 的时钟/计数说明不适用本段）。

### 3.2 task-122 教训覆盖 — **PASS**

- 新 kind `stuck_with_leftover`：`ended_by` 以 `stuck` 开头 + leftover>0 + failed=0 ⇒ 实测 1 条，`symptom='clear_dead 收尾时还剩 2 格没做成、当天以 stuck 结束'`、`evidence='leftover=2 failed=0 stopped=budget'`（B2a，pre 树 `kinds=[]`）。
- 新 kind `plot_exhausted`：12 次换片 ⇒ 1 条；1 次换片 ⇒ 0 条（B2b）。
- 干净 VERIFIED 日 ⇒ 两种新 kind 均 0 条（B2c）。
- 判定不受影响：开关教训生成、以及塞满 20 条伪造"已解决"教训 ⇒ `canon`（`verified/day_justified/ended_by/checks/final_water(剔 t)/final/stages/intents`）逐字相同；真失败日伪造库也洗不白（`verified=[False] ended_by=['stuck']`，C3a/C3b/C3c）。

### 3.3 task-123 部分购买 — **FAIL / 阻塞（未交付）**

- `team_task_list` 里 task-123 = `pending` / `ready=true` / **无 owner**。
- `git grep -n "buy_partial" -- brain tests` ⇒ **零命中**；`git log -S "buy_partial"` 只命中说明性文件（`c775817` 发布计划、`0a216c2` 冻结 note）⇒ 代码里不存在这条路径。
- 卡面 C⑤ 的后两条（"钱 `=price*3`、`buy_count=10` ⇒ 买 3 个记 `buy_partial` 且不进 failed"、"货架价 0/缺价 ⇒ 不许除零/当免费买"）**第一条无法验收**，第二条我已在 `FW.pick_seed_offer` 层面验证通过（货架价 0 或缺价 ⇒ `pick=None code=cannot_afford`；钱 < 价 ⇒ `cannot_afford` 且不抛，C5b/C5c）。
- 口径不一致（release doc / 板面 / 派工信三处）：`docs/_release-0.7.29.md` §1 当时把 task-123 标 ✅（且 121/124/126 漏 hash，只有 task-122 写了 `affa7c8`）；**Lead 已提交 `ad1f51d` 更正**（task-123 标 ❌ 未交付）。⇒ 记 NIT-1（已闭环）。

### 3.4 task-124 review-only 兜底 — **PASS-WITH-NITS**

- 关口原文 `brain/agentfarm/longrun.py:3948-3949`：`if (self._is_review_only(decision) and self.work_reasons(obs) and (self._work_spot_plot(obs) is not None or self._pending_work())):`；兜底 `_review_only_fallback`（`:2052-2112`）用**守卫据以抱怨的那份 leftover**（`leftover_targets` / `_pending_work()` / `_work_spot_plot`），不是另算一份 ⇒ 对账成立。
- 触发条件实测澄清（重要）：**看得见**的活由政策层直接换成真意图（journal `policy` 原文「政策把 ['water_area'] 提到最前（原顺序 ['review']）」，`intents=[['water_area','review']]`），`_is_review_only` 为 False ⇒ 兜底**不触发**；兜底真正管的是**指不出格**的跨片地 leftover（B1a vs B1b）。
- 有界性：`_abandon_guard_leftover` 后守卫抱怨消失（`before=['今天早些时候还有 2 格没做完（跨片地，最近的是 [70, 20]）']` → `after=[]`，C2），不会无限重试。
- `plot_exhausted_burst`（`longrun.py:2035-2050`，阈值 `PLOT_EXHAUSTED_BURST = 5`，`:101`）：同秒 12 次 ⇒ `seq=1..12`，跨秒（10.0 → 12.0 → 12.1）⇒ 归零后 `[1, 2]`；burst 日仍 `verified=False`（C4）。

---

## §4 B 段 FAIL→PASS 对照（pre 树 `9a4da64^` vs post 树 HEAD）

| 用例 | pre 树 | post 树 |
|---|---|---|
| **B1b** 只有跨片地 leftover（看不见）+ `weeds=4` | 无任何 `review_only_*`；`ended_by=stuck`，理由 `stuck:连续 3 轮世界没有任何变化（最后意图：['review']；策略说有进展：False）；守卫仍说还有活：今天早些时候还有 1…` | `review_only_fallback{source:"pending_walk"}` ×10 + `review_only_no_target` ×4；`farm_actions_today=4`；`ended_by=sleep` |
| **B2a** stuck + leftover + failed=0 | `kinds=[]` | 1 条 `stuck_with_leftover`（symptom/evidence 见 3.2） |
| **B2b** 12 次换片 | n=0 | n=1（1 次换片仍 0 条） |
| **B3a** 截断自愈 | 无 `REVIEW_RETRY_MAX_TOKENS`，1 次调用即失败 | 2 次调用，budgets `[4096, 8192]`，`review_llm{attempts:2, max_tokens:8192}` |
| **B3c** 两次截断 | 1 次调用 | 2 次调用 + `review_llm_failed{attempts:2, max_tokens:8192}` |
| **C2/C4** | `AttributeError: 'LongRun' object has no attribute '_abandon_guard_leftover'` / `'_plot_exhausted_burst'` | 全部 PASS |

合计：pre **22/34** → post **40/40**。

---

## §5 C 段 对抗矩阵（6 组，post 树实测）

1. **兜底不许把"真没活"变成乱动**：`work_reasons()` 指不出格时 `review` 照常执行 15 次，`review_only_fallback` 0 次、`review_only_no_target` 0 次（C1）⇒ 兜底不会凭空造活。
2. **兜底不许死循环**：不可定位 leftover 走 `review_only_no_target`，`leftover_targets` 清空、`_pending_work()==[]`、守卫抱怨消失（C2）⇒ 有界。
3. **教训不得洗白判定**：开关生成 / 满库伪造"已解决" / 真失败日 ⇒ `canon` 逐字相同，`verified=false` 洗不成 true（C3a/C3b/C3c）。
4. **`plot_exhausted` burst 有界**：同秒计数 1..12、跨秒归零、burst 日诚实不 VERIFIED（C4a/C4b/C4d）；日级 `plot_exhausted_burst` 事件 ≤1（C4c 该变体实测 0 条，因 burst 是指针直调）。
5. **部分购买不许掩盖买不到**：`buy_partial` **不存在 ⇒ 阻塞**（C5a）；货架价 0/缺价 ⇒ `pick=None code=cannot_afford`；钱 < 价 ⇒ `cannot_afford` 且不抛（C5b/C5c）。
6. **复盘重试不得污染判定**：网络异常 / 空返回 / 两次截断三形态，与关闭机制逐字相同、退出码全 0（C6a–C6d）。

---

## §6 NIT 表

| # | 现象 | 行号/证据 | 是否阻塞放行 |
|---|---|---|---|
| NIT-1 | task-123 三处口径不一致：`docs/_release-0.7.29.md` §1 把未交付的 task-123 标 ✅（并漏 121/124/126 的 hash），板面是 `pending`，代码 0 命中 | `ad1f51d`（Lead 已更正）；`git grep buy_partial` 0 命中 | **是**（属 task-123 阻塞的一部分，已由 Lead 更正文档） |
| NIT-2 | 本批次无作者自报 SHA256（121/124 只有提交号），我只能记录自己的读数 | `planner.py ED710CA671CD4A02` 等 | 否 |
| NIT-3 | 全量不是绿的：707 tests / 2 红（两条都是 task-124 新事件未入 analyzer 桶） | `scratch/_t125_full.txt`；task-130 在修 | 否（与本批次代码无关，但放行前必须绿） |
| NIT-4 | `review_only_fallback{pending_walk}` 一次失败日可累计 10 次（由 `resume_walks` 上限与 `review_only_no_target` 收尾兜住） | C2 有界性实测 | 否 |
| NIT-5 | `_plot_exhausted_burst` 判据用墙钟差值（`stamp - last >= 1.0`），时钟回拨会重置计数（只影响教训条数，不影响判定） | `longrun.py:2035-2050`；C4b | 否 |

---

## §7 复跑命令

```powershell
Set-Location "<repo>"
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:PYTHONPATH="$PWD\brain"

# post 树（当前 HEAD）
& $py -W error::SyntaxWarning scratch\_t125_probe.py *> scratch\_t125_probe_post.txt

# pre 树（FAIL→PASS 对照）
if (-not (Test-Path scratch\_t125_pre)) {
  git archive --format=tar -o scratch\_t125_pre.tar 9a4da64^
  New-Item -ItemType Directory -Force scratch\_t125_pre | Out-Null
  tar -xf scratch\_t125_pre.tar -C scratch\_t125_pre; Remove-Item scratch\_t125_pre.tar
}
$env:T125_ROOT="$PWD\scratch\_t125_pre"
& $py -W error::SyntaxWarning scratch\_t125_probe.py *> scratch\_t125_probe_pre.txt
Remove-Item Env:\T125_ROOT
```

注意：取证时**不要**在 `Tee-Object` 之后接 `Select-Object -First N`，上游早停会把 tee 出来的文件截断（我第一轮就踩了这个坑）。

---

## §8 结论与放行建议

- **task-121 / task-122 / task-124：PASS-WITH-NITS，无必修项**（三个特性的 FAIL→PASS 对照都在 §4，判定零影响在 §5-C3/C6 钉住）。
- **task-123：FAIL / 阻塞（未交付）**。
- **放行判定：0.7.29 现在不可放行冻结** —— 等 task-123 交付，且 task-129（P0 落盘修复）落地、全量测试转绿（task-130 收尾）之后，再做一次 delta 复验（届时开卡给我即可）。
