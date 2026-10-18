# 0.7.43 发布计划（A″/B″ 的最后一道门禁：逐格证据记账 + 事件有界等待）

> 由来：0.7.42 八步真机冒烟（`docs/_smoke-0742.md` / `533e017`）= **5 PASS / 1 FAIL / 2 无法判定**。
> - task-240（冬季可验证性）与 task-241（清障吞吐）的**真机验收面都过了**（冬 6 `verified=true` + `day_justified=true`；旧守卫文案 0 次；`farm.trees` 同日 839→828（−11）；`blocked`/`tool_ineffective` 全 0）。
> - **步 5 真红**：`clear_area` `ok=75` 而 `cleared_tiles` 只记 62（9 个阶段差 1–3、`failed` 全 0）⇒ 逐格证据记账缺口 ⇒ **task-242**。
> - **冬 7 开局 `eventUp=true`（无对话盒）**让整跑 4.92 分钟提前结束（task-243 定案 = 无法判定是哪个事件）⇒ 可能让一个臂开局白烧 ⇒ **task-245**。

## §1 卡片

| 卡 | 优先级 | 内容 | 归属 | 验收面 |
| --- | --- | --- | --- | --- |
| task-242 | P0 | **`clear_area` 逐格证据记账完整性**：`ok` 与 `len(cleared_tiles)` 的差额必须账本可解释（根因已定位：`longrun.py:6644-6676` 只对「`before.kind` 与 `after.kind_after|kind` 都非空且不等」的步记 `cleared_tiles`，其余 `unclear_steps += 1` 只进内部变量；而 `ok = len(oks)` 按步计 ⇒ 差额无痕，machine-runner 实测 `ok == attempted == ok_tiles == tiles == bound_basis`、`engaged == len(cleared_tiles)`） | dev-coder | 9 个历史阶段全部 conforming；≥4 单测 + ≥2 变异；不改 `assigned_undone`/`plot_pending`/护栏 B/`checks` 键集/事件名（新字段须单列） |
| task-245 | P0 | **`eventUp` 有界等待 + 可归因**：Mod `ui.eventId`（三态）；脑侧 `eventUp && activeMenu==null` ⇒ `EVENT_WAIT_TRIES=4` × 15s 重观测（journal `event_wait`），出现对话盒 ⇒ 走 task-228 的 `advance_dialogue`（非提问才推进、提问/职业选择立刻停），等满仍无盒 ⇒ `event_blocked`（带 `eventId/tries/worldSeq`）；永不 dismiss/替选/load_save/sleep 跳过 | dev-coder | ≥5 单测（含"不调用 dismiss/load_save"负向）+ ≥2 变异；C# +≥2 断言 |

顺序：**242 → 245**（同改 `brain/agentfarm/longrun.py`，串行单写者）。

## §2 冻结九步（Lead 独占）

1. `tools/_note-0743.txt`（首行 `v0.7.43`；列 242/245 两条）
2. `python tools/_bump-mod-version.py 0.7.43 --note-file tools\_note-0743.txt`（manifest 0.7.42→0.7.43）
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.43"`（注释 + `--- 历史 ---` 保留 v0.7.42）
4. `dotnet build -c Release --no-incremental`（0 警 0 错；本批 Mod 有 `ui.eventId` 变更 ⇒ dll 应变化）+ C# 自检
5. 冻结提交（`git diff --cached --name-only` 核对；**禁 amend / 禁 `git add -A`**）
6. `python tools/check-release.py --expect 0.7.43`（六项全绿）
7. `python tools/deploy-mod.py --no-quit`（0.7.42→0.7.43）
8. `python -m agentfarm goto Farm`（`PYTHONPATH=<repo>\brain`）
9. `python tools/preflight.py --expect 0.7.43 --save-baseline logs\run10k-baseline.json` ⇒ 记五文件 SHA256

## §3 真机门禁（A″/B″ 前，冒烟只复跑三步）

1. **步 3（A2 砍树）**：`python scratch\smoke-0742.py --phase all --only 3 --no-crops` ⇒ PASS。
2. **步 5（逐格证据）**：0.7.43 bring-up 后跑**至少 1 个游戏日**短跑产出 `logs\longrun-smoke-0743.jsonl`
   （`--phase launch/wait --days 1 --size 5 --max-minutes 30 --max-days 2 --journal logs\longrun-smoke-0743.jsonl --tag smoke-0743 --capture-observe --observe-every 120 --no-crops`），
   然后 `--phase post --only 5,8 --journal logs\longrun-smoke-0743.jsonl --tag smoke-0743 --smapi logs\smoke-0743-smapi-window.txt --no-crops` ⇒ 步 5 全部 conforming（或可解释）、步 8 沿用三条判据。
