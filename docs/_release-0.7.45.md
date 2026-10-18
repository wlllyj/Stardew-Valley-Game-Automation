# 0.7.45 发布计划（A9/B9 前门禁：诚实收工被守卫误判 + 背包满无察觉）

> 由来：0.7.44 **真机冒烟 FAIL**（`logs/longrun-smoke-0744.jsonl`，冬 26/27 两天 `verified=false`）：
> - 冬 26 `ended_reason = stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：今天早些时候还有 263 格没做完（跨片地，最近的是 [12, 17]））`，仅 `checks.day_justified=false`；
> - 冬 27 `resume_exhausted:回片区 217 格都回去看过、换片 4 次，当前观测里没有可执行目标（守卫仍说：今天早些时候还有 217 格没做完（跨片地，最近的是 [38, 36]））`；
> - 即「当前可执行面已没活，但守卫拿整天累积账本（263/217）当活」⇒ 本该 VERIFIED 的日被判 needs_review。判据链：`is_justified_end` 白名单只认 `night/stamina/no_work`（`brain/agentfarm/longrun.py:553/563-572`），`stuck:`/`resume_exhausted:` 都不认；`_pending_work()`（旧 `:4816-4833`）未剔停滞/挡死格；burst 收尾（旧 `:8665-8676`）仍写 `stuck:`。
> - 另暴露：背包容量 12 全满（`free_slots=0`）而 clear-only 日主循环根本不查背包 ⇒ 砍树/挖石掉落被游戏拒绝、战利品全丢（用户真机红 X "Inventory Full" 佐证），账本 0 条相关事件。
>
> 处置：开 task-15（P0 门禁）与 task-16（P1 背包），修完重走九步 + 重冒烟（task-18，tag smoke-0745）→ 才放行 A9/B9。

## §1 卡片

| 卡 | 优先级 | 内容 | 归属 | 状态 |
| --- | --- | --- | --- | --- |
| task-15 | P0 | **守卫只对当前可执行/可达待做格敏感**：`_pending_work()` 剔 `resume_stall_tiles`/`encircled_day`，原始账本另存 `_ledger_pending()`；`_pending_snapshot` 六口径并列；`is_justified_end` 增证据门槛（`resume_exhausted` 仅 `pending_executable==0` 才认，`stuck:` 永不认，观测缺失 fail-closed）；burst/换片上限改走诚实收工；sleep_guard no_work 防白拿；day_end 并列留痕 + `stage_midway_leftover`；checks 10 键不变 | dev-coder | `e347aaa`（定向 6/6 OK、自报全量 1317 OK、变异 4/4） |
| task-16 | P1 | **背包满留痕/腾格**：每次观测算 `free_slots = inventoryCount − len(inventory[])`；`free_slots==0` 走 slot_relief 压力通道（白名单/建造预留/每 qid 下限；工具/武器/种子/建材/锭永不卖；卖走 `Farm.shipItem`/`sell` + 观测差分）；清障掉落被拒留 `loot_lost`（info）；买种前满包先腾格；不因背包满判失败；Deluxe Backpack 2000g 交 task-14 评估 | dev-coder | `3a5d24c`（定向 9+57 OK、自报全量 1326 OK、变异 5/5） |
| task-22 | P0 | **残缺 tile 不得算 unobserved 放行**（deputy NIT-1 fail-open）：观测 `tiles[]` 里出现但缺 kind/crop 的残缺记录 ⇒ fail-closed（计 executable 或 `malformed_tiles>0` 且 `day_justified` 必 false）；账本格不在观测 tiles[] 的仍算 unobserved（冬26 的 2 格）；冬26/27 重放语义不变 | dev-coder | 在做（0.7.45 冻结前最后一卡） |

## §2 冻结九步（Lead 独占）

1. `tools/_note-0745.txt`（首行 `v0.7.45`；列 task-15/16 与真机失败原因）
2. `python tools\_bump-mod-version.py 0.7.45 --note-file tools\_note-0745.txt`
3. `brain/agentfarm/bridge.py:39` 起 `MOD_VERSION_EXPECTED = "0.7.45"`（注释 + `--- 历史 ---` 保留 v0.7.44 全文）
4. `dotnet build -c Release --no-incremental`（0 警 0 错；本批 Mod 无代码变更 ⇒ 预期 dll 与 0.7.44 同哈希 `806C1069…`）+ C# 自检
5. 冻结提交（按路径 add；**禁 amend / 禁 `git add -A`**；`git diff --cached --name-only` 核对）
6. `python tools\check-release.py --expect 0.7.45`（六项全绿）
7. `python tools\deploy-mod.py --no-quit`（先确认无游戏进程 + 无 stale bridge.json）
8. `PYTHONPATH=<repo>\brain python -m agentfarm goto Farm`
9. `python tools\preflight.py --expect 0.7.45 --save-baseline logs\runA9-baseline.json` ⇒ 记五文件 SHA256

