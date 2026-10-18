# 0.7.43 delta（task-242：clear_area 逐格证据记账完整性）独立对抗验收

> 状态：**正式判定已收口**（2026-10-18，事后收口；前任 Lead 会话 15:08 因上下文硬顶死亡，task-244 由 deputy 在冻结树上重跑全部读数后交付）。
> 判定人：deputy-lead（只读生产代码；只写 `docs/_review-*.md` + `scratch/`）。
> 冻结树：`git archive 5679562` → python tarfile 展开 `%TEMP%\t244_frozen_v3`；provenance 与读数见 §1。

## §0 判定摘要

- **冻结 hash：`5679562`**（0.7.43）。当前 HEAD `4ff9861` 与冻结树的产品代码**零差异**（唯一差异 = `docs/_analyze-longrun-caliber.md` +21 行）。
- **provenance 复核通过**：`git archive 5679562` 展开后 **677 个追踪文件 677/677 blob SHA-1 一致**（其中 6 个 `.ps1/.cmd` 按 `.gitattributes eol=crlf` 展开为 CRLF，CRLF→LF 归一化后一致）；11 个关键文件 `git hash-object` **11/11** 对照一致。**旧临时目录 `%TEMP%\t244_frozen` 复核不通过、已弃用**：5 个中文名 docs 被 bsdtar 展开成乱码、`longrun.py` 被作者变异脚本原地写回成 CRLF（内容等价但非字节一致）、153 个未追踪本地夹具。
- 逐卡：**task-242 = PASS-WITH-NITS**（无阻塞必修；5 条 NIT 见 §6；NIT-1「护栏 B 源码口径」需 Lead 认可口径）。
- **0.7.43 可以放行 A″/B″（就 task-242/244 这一面）**；但**不能凭 0.7.43 整体放行 A″/B″** —— A8 真机（0.7.43）判「臂被缺陷支配、不作 A″ 证据」（开发日志条目 084/085），还差 **0.7.44 卡 1–3 + 冻结装机 + A9/B9 同起点真跑**。
- 还差什么：本卡无阻塞必修项；结构性缺口 = 0.7.43 短跑账本 `logs/longrun-smoke-0743.jsonl` **不存在**（release plan §3 步 5 门禁要求的账本）⇒ 该门禁**【无法判定】**；本报告用 A8 真机账本做事后核验替代（见 §1 末与 §6「已知限制」）。

## §1 对象与读数

| 项 | 值 |
|---|---|
| 0.7.43 冻结提交 | `5679562`（2026-10-18 14:49:47；只动 `bridge.py`/`manifest.json`/`tools/_note-0743.txt`） |
| task-242 提交 | `f3fffad`（14:30:57；2 文件 `brain/agentfarm/longrun.py` + `tests/test_longrun.py`，+247/−3） |
| 冻结树 provenance | `git archive 5679562` → tarfile 展开 = 677 文件；**677/677 blob 一致**（6 个 eol 展开文件归一化后一致）；关键文件 `git hash-object` 11/11 一致 |
| 版本 | `manifest.json` = 0.7.43 / `bridge.py:39` `MOD_VERSION_EXPECTED = "0.7.43"`（A2 实测一致） |
| 冻结树读数（本次重跑） | `py_compile -W error::SyntaxWarning` rc=0；定向 `Ran 756 / OK`；全量 `Ran 1236 / OK`（red=0）；`dotnet build --no-incremental` **0 警 0 错**；C# 自检 **OK 91 断言** |
| 探针汇总（A/B/C/D/E） | **PASS=30 FAIL=0 SKIP=0 INFO=5**（`scratch/_t244_probe_rerun.txt`） |
| 旧会话读数 | A/B/C `PASS=29 / FAIL=0`、D 段 5 条变异全杀；**旧读数 29 条 = 当时探针少 `B5b` 一条 check**（两版共同 check 逐条一致，重跑补 B5b 后为 30） |
| 真机事后佐证（A8 账本，非冻结树） | `logs/longrun-runA8-0743.jsonl`（sidecar `head=5679562`、`worktree_clean=true`）：**161 个 `clear_area` 阶段 `ok=289 = cleared=289`、`already=50`、`unclear=0`，不变式 0 违反**；5 个新字段 161/161 在场；`already == len(already_tiles) == Σalready_cause` 161/161；12 个 `day_end` 的 `checks` 均为 10 键基线 12/12、`plot_pending`/`assigned_undone` 12/12 |

