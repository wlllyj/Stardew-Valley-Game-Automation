# 0.7.44 发布计划（A9/B9 前门禁：两条死循环修复 + 收工口径）

> 由来：A8 臂（0.7.43，`logs/longrun-runA8-0743.jsonl`，冬 7→18 共 12 天）**最好连续 3 天 VERIFIED、尾部 5 天只有 1 天**，未达目标 2 的「连续 5 日」。5 个失败日（冬 7/9/12/14/18）全部落在两条**系统性死循环**上，不是能力不足：
> - **A. `work_spot_resume` 拿不出目标 ⇒ 整天判 stuck**（冬 7/12/18；收工前已做成 46/13/19 步、账本里还有别的片区的可执行格）。
> - **B. 1 格余量反复重分配**（冬 9/14；`encircled[37,35]` / `unreachable[40,30]/[40,31]/[41,31]`，28–60 个 `assigned=1/assigned_undone=1/stopped=incomplete` 阶段空转到 `stuck`）。
>
> 判决（用户 2026-10-18 17:2x 确认）：**A8 = 臂被缺陷支配、不作 A″ 验收证据**（同条目 076 的 A′ 先例）；修 0.7.44 后重跑 **A9/B9**。

## §1 卡片

| 卡 | 优先级 | 内容 | 归属 | 验收面 |
| --- | --- | --- | --- | --- |
| task-4 | P0 | **`work_spot_resume` 拿不出目标不许判 stuck**：先换片/换田区（坐标只取当前观测或账本记账），仍无可执行才走诚实收工；新增 journal 事件+原因码（如 `work_spot_switch`/`resume_exhausted`）；不改语义键/checks 10 键 | dev-coder | ≥4 单测（含「有别的片可做⇒换片」「确实没活⇒诚实收工不 VERIFIED」「encircled 不算可执行」）+ ≥2 变异 |
| task-5 | P0 | **挡死格不进下一轮分配**：`encircled`/`unreachable`/`blocked_by_tool` 当天不得重分；`leftover` 拆「可执行余格 vs 物理挡死格」；同格当天尝试有界、留痕；不得放宽 `no_unmet_stages`/护栏 B | dev-coder | ≥5 单测 + ≥2 变异；A8 账本形态离线复现（冬 9/14） |
| task-6 | P1 | **收工口径**：①stuck 路径 `checks.slept_by_us` 快照取真值（冬 9/14 原为 false 但 sleep 实际成功）；②「只因预算延后」与「户外浇水达标」不得同真（analyzer 报 6 行） | dev-coder | ≥4 单测 + ≥2 变异；口径变更清单交 deputy 对抗验收 |

顺序：**task-4 → task-5 → task-6**（同改 `brain/agentfarm/longrun.py`，串行单写者）。

## §2 冻结九步（Lead 独占）

1. `tools/_note-0744.txt`（首行 `v0.7.44`；列 task-4/5/6）
2. `python tools/_bump-mod-version.py 0.7.44 --note-file tools\_note-0744.txt`（manifest 0.7.43→0.7.44）
3. `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.44"`（注释 + `--- 历史 ---` 保留 v0.7.43 全文）
4. `dotnet build -c Release --no-incremental`（0 警 0 错；本批预期 **Mod 无代码变更 ⇒ dll 与 0.7.43 同源重建**，以实测为准）+ C# 自检
5. 冻结提交（`git diff --cached --name-only` 核对；**禁 amend / 禁 `git add -A`**）
6. `python tools/check-release.py --expect 0.7.44`（六项全绿）
7. `python tools/deploy-mod.py --no-quit`（0.7.43→0.7.44；先确认无游戏进程）
8. `python -m agentfarm goto Farm`（`PYTHONPATH=<repo>\brain`）
9. `python tools/preflight.py --expect 0.7.44 --save-baseline logs\runA9-baseline.json` ⇒ 记五文件 SHA256

## §3 真机门禁（A9 前）

1. **短跑 ≥1 天**（用 0.7.42 门禁骨架 `scratch\smoke-0742.py` 四阶段；`--phase/--capture-observe/--observe-every/--no-crops` 都是它的参数，`run-longrun.py` 没有；tag=smoke-0744 ⇒ journal `logs\longrun-smoke-0744.jsonl`、pid `logs\longrun-smoke-0744.pid`）：
   - `python scratch\smoke-0742.py --phase pre --tag smoke-0744 --expect-version 0.7.44 --no-crops`
   - `python scratch\smoke-0742.py --phase launch --tag smoke-0744 --expect-version 0.7.44 --days 1 --size 5 --max-minutes 60 --max-days 2 --capture-observe --observe-every 120 --no-crops`
   - 起跑成功后**立即** `python tools\run-guardian.py --tag longrun-smoke-0744 --detach`
   - `python scratch\smoke-0742.py --phase wait --tag smoke-0744 --wait-minutes 60 --capture-observe --observe-every 120 --no-crops`
   - `python scratch\smoke-0742.py --phase post --tag smoke-0744 --freeze-smapi --no-crops`

   在 winter 26 上应至少 **1 天 `verified=true`**（若仍无作物，浇水/收获子项记【无法判定·无作物】）。
2. **两条死循环的离线判据**：用 A8 账本当夹具，新逻辑重放后冬 7/12/18 不再出现 `work_spot_resume` 式 stuck、冬 9/14 不再出现 28–60 个 1 格阶段（作者脚本 + deputy 的独立变异都要两列）。
3. `smoke-0742.py` 的步 3（砍树）/步 5（逐格证据）/步 8（幂等/事件）沿用 0.7.43 结论；步 5 用新账本重跑 `--only 5` 必须全部 conforming。
4. 全绿 ⇒ A9/B9 放行。

