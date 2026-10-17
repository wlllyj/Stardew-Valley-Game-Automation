# 0.7.37 发布计划 — 收获证据面的三条残留收口（R7/R8/C2-a）+ 测试编码护栏

> 状态：**草稿（跑批期间不动生产代码）**。0.7.36 正在做 A′/B′（task-113）两次 5 天长跑；本批要等跑批结束、工作树解冻后才开工。
> 前置：`docs/_release-0.7.36.md`（0.7.36 冻结装机 + task-191 真机复测 PASS + `§5.5`）；`docs/_run10-harvest-verify-0736.md`（task-191 真机取证，R7/R8 出处）。

## 0. 为什么有这一版

0.7.36 把收获证据面收到「判据落在世界证据上、回执只作线索」，task-191 真机四条判据全绿。真机同时暴露三条**口径外**的残留（不阻塞 A′/B′，但会影响「回执可信度」与「附带效果记账」的长期可信）：

- **R7（Mod）**：原始 `use_tool(tool="scythe")` 打在不 `ready` 的目标格上 ⇒ Mod 回执 `acted=true` / `actedEvidence="readyCrops"`，reason 却谎称该格「上面已经没有东西了」（实际仍在），真实效果是**连带清掉 4 格**（`crops 102→98`、`readyCrops 101→97`、`emptyDirt 51→55`，含未成熟作物）。⇒ `actedEvidence` 是**聚合口径**，与「目标格」写在同一份回执里会误导；原始技能无脑侧守卫时是破坏性的。
- **R8（brain）**：镰刀收割时顺带割草 ⇒ 背包 `Moss +1` 未进 `loot` / `affected_tiles`（脑侧**没多报**，是**没记账**）；机检脚本按「全量背包差」口径会误判 FAIL。
- **C2-a（brain，task-190 骨架复现）**：有格子级证据时白名单取整份 `gained`，同一次动作顺手进包的无关注 qid 仍会进白名单。
- **工程侧（tests）**：全量单测**依赖 `PYTHONUTF8`** —— 不带时 `test_longrun.TestTask182ClumpRulesBehaviour::test_csharp_rules_self_test_passes` 假红（C# 自检的 UTF-8 输出被按 cp1252 解码）。

## 1. 本批卡片（入版范围）

| 卡 | 侧 | 内容 | 验收 |
|---|---|---|---|
| **task-195** | Mod | `actedEvidence` 必须对得上**目标格**（或明确标注聚合来源）；原始 `use_tool` 在目标格 `ready!=true` 时不得静默连带（fail-closed 或如实报连带影响） | `dotnet build` 0 警 0 错 + C# 自检 ≥3 条新断言（目标格不可收时不得声称已空 / 连带影响必须入回执 / 证据能区分目标格与聚合）+ ≥3 变异 |
| **task-196** | brain | 附带掉落与目标格掉落**分栏记账**（`loot` / `collateral_loot`）+ `affected_tiles` 如实 + 口径说明（全量背包差 ≠ 白名单逐 qid 差） | ≥4 单测 + ≥2 变异 + 口径写进 `docs/_run10-criteria.md` 或 `docs/_analyze-longrun-caliber.md` |
| **task-193** | analyzer | 白名单归因收紧（C2-a）+（若 task-196 需要）新字段入桶；旧账本判决与计数不得变化 | 单文件 OK + 全量 OK + 六账本 rc/红数/#无法判定**并排**给旧版读数 |
| **task-197** | tests | 消除子进程抓 stdout 的编码依赖（显式 `encoding="utf-8"` 或 ASCII 标记断言）+ 「不带 PYTHONUTF8 也绿」回归护栏 | 两种环境（带/不带 `PYTHONUTF8`）都 `Ran N / OK`，读数原文贴进交付 |

## 2. 冻结九步（Lead 独占，链条冻结后一次做完）

1. `tools\_note-0737.txt`（**首串必须 `v0.7.37`**，列本批 Mod 侧改动）。
2. `python tools\_bump-mod-version.py 0.7.37 --note-file tools\_note-0737.txt` ⇒ manifest `0.7.36 → 0.7.37`（用 `json.load` 复核，别信最后那行 print：cp1252 下它会 UnicodeEncodeError 但文件已写）。
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.37"`（注释补本批条目、上一版转历史）。
4. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**；记 dll/manifest 的 size 与 mtime。
5. `git add -A && git commit`（冻结提交；**先提交再 check-release**）。
6. `python tools\check-release.py --expect 0.7.37` ⇒ 六项全绿（含 `Ran N tests`、树干净）。
7. `python tools\deploy-mod.py --no-quit` ⇒ 桥 `modVersion=0.7.37`、自动读档。
8. `python -m agentfarm goto Farm` ⇒ ok。
9. `python tools\preflight.py --expect 0.7.37 --save-baseline logs\run10e-baseline.json` ⇒ 四项全绿；把五文件 SHA 前 16 位发给下一张真机卡。

## 3. 判据

- **task-195 真机**：在 `(60,29)/(60,30)` 类格上，`use_tool` 回执的证据必须能追溯到**目标格**；对未成熟/不可收格发原始 `use_tool` ⇒ 要么被拒，要么回执如实写连带影响（受影响格清单），**不得**出现「目标格没变却说它已空」。
- **task-196**：镰刀顺带割草 ⇒ `collateral_loot` 记录 `Moss +1`；`loot` 仍只含目标格白名单项；口径不一致**不判失败**。
- **task-193**：六账本判决/计数与旧版并排一致（`#无法判定` 允许因修 bug 下降，需给出两列）。
- **task-197**：带与不带 `PYTHONUTF8` 均全绿。

## 4. 已知限制 / 风险

- 本批**不碰** `checks` 键集、不碰 `_leftover` / `JUSTIFIED_END_REASONS` 语义（0.7.36 的边界继续有效）。
- `acted` 仍是「跨观测证据」的推断，不是游戏的真值；任何新字段都要 **fail-closed**（缺 ⇒ 不采信）。
- 目标是**先把目标 2 的 A′/B′ 跑出来**；本批是跑批后的加固，不得插入跑批窗口。

## 5. 执行记录（待填）

- 5.1 链条（冻结前）：待填
- 5.2 冻结（提交 hash）：待填
- 5.3 装机与基线：待填
- 5.4 指纹与移交：待填