**夹具说明（如实写）**：冻结树是纯 `git archive`，而 `logs/` 与 `scratch/_ledger_*.jsonl` 都被 `.gitignore` 排除、不在提交内。B1/B1c 与测试套件依赖这两类**本地夹具**：

- 纯 archive 树直接跑全量 = `Ran 1230` + **4 红**（`test_analyze_longrun` 的 3 ERROR + 1 FAIL，全部是 `scratch/_ledger_green/fallback/leftover_verified.jsonl` 缺失触发的 `FileNotFoundError`/断言）⇒ 这是**测试夹具卫生**历史问题，**不是 0.7.43 产品红**。
- 按旧会话同做法补入工作树本地夹具（`logs/*` 399 个 + `scratch/_ledger*` 20 个，均不进提交）后 = **`Ran 1236 / OK`**，与开发日志条目 085 当班读数一致；`logs/longrun-smoke-0742.jsonl` 的 SHA256 = `af1d10788548bb05…7c7ef08`（与旧冻结目录里的副本逐字节相同）。
- C# 自检：开发日志 083 已如实记「0.7.43 冻结当班原文没落文档」；本报告的 `OK 91 断言` 是**事后复核**（明确标注，不冒充当班原文）。

## §2 A 段：范围与越界

- A1 关键文件在树内 ✅（`brain/agentfarm/longrun.py`、`farmwork.py`、`tests/test_longrun.py`）。
- **越界扫描（task-242 提交 `f3fffad`）**：`git show --name-only f3fffad` = 只有 `brain/agentfarm/longrun.py`、`tests/test_longrun.py`；对 `mod/`、`manifest.json`、`bridge.py`、`logs/`、`docs/00-开发日志.md` **0 命中**。冻结提交 `5679562` 只动 `bridge.py`/`manifest.json`/`tools/_note-0743.txt`（Lead 冻结步骤，非本卡）。
- **新字段单列（卡面要求「只许新增字段、须单列」）**：AST 对照 `533e017`（0.7.42 HEAD）→ `5679562`，阶段记录键 **36 → 41**，**新增恰好 5 个、删除 0 个**：`already`、`attempted_ok`、`already_tiles`、`already_cause`、`unclear`（`longrun.py:6830-6836`）。语义（补丁注释）：`already`/`attempted_ok` = 尝试成功但**世界没变**且没耗体力的步；`already_tiles` = 这些格坐标；`already_cause{cleared_by_neighbor,no_target}` = 两种归因；`unclear` = 有 ok 步但拿不到 before/after kind 证据（**只有计数**，见 NIT-2）。
- **语义未动**：
  - `checks` 10 键：旧/新 AST 键集**逐字相同**（`slept_by_us`/`no_blocking_modal`/`no_hard_failures`/`unreachable_within_bound`/`refused_within_bound`/`no_unmet_stages`/`crops_watered`/`watered_outdoor`/`day_justified`/`zero_action_evidenced`）。
  - `day_end` 47 键键集**逐字相同**（含 `assigned_undone`/`plot_pending`/`plot_pending_by_kind`）。
  - 事件名：`f3fffad` 对 `_journal("…")` **增 0、删 0**；`assigned_undone`/`plot_pending`/`no_unmet_stages` 等文本在补丁里**0 触碰**。
  - ⚠ 唯一偏离：**护栏 B 的输入口径被改了**（`ok_steps` 排除 `already`，`longrun.py:6689-6690`），与卡面「不改护栏 B」字面不一致 —— 见 §3.2 与 §6 NIT-1（行为分析：等价或更严，不洗白）。

