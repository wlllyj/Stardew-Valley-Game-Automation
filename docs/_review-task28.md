# task-28 独立集成验收（busy/stale 分类 + 防自旋护栏）

- 验收人：deputy-lead；时间：2026-10-13 01:0x
- 被验对象：task-28（rev4，dev-coder，板面 completed）；HEAD=`cc066bc`（工作树在制）
- **判定：PASS-WITH-NITS**（三条 NIT 全是文档/工具映射，无行为缺陷）

## §1 四项惯例（我独立复跑，未引用自述）

| 项 | 命令 | 读数 |
| --- | --- | --- |
| 语法 | `py_compile`（`brain/agentfarm/*.py` + `tests/*.py` 全量） | **exit 0** |
| 单测 | `PYTHONPATH=<repo>\brain python -m unittest discover -s tests` | **Ran 262 tests / OK**（task-28 基线 249 → +13） |
| Mod 构建 | `dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` | **0 警告 / 0 错误**（1.02s） |
| 版本 | `mod\AgentFarm.Bridge\manifest.json:4` / `brain\agentfarm\bridge.py:39` | 均 **"0.7.21"，未 bump**（正确，0.7.22 由 Lead 冻结时统一 bump） |

快照指纹（SHA256 前 12 / mtime）：`farmwork.py 24CDF1F93356`（00:56:42）、`longrun.py D90A731E729A`（00:57:16）、`tests/test_farmwork.py 1541686F19E7`（00:57:31）、`tests/test_longrun.py 2854C93BEB07`（01:00:16）。

## §2 任务书逐条

| # | 条款 | 结论 | 证据 |
| --- | --- | --- | --- |
| 1 | `busy` → ENV（不封格、不占配额） | ✅ | `farmwork.py:84 ENV_BLOCK_STATUSES = ("no_save","ui_modal","world_fading","busy")`；`farmwork.py:420-421 ⇒ (True, False)` |
| 2 | `stale` → INCONCLUSIVE（占配额、不封格） | ✅ | `farmwork.py:100 INCONCLUSIVE_STATUSES = frozenset({"timeout","error","stale"})`；`:422-423 ⇒ (False, True)` |
| 3 | 两处常量注释写来源/理由 | ✅ | `farmwork.py:78-100`（`MainThreadDispatcher.cs:159-169`、`BridgeHost.cs:538-553`、为什么 busy 不是 inconclusive）；`longrun.py:64-70`、`:950-956` |
| 4 | **防自旋有界策略** | ✅ | `longrun.py:70 MAX_ENV_ATTEMPTS = 2`；`env_streak`/`env_spin_noted`（`:375-377`，每日重置 `:1497-1498`）；`_count_attempts` `:962-979`：连续被挡 ≤2 次免费，第 3 次起 `+1 tile_attempts`（`:977`），到 `MAX_TILE_ATTEMPTS=2` ⇒ `capped` ⇒ needs_review，**始终不写 `blocked`/`proven_inert`**（`:920-922` 只对 `s.env_block or s.inconclusive` 跳过封格） |
| 5 | 三类集合互斥 + 覆盖扩展后全量码 | ✅ | `tests/test_farmwork.py:474-514`：三条 `assertFalse(交)`（:489-491）、`mod_codes` 含 busy/stale（:492-497）、并集覆盖断言 `:498`、精确集合 `:500-502`、`_classify_status` 逐码断言 `:505-514`；注释 `:482-483` 如实收窄覆盖范围 |
| 6 | 新增集成用例（clear/till busy、持续 busy 有界） | ✅ | `tests/test_longrun.py:1619 test_clear_busy_is_env_and_never_seals`、`:1637 test_till_busy_is_env_not_sealed`、`:1651 test_endless_busy_requests_are_bounded`、`:1681 test_endless_busy_full_run_is_not_verified`；farmwork 侧 `tests/test_farmwork.py:516/:529/:540` |
| 7 | 不改协议/Mod、只写三处范围 | ✅ | `git status --short` 里 Mod 三件套（`Contracts.cs`/`UiRead.cs`/`WorldSnapshot.cs`）是 **task-11 经批准的越界**，task-28 未碰 Mod |

