# 0.7.39 发布计划（Lead 独占：冻结/装机/开发日志）

状态：**计划中（未开工冻结）**　上一版：0.7.38（已装机，见 `docs/_release-0.7.38.md` §5）
制定时间：2026-10-18 01:30（Asia/Bangkok）

## §1 本批内容（按合入顺序）

| # | 卡 | 内容 | 状态 |
|---|---|---|---|
| 1 | task-218 | 树纳入清障（普通树 0 级斧可砍）+ **护栏 A 端到端 6 层** + **护栏 B 逐格判据** + 片地优先/体力预算/桩与圆木 backlog | ✅ `b679f4e`（9 files +887/−64） |
| 2 | task-222 | Mod `debug_dump` 支持 1.6 强类型资产（四表 + 逐表 fail-closed + `type`/`error`）+ 观测 `knownCraftingRecipes` 三态 | ✅ `7f030c2`（7 files +399/−66） |
| 3 | task-223 结果 | Furnace 配方 1.6 合法授予路径定案 | ✅ `fb275a8`（`docs/_il-furnace-unlock.md`） |
| 4 | task-219 | **意图-执行对账闭环**（`intent_coverage` + 12 码闭合集 + `<journal>-gaps.json` + `Brief.recent_gaps`） | ✅ `fc147a7`（5 files +950/−22） |
| 5 | task-210 | 机器链技能层 `craft_item`/`place_object`/`machine`（策略层并入 task-227） | ✅ `2dde12e`（3 files +613） |
| 6 | task-228 | Mod `advance_dialogue`：**只推进非提问对话**（用户 `m19382` 授权；无人值守跑批前提） | ✅ `3dc4b1e`（13 files +1204/−9；C# 85 断言、全量 1132 OK） |
| 7 | task-220 | analyzer 收 `intent_coverage`/gaps + §8 判红 + 跨 run `gaps-registry.json` | ✅ `19b2827`+`fac6a29`（247 OK） |
| 8 | task-230 | **P0 收口**：`FarmView` 五项农场计数 / 12 码 + 映射表 + `no_target` 证据 / gaps 坏档归档 + 写失败判问题 + 禁转 lessons | dev-coder 在制 |
| 9 | task-231 | analyzer 口径对齐（`ok_tiles`/判红编号/§8.6 backlog），`blocked_by task-230` | 待 230 落地后 GO |

**本批不进**（0.7.40+）：task-227 铜斧全链路、task-229 床上睡觉坑、task-195/196/193/197 遗留、task-151/221（目标 1 的田区清空与余力多清）。

> **§1b 本批外的重大真机结论（2026-10-18，task-226 `d1e085a`）**：**买 1 个铜矿即可触发 Clint 送 Furnace 蓝图**（存档 `<craftingRecipes>` 19→20、新增键 `Furnace`；与旧 wiki"购买不触发"相反）。P0-0「没有铜锭」在"蓝图"环节已解，剩余是钱与材料（缺口 ≈6300g，现有 1977g）。详见 `docs/_run10-furnace-acquire.md` 与开发日志条目 078。

## §2 冻结九步（照 0.7.37/0.7.38 同款）

1. `tools/_note-0739.txt`（首串必须 `v0.7.39`，列本批 Mod 侧内容）。
2. `python tools\_bump-mod-version.py 0.7.39 --note-file tools\_note-0739.txt` → manifest `0.7.38→0.7.39`（核 `Description` 首串）。
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.39"`（注释补条目，历史段保留）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ 0 警 0 错，记 dll 字节数。
5. `git add -A` 后冻结提交（含 manifest + bridge.py + 本批代码/测试/文档）。
6. `python tools\check-release.py --expect 0.7.39` ⇒ 六项全绿（manifest==brain、版本==期望、dll 新鲜、py_compile、全量 `PYTHONUTF8=1` 0 红、树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ 装机 + 自动读档；记录桥 `modVersion=0.7.39`、port。
8. `python -m agentfarm goto Farm`（需 `PYTHONPATH=<repo>\brain`）⇒ 记 hop1/耗时。
9. `python tools\preflight.py --expect 0.7.39 --save-baseline logs\run-check-0739-baseline.json` ⇒ 四项全绿。

**装机后必做的真机烟雾（条目 077 的教训，硬性；2026-10-18 按 task-225 §6 升级为 7 步）**：
1. `debug_dump table=crafting_recipes key=Furnace` ⇒ 不得回 `unknown_skill`，且 `matchedCount>=1`（验 Mod 白名单与 dump 双通道）；
2. `debug_dump table=trigger_actions` ⇒ 能读（task-222 的目标；若仍 `InvalidCastException` 则本批 smoke 判红、回炉）；
3. 单技能砍树：对一棵 `kind=="tree"` 的格发 `use_tool(axe)` ⇒ 观测里该格必须从 `tree` 变 `stump`（或消失），且 `StepResult.after` 带 before/after kind；
4. 跑 **1 个游戏日**的 `tools\run-longrun.py --days 1` ⇒ `day_end.intent_coverage` 出现、`<journal>-gaps.json` 生成；
5. 该日 `day_end.stages[]` 里 `clear_area` 的每个 ok 步都有 `cleared_tiles`/kind 变化（P0-1 逐格判据活）；
6. 该日跨日落盘**六串 6/6 配对**（`tools\compare-runs.py` 或 `scratch/runA-tools.py` 系列复核）；
7. `tools\analyze-longrun.py --days 1` 判 §8 无「意图 executed_steps==0 且无原因码」；`tools\verify-run3.py` 对 §8 只出 info（P0-5 分工）。
**全部 7 步通过才允许起 A″/B″**；任一步失败 ⇒ 停手、回滚、判红。