## §3 真机重冒烟门禁（A9 前必过，tag smoke-0745）

1. 用 0.7.42 门禁骨架 `scratch\smoke-0742.py` 四阶段（参数以脚本为准，`run-longrun.py` 没有 `--tag/--no-crops`）：
   - `python scratch\smoke-0742.py --phase pre --tag smoke-0745 --expect-version 0.7.45 --no-crops`
   - `python scratch\smoke-0742.py --phase launch --tag smoke-0745 --expect-version 0.7.45 --days 1 --size 5 --max-minutes 60 --max-days 2 --capture-observe --observe-every 120 --no-crops`
   - 起跑成功后**立即** `python tools\run-guardian.py --tag longrun-smoke-0745 --detach`
   - `python scratch\smoke-0742.py --phase wait --tag smoke-0745 --wait-minutes 60`
   - `python scratch\smoke-0742.py --phase post --tag smoke-0745 --freeze-smapi --no-crops`
2. **放行判据**：至少 1 天 `verified=true`；0.7.44 冒烟步 8.1 由 FAIL 转 PASS；`day_end.pending_executable=0` 时 `day_justified` 必须 true；再出现 `stuck:` 掩盖 ⇒ 不放行。
3. **证据质量附则（product-observer 审计后新增）**：`no_work` 早收工也会判 VERIFIED（A8 的 7 个 VERIFIED 日全是 07:10–11:00 的 no_work）⇒ 冒烟/A9 的 VERIFIED 判定必须同时看 `ended_by`、`ok_steps`、`pending_executable`；**只有 `no_work` 且 ok_steps≈0 的 VERIFIED 日不得单独作为「连续 5 日」达标证据**。
4. 冒烟后必须优雅退游戏（guardian 自动或 `stop-game.py --wait 45`），并在 `docs/_smoke-0745.md` 留两日读数/六串/存档四件。

## §4 A9/B9 协议（与 0.7.44 同起点同 argv，版本改 0.7.45）

- **起点**：`logs/ab-backup/A9-start/`（winter 26，四件 SHA256 已在 0.7.44 §6 登记，MANIFEST `5479354B…`）；A9 前 `arm-start-helper.py verify --arm A9` 必须 4/4 OK，`restore` 后逐件再核。
- **A9**：`python tools\start-detached-longrun.py --journal logs\longrun-runA9-0745.jsonl --expect-version 0.7.45 --days 5 --size 5 --max-minutes 240 --max-days 12`；起跑后立即 `run-guardian --tag longrun-runA9-0745 --detach`。
- **B9**：`restore --arm A9` 还原 + SHA256 核对；A9 的 `logs\longrun-runA9-0745-lessons.json` **字节拷贝**为 `logs\longrun-runB9-0745-lessons.json`；同 argv 起 `logs\longrun-runB9-0745.jsonl`（guardian `--tag longrun-runB9-0745`）。
- **判据**：`verify-run3 --days 5 --smapi` + `analyze-longrun --window 5` + `compare-runs` L0–L5 + 三检查器 + 外部证据（六串 ≥5/5、每日 ≥2 份独立观测、存档四件、优雅退出四项）；**already 双列并读**（`stages[].ok` 与 `stages[].already`，见 task-10 #1）。
- **尾部口径**：冬 26/27/28 为热身，尾 5 天应落 spring 1–5（12 天上限到 spring 9）；spring 首次出现真实农务腿（买种/播种/浇水/收获），是目标 2 的主要证据面。
- **纪律**：游戏只要开着必须有脑在跑；跑完立刻优雅退；不 load_save 到别的档。

## §5 已知限制（照实写）