## §3 B 段：根因与修法覆盖

### §3.1 修前红（0742 账本基线，冻结树复核）

- 夹具：`logs/longrun-smoke-0742.jsonl`（149 行；3 个 `day_end`；无独立 `stage` 事件，阶段记录在 `day_end.stages[]`）。SHA256 `af1d1078…7c7ef08`。
- **本次冻结树复核（B1）**：9 个 `clear_area` 阶段 `ok ≠ len(cleared_tiles)`，合计 **ok=34 / cleared=21 / 差 13**，全部在 `day=[1,"winter",5]` 的 `day_end`；`failed` 全 0。与 `docs/_smoke-0742.md` §5 全账本口径 75/62 一致（本表为这 9 个阶段内部口径）。
- **历史不可回溯（B1b）**：旧账本 9 阶段无 `already`/`unclear` 字段（命中 0）——修的是未来记账，不改历史。
- **根因（代码级，冻结树原文）**：旧 `longrun.py` 的 `cleared_tiles` 只收「`before.kind` 与 `after.kind_after|kind` 都非空且不等」的 ok 步，其余 `unclear_steps += 1`（只进进程内变量）；而 `ok = len(oks)` 按步计 ⇒ `farmwork.clear()` 的「没有需要清的障碍」分支（`farmwork.py:2397-2400`，返回 `ok=True, code="already"`、没站位/没观测/没耗体力）把差额撑大且账本无痕。
- **作者离线重放（B1c，冻结树复跑）**：`rc=0`、9/9 conforming（每段「旧 ok = cleared + Δ ⇒ 新 ok=cleared、already=Δ、unclear=0」）。限制见 NIT-3（是形状验证，不是逐 step 重放）。

### §3.2 修法与覆盖（逐路径判定）

**修法要点**：`clear_area` 的 `ok` 只数**真的改变了一格**的 ok 步；`code=="already"` 的步单列 5 字段（不计 ok）；拿不到 kind 证据的 ok 步落 `unclear` 计数；护栏 B 的 ok 步集合排除 `already`；瓦片级 `ok_tiles` 仍按全部 ok 步（already 格仍算已达标）。阶段不变式 = **`ok == len(cleared_tiles) + unclear`**（开发日志 083 同口径；`unclear=0` 时即 `ok == len(cleared_tiles)`）。

| # | 漏记路径 | 覆盖判定 | 证据（冻结树：行号/实测） |
|---|---|---|---|
| 1 | 多次 `use_tool` 补请求（树/巨石多刀） | ✅ | `farmwork.clear()` 每格最终只返回**一条** `StepResult`，多刀/多请求合并进同一 `after.kind_before/kind_after`（`farmwork.py:2445-2489`）⇒ 一格最多 1 个 ok 步、1 条 cleared；B2 实测 `ok=4 == cleared=4` |
| 2 | `clear_neighbor`/`open_way` 连带格 | ✅ | 连带格只进 `StepResult.opened`（`farmwork.py:2078/2104/739-740`），不进 `all_steps`/`cleared_tiles`；目标格随后回 `already` 时由 `already_cause.cleared_by_neighbor` 显式区分（`longrun.py:6803-6821`）。实测：`test_collateral_neighbour_clear_is_explained` 绿；变异 `m244c` 被杀；A8 账本 `already==already_tiles==Σcause` 161/161 |
| 3 | `tree→stump` | ✅（无此漏记路径） | 树类 `clear()` 判据是「kind 离开 tree 才算 ok」（`farmwork.py:2471-2474`）⇒ `tree→stump` 中间态**不产 ok 步**；一旦产 ok 则 kind 必已变 ⇒ 必进 `cleared_tiles`（`longrun.py:6678`）。不存在「ok 但 cleared 缺」的树路径 |
| 4 | stage tiles 与 step tile 不同源 | ✅-（残余 R1） | 不变式只用 step 口径（`ok`/`cleared` 均来自 `all_steps`）；`tiles` 字段 = step tile 去重数。**R1**：若某 step tile 不在 `assigned`，`ok_tiles_set` 会被 assigned 交集吞掉（`longrun.py:6781`），不影响 `ok==cleared+unclear`，但可能让瓦片三分类（requested/ok/failed/unexecuted）与 cleared 清单想当然地对不上；A8 161 阶段未见 |
| 5 | blocked/deferred 路径 | ✅ | 非 ok 步（failed/skipped/env_block/inconclusive/unreachable/refused）一律不进 `ok`/`cleared`/`unclear`；`env_retry` 重跑同一批格时，上一轮已清的格回 `already` 而非 ok（A8 实录 0 违反） |
| 6 | 残余风险 R2（tile-less ok 步） | 未观测到 | 若出现 `ok=True, tile=None` 的步，`cleared` 循环会静默跳过且不计 `unclear` ⇒ 破坏不变式；但 `clear_area` 的 `run_stage` 逐格返回、补水结果**不入** `all_steps`（`longrun.py:6580-6606` 只记 journal）⇒ A8 161 阶段 0 违反 |

