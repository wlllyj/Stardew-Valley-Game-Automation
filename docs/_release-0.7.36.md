# 0.7.36 发布计划 — loot 白名单收敛（task-186/189）+ Mod `use_tool` 回执诚实化（task-188）+ 认输释放的末态记账（task-192）

> 立卡时间：2026-10-17（Lead）。来源：task-184 真机复测残留 R1/R2/R3（`docs\_run10-harvest-verify-0735.md`，machine-runner `61031b6`）+ task-185 的 NIT-1（`docs\_review-task168.md`，deputy-lead `bd50814`）。

## 0. 为什么有这一版

0.7.35 把「收获成功」的真相钉死了（task-181/182/168），同格复测也过了三源一致。但同一次复测暴露三条**残余不彻底**：

- **R1（Mod）**：`use_tool` 路径（镰刀类作物）**没有** `acted`/`actedEvidence` ⇒ 回执仍可能是"世界变了却报没动手"的另一半；`skill:"use_tool"` 的 reason 还会渲染成空物品名（R4 文案）。
- **R2（brain）**：多格一次动作（一镰刀连收 4 格）与"并入既有叠"的 loot 记账靠**动作后第一张观测**，落下物有延迟 ⇒ 真机上 `(O)262 +4 / (O)178 +2` 被脑侧读成"背包没有新增物品"；判据本身没写错，是**时序 + 文案**把"还没看见"当成了"确实没有"。
- **R3（判据/文档）**：`interact` 的 `worldSeq` 可能不动（60→60）⇒ 不能拿它当成功信号；已写进 `docs\_run10-criteria.md` §5。

外加一条 task-185 的 NIT-1：`_release_zone` 释放认输区时**不扣当天认输记账** ⇒ `day_end.scope_shed_tiles` 记的是"曾经认输过多少格"而不是"日终仍在认输态多少格"，雨天「先认输 → 雨浇好 → 释放 → 其余活做完」的**诚实日**会被工具误判成 needs_review。判据修在工具侧（净额对账，`3ccc29b`），记账修在脑侧（task-192）。

## 1. 本批卡片（入版范围）

| 卡 | 所有者 | 内容 | 状态 |
|---|---|---|---|
| **task-186** | dev-coder | F1 缺格不许当"crop 消失"（`crop_gone = tile_seen and not crop`，且 `tile_seen` 同时把关 `ready`/`readySource` 两路）+ F3 白名单绑格子级证据（`whitelist_bound`/`tile_seen`，sell 事件加 `whitelist`/`whitelist_count`/`whitelist_source`）+ F5 措辞 | ✅ `c67b85f`（949 OK） |
| **task-189** | dev-coder | R2 loot 记账：有界确认（`LOOT_CONFIRM_TRIES=2` × 0.35s，只服务背包）+ 与 `affected_tiles` 对账 + 废止"背包没有新增物品"这句 + `loot_waits`/`loot_unconfirmed` | ✅ `7f9c719`（952 OK） |
| **task-188** | dev-coder | R1/R4（Mod）：`use_tool` 也走 task-182 的跨观测证据 + fail-closed；reason 文案不再渲染空物品名；C# 自检工程 ≥+3 断言 | 在制 |
| **task-192** | dev-coder | NIT-1（brain）：`_release_zone` 释放时扣当天认输记账并同步 `rep.scope_shed`/`shed_zones` 为**日终末态**；护栏一律不放宽 | 待做（排 188 后） |
| **task-190** | deputy-lead | task-186/188/189 独立对抗验收（自建变异实跑、C5 Mod 回执复核、C6c 作者自报变异映射实测、C2-a 记 NIT） | 骨架已就（`b632b42`，24 PASS/0 FAIL/2 SKIP） |
| **task-191** | machine-runner | 0.7.36 真机复测：镰刀格走 `use_tool` ⇒ 脑侧 `ok` + Mod `acted/actedEvidence` + 世界证据三者一致；多格 loot 记账与 `loot_waits` 如实 | blocked_by 190 |
| task-113（改） | machine-runner | **A′/B′ 复跑**（同构建、argv 只差 `--journal`；B 起点 = A 的 lessons 字节拷贝）⇒ L0–L5 | blocked_by 191 + 冻结装机 |