## §3 判据

- **通用**：`docs/_run10-criteria.md` 全部条款 + `docs/_run6-criteria.md` 尾部窗口口径；两侧工具（`tools/verify-run3.py`、`tools/analyze-longrun.py`）同向；缺失 ≠ 通过；口径变更须过独立对抗验收。
- **护栏 A（意图-执行覆盖）**：`OBSTACLE_KINDS ∪ CLUMP_KINDS` 每一类，**端到端 6 层**（planner → `_plot_brief` → `_stage_tiles` → `clear()` → `_plot_has_work` → `_apply_policy`）都要么能产出可执行目标，要么登记在 `DEFERRED_KINDS` 且简报如实写"暂不支持"；另须 `SKIP_KINDS ⊆ DEFERRED_KINDS` + `DEFERRED_KINDS` 键集合快照（当前只许 `{fruitTree,bush}`）+ 注册表漂移测试 + tiles 缺失/截断时 fail-closed announce。有一条两头都不在 ⇒ 判红。
- **护栏 B（清障有效性）**：`clear_area` 的每个 ok 步必须给出该格 `cleared_tiles` 或 kind 变化（`tree→stump` 记 progress **不算红**）；**farm 级聚合只作 info、不进判红**（`farm.blockers` 在观测里不存在，见 P0-1）；if farm 计数由 task-222 补上，仅作趋势参考。
- **工具分工（P0-5）**：§8 意图对账**由 `tools/analyze-longrun.py` 判红**（读 `day_end` 全量 dict）；`tools/verify-run3.py` 对 §8 **只出 info**（day_end 白名单 `tools/verify-run3.py:290-324` 不扩）；能力缺口 ≠ hard failure、不进 `_leftover`/`checks`。
- **意图对账（task-219）**：LLM 给出的每个意图都必须有 `intent_execution` 记录；`executed_steps==0` 必须有原因码；原因码属能力缺口 ⇒ 进 `gaps.json` 且次日简报可见。
- **零回归**：既有 1055+ 单测 0 红；账本矩阵（green/run2/run7/runA-0732/run9b/run9c/run9d）rc 与旧判决不变。

## §4 风险与已知限制

- **Furnace 配方仍是硬阻塞**：没有铜锭 ⇒ 没有铜斧 ⇒ 目标 1 的树桩/圆木清不掉；task-223 若给不出合法路径，需要走"替代材料来源"或"先清无桩区域"的降级验收（Lead 届时裁定，不许改存档/不许直接写 `craftingRecipes`）。
- **树纳入清障会显著增加体力开销**：树 743 棵，单棵斧头多次挥动；护栏 B 可能让 `clear_area` 阶段大量 incomplete ⇒ 需要 `task-218` 的体力预算与片地优先同时生效，并观察是否把日子拖成 `stamina` 收尾（可接受，但 A″/B″ 前要复核不会天天 `stuck`）。
- **真机次数成本**：每次装机+读档+跑批约 40–60 分钟；本批冻结后优先做 task-214 复跑（假设 B 定案），再进 A″/B″。
- **无人值守昏睡罚金**：已发生 3 次（各 −10% 金币）；游戏开着就必须有人/有脑在跑，跑完立刻 `stop-game.py`（`m02833`）。

## §5 执行记录

（待冻结后填写：日期 / 冻结提交 / dll+manifest 字节 / check-release 原文 / 装机 port / 基线文件 / 五文件指纹 / 烟雾结果）

## §6 冻结后的执行顺序（Lead 2026-10-18 定稿）

1. **0.7.39 冻结九步**（本文件 §2）＋ 7 步真机冒烟（§2 末）。
2. **A″/B″**（task-113 rev16）在 0.7.39 上各跑 5 个游戏日：A″ → 字节拷贝教训库 → B″ → compare-runs 的 L0–L5。**跑批期间 brain 三文件冻结**。
3. A″/B″ 出结论后，再进 **0.7.40 批次**：
   - **task-229**（sleep 床上坑：读档即在床上 ⇒ 先下床再睡）；
   - **task-227**（铜斧全链路：攒钱 6300g → 买 45 铜矿+6 煤 → 造熔炉 → 炼 5 铜锭 → 买铜斧 → 2 天后取回 → 	oolOk false→true）；
   - **task-151 rev5**（指定作业区清空 + zone_cleared + 连续 2 天复核）与 **task-221 rev2**（余力多清）—— 目标 1 的验收面。
4. 目标 1 的"钱在作物再投资与工具升级间平衡"由 task-227 的 
eserve_for_upgrade 落地后再跑 3–5 天真机核账。

**已知不阻塞项**（0.7.40+）：task-195/196/193/197 遗留、task-16 常设、task-82/111/112 复盘进化（task-58/59 已交付）。