**连带格「目标格 + 连带格」显式区分**：✅ 已区分——连带格**不进** `cleared_tiles`（它不是目标步），目标格被连带清掉后回 `already`，归因入 `already_cause.cleared_by_neighbor`，另一桶 `no_target` 对应「本来就没障碍」的竞态/陈旧目标；`already_tiles` 是这两桶的并集坐标。实测 A8：`already == len(already_tiles) == Σcause` 161/161。

**NIT-1（护栏 B 源码口径偏离卡面字面）**：补丁把护栏 B 的 `ok_steps` 改成排除 `already`（`longrun.py:6689-6690`），而卡面写「不改护栏 B」。行为分析：0.7.42 里 `already` 步没有 before/after kind ⇒ 会进 `unclear_steps`，从而**抑制**护栏 B；修后 `already` 不再进 `unclear`，护栏 B 若仍把它算进 `ok_steps`，全 already 阶段会被误判 `incomplete`（新增单测 `test_guardrail_b_ignores_already_steps` 正是钉这个）。与 0.7.42 的差异只落在「`already` 与『kind 有证据但没变』的 ok 步混在同一阶段」这一角：旧=不判红（被 already 压住的假阴性），新=判 `incomplete`（**更严、只会更红，不会洗白**）。结论：不构成放行阻塞，但需 Lead 记口径。

## §4 C 段：四把伪造（独立判据，修前已可判红/判绿）

判据（我方独立实现 `scratch/_t244_probe.py:97-119`，卡面语义）：`ok > len(cleared) + explainable` ⇒ 红；`len(cleared) > ok + collateral` ⇒ 红；清单格不在阶段 tiles 且非 collateral ⇒ 红。`explainable` 只认 `unclear` 族（**不含 already**，否则 m244a 会被误放行）。

| # | 伪造 | 期望 | 修前读数 | 冻结树判据实测 |
|---|---|---|---|---|
| C1 | 漏记一个 ok 格（ok=4 / cleared=3、unclear=0） | 红 | ✅ 红 | ✅ 红 |
| C2 | 连带清多格只记目标格（ok=1 / cleared=2，无 collateral 解释） | 红 | ✅ 红 | ✅ 红 |
| C2b | 同 C2 但显式记 `collateral_tiles` | 绿（可解释） | ✅ 绿 | ✅ 绿 |
| C3 | 清单多出未 ok 的格（ok=3 / cleared=4） | 红 | ✅ 红 | ✅ 红 |
| C4 | `len==ok` 但格子不在阶段 tiles 内（`[70,20]` 越界） | 红 | ✅ 红 | ✅ 红 |
| C5 | 把 already 伪装成 unclear 试图解释差额（ok=4/cleared=2/unclear=2） | 绿（可解释） | — | ✅ 绿（判据设计：unclear 是唯一合法解释项；见 NIT-2） |
| C6 | unclear 缺失时差额必须判红（ok=4/cleared=2） | 红 | — | ✅ 红 |
| C7 | cleared 全在 tiles 内但 ok 少（ok=2/cleared=4/无 collateral） | 红 | — | ✅ 红 |