**不入本版**：task-193（白名单只收本格作物产物 id）、task-175（`harvest_gave_up` 窗口依赖）、task-174（账本 farm 白名单补 `ripeCrops`/`readyCrops`）、目标 1 的经济/工具链（task-141/142/151/152/155）⇒ 0.7.37+。

## 2. 冻结九步（Lead 独占，链条冻结后一次做完）

1. `tools\_note-0736.txt` 首串必须是 `v0.7.36`（列本版 Mod 侧改动：task-188）。
2. `python tools\_bump-mod-version.py 0.7.36 --note-file tools\_note-0736.txt` ⇒ `manifest 0.7.35 → 0.7.36`（`json.load` 复核）。
3. `brain/agentfarm/bridge.py` 的 `MOD_VERSION_EXPECTED = "0.7.36"`（注释补 v0.7.36 条目，历史保留）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**；记 dll / manifest 字节数。
5. `git add -A` + 冻结提交（工作树必须干净，否则 `check-release` 会红）。
6. `python tools\check-release.py --expect 0.7.36` ⇒ **六项全绿**（含全量单测、dll 不比源码旧、工作树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ `0.7.35 → 0.7.36`，桥 `modVersion=0.7.36`，自动读档。
8. `python -m agentfarm goto Farm` ⇒ `preflight --expect 0.7.36 --save-baseline logs\run10d-baseline.json` 四项全绿。
9. 把五文件指纹 + argv + 现场读数发 machine-runner，GO **task-191**。

## 3. 判据

- **task-191（真机）**：镰刀格（`(60,28)` 类）走 `use_tool` ⇒ 脑侧 `ok` **且** Mod `acted=true`/`actedEvidence` 非空 **且** 世界证据至少一条；多格 loot 逐 qid 记账与 `loot_waits` 如实；出现"世界变了仍报 no_action"或"脑侧 ok 但世界没变" ⇒ FAIL + 最小复现。
- **A′/B′**：`tools\run-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12`；三检查器（`verify-run3` / `analyze-longrun` / `run9-lead-check`）同向 + L0–L5（`compare-runs`，L1 用 `hint`/`symptom` 口径 + `lesson_section_present` 双信号）。
- **目标 2 的验收**：连续 5 个游戏日 VERIFIED + 每日 ≥2 份独立观测 + 落盘五/六串配对 + L0–L5 对照；`history_problems` 只呈现，**尾部窗口**必须零问题。

## 4. 已知限制 / 风险

- **C2-a（deputy-lead task-190 骨架复现，记 NIT）**：有格子级证据时白名单取整份 `gained`，同动作顺手进包的无关注 qid 仍会进白名单（构造：收成 + `(O)128` ⇒ `harvested={'(O)128': 1}`）。这是**归因不彻底**（原洞"只凭背包差分也进白名单"已堵），不影响四腿与禁卖物清单 ⇒ 不阻塞本版，收紧见 **task-193**（0.7.37）。
- **`readyCrops == crops`**：游戏口径，不是 fail-open；本版不动目标池收窄，靠 `harvest_gave_up` 兜底。
- **`acted` 扩权到 `use_tool` 后**：必须防"世界变了但与本次动作无关"；`actedEvidence` 如实落来源，脑侧仍以观测差分判成功。
- **有界确认的代价**：`LOOT_CONFIRM_TRIES=2` × 0.35s 只在有格子级证据时发生 ⇒ 每天最多几次 × 0.7s，可忽略；但"真丢在地上"的情况会多花 0.7s 并如实写"对不上"。
- 时间预算：本批 4 张实现卡（186/189 已完成）+ 1 张对抗验收 + 1 张真机 + 2 次 5 天长跑。
