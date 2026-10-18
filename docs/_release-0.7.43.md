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
