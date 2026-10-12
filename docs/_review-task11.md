# task-11 独立集成验收（模态守卫 / 职业安全硬规则）

- 验收人：deputy-lead（只读复核 + 独立复跑，不引用 dev-coder 结论）
- 时间：2026-10-13 01:0x
- 验收对象：工作树在制（**未提交**）的 task-11 改动；HEAD = `cc066bc`
- 快照指纹（SHA256 前 12 位 / mtime）：
  - `brain/agentfarm/longrun.py` = **D90A731E729A**（00:57:16，含 task-11 模态守卫 + dev-coder 同时进行的 task-28 防自旋片段）
  - `mod/AgentFarm.Bridge/Contracts.cs` = 114724132119（00:52:31）
  - `mod/AgentFarm.Bridge/UiRead.cs` = D265F1DF3481（00:52:28）
  - `mod/AgentFarm.Bridge/WorldSnapshot.cs` = 9E913A4E0734（00:52:33）
  - `tests/test_longrun.py` = 4FF8066429E7（00:55:05）
  - `brain/agentfarm/farmwork.py` = 24CDF1F93356（00:56:42，**diff 100% 属 task-28**：`busy`/`stale` 归类，见 §6）
- 判定：**PASS-WITH-NITS**

## §1 四项惯例

| 项 | 结果 |
| --- | --- |
| `py_compile`（`brain/agentfarm` + `tests` 全量） | exit 0 |
| `python -m unittest discover -s tests` | **Ran 258 tests / OK**（当前快照；见 §6 的 255→258 说明） |
| `dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` | **0 警告 / 0 错误**（1.56s，DLL 已重出） |
| 版本 | `mod/AgentFarm.Bridge/manifest.json:4 "Version": "0.7.21"`、`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.21"` —— **未 bump，符合"整链冻结时统一 bump"** |

## §2 职业四态（逐条对代码 + 用例）

1. **普通升级弹窗**：`longrun.py:1442 ids = ui.get("professionsToChoose", None)` → `:1456 kind="levelup"` → `:1467 _dismiss_modal_once()`。
   用例 `tests/test_longrun.py:1464 test_plain_levelup_dismissed_save_menu_only_waited`：`w.dismissed == ["LevelUpMenu"]`、`dismiss_calls == 1`、`modal_dismissed[0].kind == "levelup"`、回执 `ok=True` 留痕。✅
2. **职业选择（非空候选）**：`longrun.py:1450-1455` → `_journal("levelup_profession_pending", ids=list(ids), menuText=…)` + `rep.notes` + `_modal_blocked()`（`:1477 rep.ended_by = ENDED_BY_MODAL`）。
   用例 `:1509 test_profession_choice_is_never_dismissed_and_day_is_not_verified`：`run()` 返回 **1**、`dismiss_calls == 0`、`levelup_profession_pending[0].ids == [0, 1]`、`rep.ended_by == "blocked_modal"`、`rep.checks["no_blocking_modal"] is False`、`rep.verified is False`。✅
3. **字段缺失 = 未知**：`longrun.py:1443 if ids is None:` → `:1444` 记 `levelup_profession_unknown` → **不 dismiss**、停下。
   用例 `:1528 test_missing_professions_field_is_treated_as_unknown`：`dismiss_calls == 0`、`ended_by == ENDED_BY_MODAL`、事件 1 条。✅（"不拿不确定性赌不可逆操作"落实）
4. **`SaveGameMenu` / `NewDaySavingMenu` = wait-only**：`longrun.py:75 MODAL_WAIT_ONLY = ("SaveGameMenu", "NewDaySavingMenu")` → `:1432 _wait_modal_gone()`（`MODAL_WAIT_TIMEOUT_S = 90.0`，真机约 30s 的 3 倍余量）→ 超时 `:1377 modal_timeout` + `_modal_blocked` 停下。
   用例 `:1560 test_wait_only_modal_timeout_stops_the_day`：`dismiss_calls == 0`、`ended_by == ENDED_BY_MODAL`、`modal_timeout[0]["menu"] == "SaveGameMenu"`；`:1464` 另证"自走完的存档模态不 dismiss、且 `modal_gone` 留痕"。✅
5. **附加两条**（任务书要求之外，实测都过）：连出两个 `LevelUpMenu` 关两次（`:1492`，`dismiss_calls == 2`）；提问模态走 Mod 的"选否"口径且 `kind="question"`（`:1544`，`dismiss_calls == 1`）。✅
6. **调用位置**：`longrun.py:1517 while True:`（日循环每一步）→ `:1524 obs = self._snap()` → `:1535 obs, modal_blocked = self._clear_modals(obs, rep)` → `:1536 if modal_blocked: break` → 之后才 `sleep_guard`/`_preconditions`/`decide`。即"**每步之前**、`_snap()` 之后、决策之前"，与任务书第 1 条一致。✅
7. 菜单名口径：`UiRead.ActiveMenu()`（`mod/AgentFarm.Bridge/UiRead.cs:43 return menu.GetType().Name`）⇒ `LevelUpMenu`/`SaveGameMenu` 字面量比对成立。✅