## §4 A9/B9 协议（用户 2026-10-18 已授权：新起点 winter 26，全授权真机/存档）

- **起点**：当前存档第 1 年 winter 26（钱 2767g，无作物）→ `python scratch\arm-start-helper.py backup --arm A9` ⇒ `logs\ab-backup\A9-start\`（四件 + MANIFEST）。
- **A9**：0.7.44 装机后起跑，`python tools\start-detached-longrun.py --journal logs\longrun-runA9-0744.jsonl --expect-version 0.7.44 --days 5 --size 5 --max-minutes 240 --max-days 12`；起跑成功立即 `python tools\run-guardian.py --tag longrun-runA9-0744 --detach`。**冬 26/27/28 三天为热身**（winter 28 天：26→27→28 之后才是 spring 1），**尾 5 天应落在 spring**（提前达标则 spring 1–5）；解决 0.7.43 §4「冬季农务面不可判」。**A8 与 A9 是不同起点 ⇒ 两对臂不可跨对比较，证据 §1 写明「新的一对起点」。**
- **B9**：A9 收工后 `arm-start-helper.py restore --arm A9` 还原并逐件 SHA256 核对；A9 的 `logs\longrun-runA9-0744-lessons.json` **字节拷贝**为 `logs\longrun-runB9-0744-lessons.json`；同 argv 起 `logs\longrun-runB9-0744.jsonl`（guardian `--tag longrun-runB9-0744`）。
- **判据**：`verify-run3 --days 5 --smapi` + `analyze-longrun --window 5` + `compare-runs` L0–L5 + 三检查器 + 外部证据（六串 ≥5/5、每日 ≥2 份独立观测、存档四件、优雅退出四项）。
- **纪律**：起跑必须带 task-9 看护守护（脑进程消失 ⇒ 自动 `stop-game`）；游戏只要开着必须有脑在跑；跑完立刻优雅退。

## §5 已知限制（照实写）

- 春季农务腿（买种/播种/浇水/收获）是 **0.7.43 及以前从未在真机被完整验证过**的能力面；A9 可能暴露新缺陷 ⇒ 届时按「臂有效性」判：若被新缺陷支配，先止损再决定是否冻 0.7.45。
- A8 的无人值守 7 次落盘（冬 19→26）全部**列废数据**，不进任何证据；A8 终态存档四件【无法判定】。
- `event_wait`/`event_blocked` 在 A8 真账本 **0 条**（事件闸门仍缺真机正例）。

## §6 冻结记录（2026-10-18 18:2x，Lead 实测原文登记）

| 项 | 读数 |
| --- | --- |
| 冻结提交 | `37cac51`（`chore(release): 冻结 0.7.44（四卡收工/分配死循环修复）`，3 文件：`brain/agentfarm/bridge.py` / `mod/AgentFarm.Bridge/manifest.json` / `tools/_note-0744.txt`） |
| 版本一致性 | manifest `Version=0.7.44` / brain `MOD_VERSION_EXPECTED="0.7.44"` |
| dll | **`806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F`**（286208B；**与 0.7.43 冻结 dll 逐字节相同 = 本批 Mod 无代码变更，符合 §2 步 4 预期**；repo 与装机同哈希） |
| manifest | `77003E0B9EBD0C0644787831AF814274A9283BFC857BB5DF271FB3D9BF49DB92`（71491B；repo 与装机同哈希） |
| build / C# 自检 | `dotnet build -c Release --no-incremental` = **0 警 0 错**；C# 自检 **91 断言全部通过**（rc=0） |
| check-release | `--expect 0.7.44` **六项全绿**：版本一致 / dll 不比源码旧 / `py_compile`（27 文件）/ 全量单测 **`Ran 1277 tests / OK`** / 工作树干净（末行文案仍写「四项全绿」，系脚本旧文案，六项读数逐条见输出） |
| 装机 | `deploy-mod.py --no-quit`：0.7.43→0.7.44，桥 `modVersion=0.7.44 port=17890`，`load_save` 进 `Wahaha_450799035`（FarmHouse(9,9)）；`goto Farm` OK（landing=[64,15]，7643ms）；`preflight --expect 0.7.44` ⇒ ✅ 可以起跑（`logs/runA9-baseline.json` `7082F6F4…`，701B） |
| 收尾 | `stop-game.py --wait 45` ⇒ 优雅退出；进程 0 / 根 `bridge.json` 已删 / 17890 无 LISTENING / AppData 侧 bridge.json 无残留 |
| A9-start 备份 | `logs/ab-backup/A9-start/`：`Wahaha_450799035` `053CAA71…`(3141826B) / `SaveGameInfo` `3D964F3F…`(32305B) / MANIFEST `5479354B…`(1222B)；起点 = 第 1 年 **冬 26**（17:03:52 存档，2767g、作物 0、Wheat Seeds 10、waterLeft 13、farmingLevel 3） |

> 缺口/限制（照实）：①真机冒烟（§3）尚未做，未绿则 A9 不放行；②`deploy-mod` 自带的存档备份在 `logs/deploy-*/`，与本表的 A9-start 不是同一个口径，判据以 A9-start MANIFEST 为准；③本表所有哈希均为 2026-10-18 18:2x 实测，未使用任何事后推算值。
