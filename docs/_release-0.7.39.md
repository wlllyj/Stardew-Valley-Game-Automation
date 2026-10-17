# 0.7.39 发布计划（Lead 独占：冻结/装机/开发日志）

状态：**计划中（未开工冻结）**　上一版：0.7.38（已装机，见 `docs/_release-0.7.38.md` §5）
制定时间：2026-10-18 01:30（Asia/Bangkok）

## §1 本批内容（按合入顺序）

| # | 卡 | 内容 | 状态 |
|---|---|---|---|
| 1 | task-218 | 树纳入清障（普通树 0 级斧可砍）+ **护栏 A 意图-执行覆盖矩阵** + **护栏 B `farm.blockers` 未降判红** + 片地优先/体力预算/桩与圆木 backlog | dev-coder 在制 |
| 2 | task-222 | Mod `debug_dump` 支持 1.6 强类型资产（`trigger_actions`/`objects`/`big_craftables`/`machines`，泛型反射 + 每表 fail-closed）+ 观测 `knownCraftingRecipes`（三态） | dev-coder 排队（218 之后） |
| 3 | task-223 结果 | Furnace 配方合法授予路径定案（`docs/_il-furnace-unlock.md`）；**若结论需要 Mod 侧合法触发入口，则按需加一张卡再进本批** | log-analyst 在制 |
| 4 | task-219 | **意图-执行对账闭环**（`User said (m18972)`）：每个 LLM 意图 `intent_execution` 记录 + 固定原因码 + `<journal>-gaps.json` 缺口清单 + `Brief.recent_gaps` 次日可见 | 待派 |
| 5 | task-220 | analyzer 收 `intent_coverage`/gaps + 判红「有意图 executed_steps==0 却无原因码」+ 连续能力缺口 ⚠ | 待派（blocked_by 219） |

**移出本批**（0.7.40+）：task-210 机器链（craft/place/feed/collect）、task-152/151 目标 1 的升级选型与田区清空验收、task-195/196/193/197 遗留。

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

**装机后必做的真机烟雾（条目 077 的教训，硬性）**：任取一个本批**新增只读技能**（0.7.39 用 `debug_dump table=trigger_actions`）发一次请求，断言**不得回 `unknown_skill`**；失败 ⇒ 立刻停手回滚判红。

## §3 判据

- **通用**：`docs/_run10-criteria.md` 全部条款 + `docs/_run6-criteria.md` 尾部窗口口径；两侧工具（`tools/verify-run3.py`、`tools/analyze-longrun.py`）同向；缺失 ≠ 通过；口径变更须过独立对抗验收。
- **护栏 A（意图-执行覆盖）**：`OBSTACLE_KINDS ∪ CLUMP_KINDS` 每一类，要么能产出可执行目标，要么登记在 `DEFERRED_KINDS` 且简报如实写"暂不支持"；有一条两头都不在 ⇒ 判红。
- **护栏 B（清障有效性）**：`clear_area` 有 ok 步但当天 `farm.blockers` 未下降 ⇒ 该阶段判 incomplete（不得 VERIFIED）。
- **意图对账（task-219）**：LLM 给出的每个意图都必须有 `intent_execution` 记录；`executed_steps==0` 必须有原因码；原因码属能力缺口 ⇒ 进 `gaps.json` 且次日简报可见。
- **零回归**：既有 1055+ 单测 0 红；账本矩阵（green/run2/run7/runA-0732/run9b/run9c/run9d）rc 与旧判决不变。

## §4 风险与已知限制

- **Furnace 配方仍是硬阻塞**：没有铜锭 ⇒ 没有铜斧 ⇒ 目标 1 的树桩/圆木清不掉；task-223 若给不出合法路径，需要走"替代材料来源"或"先清无桩区域"的降级验收（Lead 届时裁定，不许改存档/不许直接写 `craftingRecipes`）。
- **树纳入清障会显著增加体力开销**：树 743 棵，单棵斧头多次挥动；护栏 B 可能让 `clear_area` 阶段大量 incomplete ⇒ 需要 `task-218` 的体力预算与片地优先同时生效，并观察是否把日子拖成 `stamina` 收尾（可接受，但 A″/B″ 前要复核不会天天 `stuck`）。
- **真机次数成本**：每次装机+读档+跑批约 40–60 分钟；本批冻结后优先做 task-214 复跑（假设 B 定案），再进 A″/B″。
- **无人值守昏睡罚金**：已发生 3 次（各 −10% 金币）；游戏开着就必须有人/有脑在跑，跑完立刻 `stop-game.py`（`m02833`）。

## §5 执行记录

（待冻结后填写：日期 / 冻结提交 / dll+manifest 字节 / check-release 原文 / 装机 port / 基线文件 / 五文件指纹 / 烟雾结果）