3. **事件观察**：短跑期间若出现 `event_wait` / `event_blocked`，记录 `eventId`（0.7.43 新增）与等待次数；若 A″ 起点为冬 7 且该事件复现，按 `event_blocked` 如实结束该臂并在证据里写明。
4. 全绿 ⇒ A″/B″ 放行（task-113 rev23，0.7.43，同起点协议，备份目录 `logs\ab-backup\A8-start\`）。

## §4 已知限制（0.7.43 起照实写）

- **冬 7 那个 `eventUp` 事件仍无法归因**（task-243：`currentEvent` 不落盘、SMAPI 无事件行、存档 eventsSeen 3 条；唯一未 seen 且前置可评估的候选 `900553`，其 `A cc_Greenhouse` 语义未定）。0.7.43 只做到「有界等待 + 带 `eventId` 归因 + 仍硬停」，**不保证能自行推进**。
- **`farm.trees` 口径已确认正常**：`FarmScan.cs:371/373-379` Trees = 果树 + 非树桩树（树桩单列 `:398-399`）；存档逐格 836 棵、`stump=true` 4 ⇒ 口径值 832 与实测一致；冬 5 的 −11 有 `TreesChopped=11` 佐证。冬 6 的 +4 需真机同日双采样才能归因。
- **冬季结构限制**：露天 0 作物 ⇒ `harvest`/浇水数据天然为 0，A″ 证据里必须写「农务面不可判」，不得据此判 PASS/FAIL。
- 冒烟骨架的 `--only 3` 只跑 pre（不起长跑）、`--only 5,8` 纯离线（`scratch/smoke-0742.py:1114-1124`）；`--dry-run` 在打印 `[plan]` 之前返回，故 phases 解析只在真跑首行出现。

## §5 冻结与装机执行记录（**事后补记，2026-10-18 17:3x**）

> 由来：0.7.43 的冻结九步由前任会话执行（`2026-10-18 14:4x`），但**冻结后 15:08 会话因上下文硬顶死亡**，`dotnet build` / C# 自检 / `check-release --expect 0.7.43` 的原文没来得及写进任何文档 ⇒ 本节只补**可复核**的部分，没跑过的读数一律不补写。

- **冻结提交**：**`5679562`**（`chore(release): 冻结 0.7.43（事件有界等待 + 清障逐格证据口径 + analyzer 归因）`）；其下 `f3fffad`(task-242) / `0a13973`(task-245) / `aa97f61`+`4ff9861`(task-246)。冻结后 HEAD 只加了文档/scratch（`4ff9861`）。
- **五文件指纹（A8 起跑 sidecar 原文，`logs/longrun-runA8-0743.version.json`；2026-10-18 17:2x 现树重算 5/5 逐字一致）**：

| 文件 | SHA256 | 字节 |
| --- | --- | --- |
| `brain/agentfarm/longrun.py` | `FF031D7791A85DAB54B13E3FC5EAD59C34A24F196C7577CC992E5BD2B878369D` | 591736 |
| `brain/agentfarm/farmwork.py` | `88E14811260363F606EFA55C688E8DDB46E6BF3A7DE1162E2CDC5645F38370A0` | 231217 |
| `brain/agentfarm/bridge.py` | `992FB6A4785A4A25993BDE819F7BC0FA20BA5D48008BF4008CB3DFC95844AFC4` | 69493 |
| `mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll` | `806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F` | 286208 |
| `mod/AgentFarm.Bridge/manifest.json` | `3CED533859272EBC7246012020270F4667654B9435773D079E48FEADB881244C` | 70055 |

- **装机**：`deploy-mod --no-quit` 于 `2026-10-18 14:49` 完成（桥回执 `modVersion=0.7.43 port=17890`；装机目录 manifest `0.7.43` / dll `806C1069…` 与上表一致）。`preflight` 基线 = `logs/run10k-baseline.json`：第 1 年 **冬 7 日 06:40 sunny / Farm(64,15) / 体力 270 / 钱 2767g / farmingLevel 3 / waterLeft 13 / tillable 177 / 作物 0 / 无模态**。
- **缺失留痕（如实）**：`dotnet build --no-incremental` 的 0 警 0 错读数、C# 自检断言数、`check-release --expect 0.7.43` 六项读数 **【无法判定·未落文档】**；事后以「sidecar 五指纹 + 现树 5/5 一致 + 装机回执」为佐证，**不补写未跑过的数字**。
- **真机门禁执行情况**：§3 的「步 3 冒烟」**没有单独跑**；改为用 A8 前 3 天的 `clear_area` 阶段做 task-242 旁证（当班 machine-runner 读数：`ok == len(cleared_tiles)` 全等）。**task-244 的正式冻结树验收是事后做的**（`git archive 5679562`；A/B/C 段 29 PASS / 0 FAIL、变异 5/5 被杀，见 `docs/_review-0.7.43.md`）——即 0.7.43 是**先用于 A8 真机、后补独立验收**，这一点必须与 A8 证据一起如实写。
- **A8 使用情况**：A8 臂在 0.7.43 上跑冬 7→18 共 12 天，因两条系统性死循环未达 5 连绿 ⇒ 判「臂被缺陷支配、不作验收证据」（`docs/_runA8-0743-evidence.md` / 开发日志条目 084）。0.7.43 后续由 0.7.44 取代。`event_wait`/`event_blocked` 在 A8 **0 条**（事件闸门未在真账本出现正例，如实记）。