C5–C7 是本次补的「unclear 解释边界」对抗（修前 C1–C4 已可判）。

## §5 D 段：变异实测（自报 vs 实测）

- **作者脚本**：`scratch/_t242_mutate.py`（在冻结树内、可复跑；`kind = unittest:TestTask242ClearAreaEvidence` 5 例）。作者提交 `f3fffad` 自报「**变异 4/4 被杀**」。本次**在副本 `%TEMP%\t244_frozen_v3_author` 上**独立复跑：基线 `Ran 5 / OK`，**实测 4/4 被杀**（FAIL 数 4/1/1/1），与自报一致。
- **我方自建**：`scratch/_t244_mutate.py`（`kind = probe`，锚点 5 条、`--check-anchors` 坏 0 处），**实测 5/5 被杀**（每条 probe 1 FAIL；`--base` 指向冻结树，变异只在临时副本里做，冻结树零改动）。
- **两列表**：

| 变异 | 来源 | 自报 | 实测（冻结树独立复跑） |
|---|---|---|---|
| `m242a_ok_counts_already` | 作者 | 作者自报 4/4 之一 | **被杀**（单测 4 红：`test_already…`/`test_collateral…`/`test_guardrail…`/`test_smoke…`） |
| `m242b_guardrail_counts_already` | 作者 | 作者自报 4/4 之一 | **被杀**（1 红：`test_guardrail_b…`） |
| `m242c_ok_tiles_drops_already` | 作者 | 作者自报 4/4 之一 | **被杀**（1 红：`test_already…`） |
| `m242d_collateral_cause_lost` | 作者 | 作者自报 4/4 之一 | **被杀**（1 红：`test_collateral…`） |
| `m244a_already_counted_as_ok` | 我方（≈作者 m242a，走 probe 判据） | 我方脚本声明「等价」 | **被杀**（probe 1 FAIL） |
| `m244b_unclear_not_recorded` | 我方自建 | 自建、无自报 | **被杀**（1 FAIL） |
| `m244c_already_cause_always_neighbor` | 我方（≈作者 m242d） | 我方脚本声明「等价」 | **被杀**（1 FAIL） |
| `m244d_ok_tiles_drops_already` | 我方（≈作者 m242c） | 我方脚本声明「等价」 | **被杀**（1 FAIL） |
| `m244e_attempted_ok_zero` | 我方自建 | 自建、无自报 | **被杀**（1 FAIL） |

- **脚本卫生备注（NIT-4）**：作者脚本用 `Path.write_text()` 原地改/恢复 `longrun.py`，Windows 下恢复时**会把行尾改成 CRLF**（旧临时目录 `t244_frozen` 的 `longrun.py` 正是被这样留下的）⇒ 冻结树禁止原地跑变异；本次统一在副本跑。

## §6 E 段：结论

- **task-242 判定：PASS-WITH-NITS（无阻塞必修）**。证据锚点：
  - 冻结树 provenance `677/677` blob 一致、关键文件 `hash-object 11/11`；
  - A/B/C/D/E 探针 **30 PASS / 0 FAIL**（`scratch/_t244_probe_rerun.txt`）；`py_compile rc=0`；定向 `Ran 756 / OK`；全量 `Ran 1236 / OK`；`dotnet build 0 警 0 错`；C# 自检事后复核 `OK 91 断言`；
  - 9 个历史阶段 conforming（B1/B1c）+ 新增 5 单测全绿；作者 4/4、我方 5/5 变异全杀（自报 vs 实测算术一致）；
  - **A8 真机账本**（0.7.43，sidecar `head=5679562`）：161 个 `clear_area` 阶段 `ok=289=cleared`、`already=50`、`unclear=0`、不变式 0 违反、5 字段 161/161。