## §3 两处"经 Lead 批准的越界"（核对无夹带）

- `mod/AgentFarm.Bridge/WorldSnapshot.cs`：diff **只有 1 条语句 + 3 行注释** —— `v.ProfessionsToChoose = UiRead.ProfessionsToChoose();`（:800 附近），无其它语义变化。✅
- `brain/agentfarm/longrun.py` 日循环收尾：`:1748 if rep.ended_by in ("bridge_down", "stop", ENDED_BY_MODAL):`（原为两元素元组）—— 只多了一个早退分支 + 2 行注释，无其它语义变化。✅
- **`WhenWritingNull` 前提核实**：`mod/AgentFarm.Bridge/Contracts.cs:26-29 JsonSerializerOptions Options { DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull }`；`UiRead.cs:83-107` 三态返回（非 `LevelUpMenu`/反射失败 → `null`；`LevelUpMenu` 读到 → `int[]`，**空数组**=`[]`）⇒ JSON 里"字段缺失"与"空数组"可区分，脑侧第 2/3 态的前提成立。✅

## §4 口径一致性（我的常设职责②）

- `tools\verify-run3.py`（未改动）对 `ended_by="blocked_modal"` 的处理正确：用探针账本 `scratch\review-task11-modal-day.jsonl`（绿账本最后一天改为 `blocked_modal` + `no_blocking_modal=false` + `verified=false`，生成器 `scratch\_mk_task11_modal_day.py`）实测 **exit 1 / needs_review**，问题两条：`ended_by=blocked_modal（不是我们主动睡过去的）`、`day_end verified=false`，尾部连续 VERIFIED 天数 0。✅
- `tools\analyze-longrun.py` 也用同一账本实测：`checks.slept_by_us=false` 与 `checks.no_blocking_modal=false` **都被抓成"1 该做没做"**，没有漏报。✅
- **NIT（口径漂移，只报不改）**：`tools\analyze-longrun.py:50-55 CHECK_MEANING` 里没有 `no_blocking_modal`，所以分析器对这条打印的是 `checks.no_blocking_modal=false —— **未定义的检查项**`（判定不受影响，只是给不出人话解释）。建议把该键补进 `CHECK_MEANING`（task-11 新增的口径）。
- **NIT（轻微）**："立刻上报 Lead"目前落成 journal + `rep.notes` + `_say` + 退出码 1，没有主动通知通道；run3 期间若真弹职业选择，只能靠人盯日志/退出码。Lead 已用 XP 证据判定 3 天内不会弹（防风草 8 XP × 31 格 × 3 天 = 248 < 2150），风险可接受。

## §5 在制干扰说明（为什么 §1 的测试数不是 255）

- dev-coder 的 task-28（`busy`→ENV / `stale`→INCONCLUSIVE + 防自旋）**与本次验收并行在同一批文件上**（`farmwork.py` 00:56:42、`tests/test_farmwork.py` 00:57:31、`longrun.py` 00:57:16）。
- 我在 00:56 前后跑全量时曾见 **255 tests / 1 failure**：`test_farmwork.py:493 assertEqual(incon, {"timeout","error"})` 报 `Items in the first set but not the second: 'stale'` —— 这是 task-28 **条款 5 明确要求同步更新**的那条用例当时尚未更新，**不是 task-11 缺陷**。
- dev-coder 更新后（`tests/test_farmwork.py:500-502` 已含 `stale`/`busy`）同一套件为 **258 tests / OK**。
- task-11 自身的 6 条用例在**最新快照**单独复跑：`discover -p test_longrun.py -k …` ⇒ **Ran 6 / OK**；`test_longrun.py` 全模块 54 tests / OK。
- 结论：**task-11 的语义与用例在当前快照上独立复现通过**；全量基线的"绿"与本任务不冲突。

## §6 越界与卫生

- task-11 实际只碰：`brain/agentfarm/longrun.py`、`mod/AgentFarm.Bridge/{Contracts,UiRead,WorldSnapshot}.cs`、`tests/test_longrun.py`。`brain/agentfarm/farmwork.py` 的工作树 diff **纯 task-28**（`busy`/`stale` 常量与注释），与 task-11 无关。
- 未碰 `docs\00-开发日志.md`、`logs\`；无 deploy、无真机、无 Mod 装机；manifest 未 bump。
- `git status --short` 里的 `scratch/dbg_level_risk.py`、`tools/` 无改动等属其它成员/我的 scratch 产物，不影响本判定。

## §7 建议（非阻塞）

1. 把 `no_blocking_modal` 补进 `tools\analyze-longrun.py:50 CHECK_MEANING`（顺带把 `final_water`/`env_fail` 的"计划新增"措辞在 task-19 落地后更新）。
2. 整链冻结时，本报告的四态用例纳入发布前门禁（`-k levelup -k profession -k modal -k question` 一条命令即可）。