- 春季农务腿（买种/播种/浇水/收获）在 0.7.44 及以前**从未真机完整验证**；0.7.45 只修了收工判定与背包留痕，不能保证春季腿无新缺陷 ⇒ A9 若被新缺陷支配，先止损再决定是否冻 0.7.46。
- 背包容量仍为 12（未买升级）；腾格上限约 3 格（Clay/Geode/Wheat）；背包升级 2000g 交 task-14 评估。
- 冬 26 的 40 格账本无坐标（观测 10 片×25=250<263 截断）⇒ 逐格归属【无法判定】；冬 27 的 217 精确闭合（220−3 挡死）。
- `no_work` VERIFIED 日证据力弱（见 §3 附则）；L2/L3 对照需要春季作物面，冬季尾巴无面可测。
- **边界裁决（task-16，Lead 2026-10-18）**：槽位压力通道按 `free_slots==0` 触发，不按卡面字面 `<=SLOT_RESERVE(1)`——因为 `TestTask198SlotRelief.test_one_free_slot_and_one_ripe_crop_does_not_relief` 钉死「1 空格 + 1 熟作物不许白卖腾格」（0.7.40 边界），而缺的正是「真满 0 格 + 无收获需求」这条；买种需求（需要 1 格）由买种前腾格路径独立覆盖。腾格上限约 3 格（Clay/Geode/Wheat）如实报。
- LLM 输入仍缺容量/当季性/工具等级，取消原因不回灌 ⇒ L3/L4「据结果优化」证据不足，task-20（卡 C，0.7.46）补齐。

## §6 冻结记录（待冻结后由 Lead 填实测原文）

| 项 | 读数（2026-10-18 实测原文） |
| --- | --- |
| 冻结提交 | `2feb1f8d607629b0dabd5694b4d88d261e266983` `chore(release): 冻结 0.7.45（诚实收工判据/背包满留痕/残缺 tile fail-closed）`，3 files +31/−5（brain/agentfarm/bridge.py、mod/AgentFarm.Bridge/manifest.json、tools/_note-0745.txt）；父提交 `18c415e`。 |
| 版本一致性 | manifest `Version=0.7.45` / brain `MOD_VERSION_EXPECTED="0.7.45"`；manifest 头部 Description=`v0.7.45（2026-10-18）…`。 |
| dll / manifest | dll 286208B SHA256 `806C1069D217EEEFAB6D3354BA09DA049847D97EE5B4A1D2D65845F1DCB0B17F`（与 0.7.44 逐字节相同 ⇒ Mod 无代码变更，符合预期）；manifest 73663B SHA256 `DECBA6775569D7C42DF910E7E6A72BC2CF59B1E2729C29484E700F6E786A2E5C`；装机后 dll/manifest 与仓库逐字节一致（同长度同哈希）。 |
| build / C# 自检 | `dotnet build -c Release --no-incremental`（mod/AgentFarm.Bridge）= 0 警告 0 错误（3.20s）；`dotnet run -c Release`（mod/AgentFarm.Bridge.Tests）= `OK 91 断言全部通过`；`python -W error::SyntaxWarning -m py_compile brain\agentfarm\bridge.py` rc=0。 |
| check-release | `python tools\check-release.py --expect 0.7.45`：六项全绿 —— 版本一致、dll 18:54:09 不比源码旧（最新 WorldSnapshot.cs 14:36:09）、py_compile 30 文件、全量 **Ran 1330 tests / OK**、工作树干净（首跑因 log-analyst 两个未跟踪 scratch 探针红 ⇒ 提交 `1830e28` 后复跑全绿；末行文案仍写「四项全绿」系脚本旧文案）。 |
| 装机 / goto / preflight | `deploy-mod.py --no-quit`：0.7.44 → 0.7.45，桥 `modVersion=0.7.45 port=17890`，load_save 进 `Wahaha_450799035`（FarmHouse(9,9)）`[OK] 部署闭环完成`；`agentfarm goto Farm` OK（FarmHouse→Farm，landing=[64,15]，7653ms）；`preflight.py --expect 0.7.45 --save-baseline logs\runA9-baseline.json` ⇒ `✅ 可以起跑`（基线 700B SHA256 `141F7EDE8F543F3A85CAE5EFFE9C63939F966EF9D5433BB381A9D08415EA07E7`，冬28 06:00 Farm/钱2767/体力270/种子 483×10/耕地8/作物0/tileCount 400）。**注**：该基线取自当前档（winter 28，冒烟推进后的档）；A9 起跑前 restore `A9-start`（winter 26）后必须按 §4 重跑 preflight 并重写基线，以 restore 后读数为准。 |
| 收尾 | `stop-game.py --wait 45`：quit_game 回执 ok、原 pids=[10532] 消失 ⇒ 进程 0 / 仓库根 `bridge.json` 不存在 / 17890 无 LISTENING / AppData 无残留。 |
| 冒烟（smoke-0745） | 待 machine-runner 执行（tag `smoke-0745`；门禁见 §3，≥1 天 VERIFIED 才放行 A9）。 |