- **0.7.43 可/不可放行 A″/B″**：**可以放行 A″/B″ 的 task-242/244 面**（无阻塞必修，事故后真机 A8 账本也验证了 0.7.43 的新口径在真机上成立）；**但不能凭 0.7.43 整体放行 A″/B″** —— A8 整臂被判「缺陷支配、不作 A″ 证据」（条目 084/085 的两条系统性死循环与 242/245 无关），**还差 0.7.44 卡 1–3 + 冻结装机 + A9/B9 同起点真跑（步 3/步 5 等门禁复跑）**。
- **NIT 清单（不阻塞放行）**：
  - NIT-1 护栏 B 源码口径改了（`ok_steps` 排除 already），与卡面「不改护栏 B」字面不一致；行为更严、不洗白，需 Lead 认可口径（§3.2）。
  - NIT-2 `unclear` **只有计数、无逐格坐标**：差额可解释但不可逐格审计（B3 实测 `ok=4/cleared=3/unclear=1`；A8 真机 0 命中）。
  - NIT-3 作者离线重放是**形状验证**：0.7.42 账本无逐 step 明细，重放用「`engaged=cleared`、`Δ=ok−engaged`」重建 9 阶段，证明的是新记账路径的不变式，不是原始事件逐条重算。证据强度限制如实写。
  - NIT-4 测试夹具未入仓 + 变异脚本原地跑改行尾：纯 `git archive` 树全量单测 4 红（全是 `scratch/_ledger_*.jsonl` 缺失）；补齐本地夹具后 `Ran 1236/OK`。建议后续把夹具放进 `tests/fixtures/` 或改成 skip（历史遗留，不在本卡范围）。
  - NIT-5 `ok` 口径跨版本不可直接比：0.7.42 的 `ok` = 尝试成功数（含 already），0.7.43 起 = 真变化数；`tools/verify-run3.py:1100-1127` 用 `stages[].ok` 求和判「0 动作/弱日」、`tools/compare-runs.py:138` 做吞吐对比 ⇒ 跨版本对比须用新字段或按版本换算。**A8 真机未触发误判**（`ok=0 且 already>0` 的 clear_area 阶段 0 个；全阶段 ok 合计为 0 的天 0 天）。
- **已知限制 / 【无法判定】**：
  - 0.7.43 短跑账本 `logs/longrun-smoke-0743.jsonl` **不存在** ⇒ release plan §3 的「0.7.43 步 5 真机门禁」**【无法判定】**；本报告用 A8 真机账本（0.7.43、161 阶段）做事后核验，**不能**把 A8 当 A″ 证据（A8 已判缺陷支配）。
  - 0.7.43 冻结当班的 `dotnet build`/C# 自检/`check-release` 原文缺失（条目 083 已如实记录）；本报告的 build/C# 读数是**事后复核**，只能证明"现在仍绿"，不能冒充当班原文。

## §7 边界声明

- 只读生产代码；只写 `docs/_review-0.7.43.md` + `scratch/`；不碰游戏/桥、不 deploy、不 bump、不改任务板、不写 `docs/00-开发日志.md`。
- 本次读数的复现命令：`T244_ROOT=%TEMP%\t244_frozen_v3 python scratch\_t244_probe.py --readings`（全量）、`python scratch\_t244_mutate.py --base %TEMP%\t244_frozen_v3 --all`（我方变异）、在冻结树副本根跑 `python scratch\_t242_mutate.py`（作者变异）。探针/变异脚本本次随本报告一并提交（旧骨架提交 `73d3c9a`/`25510d2`）。
- worktree 在制读数/旧会话读数只作线索；正式判定一律以 `git archive 5679562` 冻结树 + A8 真机账本（sidecar 版本证据）为准。
- 旧临时目录 `%TEMP%\t244_frozen` 已证明非 pristine（见 §0），本报告所有读数来自重新展开的 `%TEMP%\t244_frozen_v3`。