**防自旋的"有界"是实测断言，不是推理**：`test_endless_busy_requests_are_bounded`（`tests/test_longrun.py:1666-1674`）在"永远回 busy"的假桥下断言 `client.use_tool_calls == MAX_ENV_ATTEMPTS + MAX_TILE_ATTEMPTS`（**恰好 4 次**）、`tile_attempts[(60,10)] == 2`、`run.blocked == {}`、`blocked` 事件 **0 条**、`proven_inert` 求和 **0**、`env_spin_capped` 恰好 1 条、`postcondition_met is False`、`terminal == "needs_review"`；端到端 `:1681-1695` 断言 `run.run()` 非 0、请求数 ≤ 4+2、当天 `verified is False`。⇒ 满足 task-28 条款 4 的"请求次数有界 / 当天不 VERIFIED / 不产生 `proven_inert`"三项硬要求。

## §3 NIT（只报不修）

- **N1（口径映射漏项，建议并入 task-30）**：task-28 新增 journal 事件 `env_spin_capped`（`longrun.py:973`），但 `tools/analyze-longrun.py` 的映射表里没有它（现有映射只到 `env_fail`/`inconclusive_fail`/模态事件，`analyze-longrun.py:53/:63-64/:70/:125-126`）⇒ 分析器会把这类"配额被吃掉的证据"当未知事件。task-30 正在做同族工作，加一行即可。
- **N2（注释与实际口径不一致，`longrun.py:911`）**：`_mark_blocked` 的 docstring 仍写 `s.inconclusive`（超时 / 异常 / **没见过的码**）——与 Lead m01763 裁定 A 冲突：按 `farmwork.py:407-408`/`:419-424`，**没见过的码属兜底桶 `(False,False)`＝"Mod 真的回应了"**，会走结论（封格）路径。措辞应改成"超时 / 异常 / **`stale`**"，否则下一个读者会拿它当依据去放宽封格。
- **N3（粒度未写明）**：`env_streak` 只按**格**（`tuple(s.tile)`）计数、不带动作 ⇒ 同一格上"清障被挡"与"浇水被挡"共用一条 streak（`longrun.py:965-969`）。当前语义可接受（环境挡路确实与动作无关、更保守），但 docstring 未说明，建议一句话点明"按格不按动作"。

## §4 附带观察（不影响判定）

- `env_spin_capped` 未进 stage/day 汇总（`longrun.py:1082-1088` 只汇总 `env_fail`/`inconclusive`）⇒ `tools/verify-run3.py` 无法直接看到"触发了上限"，只能从 `capped`/`stage_exhausted`/`verified=false` 间接推断。当"信息项"可接受。
- 端到端用例的界允许 `+2` 松弛（`:1691`），精确界由 `_step_stage` 级用例（`:1667`）钉死 —— 分工合理，非缺陷。
- 验收期间 `log-analyst` 的 task-30 在制（`tools/analyze-longrun.py` + `tests/test_analyze_longrun.py`），全量 262 OK 说明其当前状态干净；若后续它红了，责任文件是那两个（与 task-28 无关）。

## §5 越界与卫生

- task-28 只在 `brain/agentfarm/farmwork.py`、`brain/agentfarm/longrun.py`、`tests/` 内改动（`git status --short` 核对）；未碰 `mod/`、`docs/00-开发日志.md`、`logs/`、`tools/`、`scratch/`（`scratch/_review_neg_gen.py` 与 `docs/_review-*.md`、`docs/_verify-run3-limits.md`、`scratch/_mk_*.py` 是**我**的在制产物）。
- 未 deploy、未碰游戏/桥、未 bump。
