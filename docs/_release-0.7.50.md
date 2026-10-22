# 0.7.50 发布计划（A9 重跑前置批：task-240b 买种子 catch-22 + task-241 季节感知选品 [+ 待定：死锁逃生/走路预算]）

> 日期：2026-10-19（夜）。前置：0.7.49 冻结指针 `daceb48`（条目096），T16/T17 已过；今日 A9-0749 三跑全败（条目097），败因=买种子三重死锁 + 冬季盲选品 + 走路预算耗竭。
> 本版动机：把条目097 定位的败因修成合规交付，按九步重冻为 **0.7.50**，为 deploy + 1 日 smoke-0750 + A9/B9（winter26 起跑，热身三天 + 判定 spring1-5）做准备。
> ⚠ 判据纪律：本批**不许放宽任何判据口径**（day_justified / sleep_guard / verify-run3 一律不动）；只修产品行为与证据真值。

## §1 卡片（commit 列在冻结时填）

| 卡 | 内容 | 责任 | 读数 |
|---|---|---|---|
| task-240b | 腾格成功后立刻尝试买种子（`longrun.py:9879-9887`：重取快照 + `_observe_free_slots` + `_preconditions` + continue；修 catch-22） | dev-coder | 待填（单测/变异/全量） |
| task-241 | 季节感知买种子选品：只用当季可种/在售条目；冬季无在售 ⇒ 不发 buy、`seed_dead_today` 如实记账 | dev-coder | 待填 |
| task-242（待定） | 视 log-analyst 归因结果开：走路预算/死锁逃生（如 last-resort 出货保护材料above reserve）——**涉及纪律边界，须 Lead 裁决 + deputy 对抗 + 用户目标对齐后方可开卡** | dev-coder | 待定 |

## §2 冻结九步（与 0.7.44/45/46/47/49 一致）

1) `tools/_note-0750.txt`；2) `_bump-mod-version.py 0.7.50`；3) `bridge.py` `MOD_VERSION_EXPECTED="0.7.50"` + 注释块；4) `dotnet build -c Release --no-incremental` + C# 自检 + py_compile；5) 按路径 commit；6) `check-release --expect 0.7.50`；7) deploy 前核 `bin\Release` dll == 冻结产物；8) `goto Farm`；9) `preflight --expect 0.7.50 --save-baseline` → 收尾。

## §3 smoke-0750 门禁（machine-runner，1 日）

1) ≥1 个游戏日 `verified=true`；
2) 0 条 `stuck:`；
3) 0 笔禁售卖单（388/390/330/771/382/378/380/384/386/909 走 ShopMenu 口径）；
4) `buy`（种子）意图在真机出现且 `executed_steps`/`reasons` 如实（D2 口径：有动作才 1、无动作 0 + `unknown_evidence`）；
5) 跨日落盘六串配对 + guardian 干净退出；
6) 硬闸口五连：进程 0 / `bridge.json` 删 / 17890 无 LISTENING / 存档四件 SHA256 比对 / SMAPI `modVersion`=0.7.50。

## §4 A9/B9（0.7.50）

- 恢复起点：`logs\ab-backup\A9-start\`（winter 26 四件）→ `preflight --expect 0.7.50 --save-baseline logs\runA9-baseline.json`（冬26 档）。
- A9：`--days 10`（热身 winter26/27/28 逐日单列两形态 + 判定 spring1-5 五天连 VERIFIED）+ guardian + journal `logs\longrun-runA9-0750.jsonl`。
- B9：同起点同参数（argv 只差 `--journal`），起跑前把 A9 lessons **字节拷贝**到 `logs\longrun-runB9-0750-lessons.json`（记两侧 size+SHA256）。
- 判决：`verify-run3 --days 5 --smapi`（两侧）+ `analyze-longrun --window 5` + `compare-runs` L0–L5 + 三检查器；`already`/`attempted_ok` 与 `ok` 双列读。
- 目标1 证据随跑采集：①经济分配（seed buy 钱差分 + upgrade 钱/材料差分）；②zone 清空 + 连续2天复核（`verify-zone-retention.py`）；③铜斧链（铜矿来源实证 + toolOk=false 锚点升级后清除）。

## §5 已知限制

1) 冬季档无种可买 ⇒ 热身三天不可能有种 buying 证据（经济证据集中在 spring1-5）。
2) 背包全保护材料的结构性死锁若仍在（T-6 探针确认中）⇒ task-242 的边界需 Lead 裁决，本版可能不足以解开春季死锁。
3) 铜矿（(O)334×5）来源未证（T-4/T-6 进行中）⇒ 目标1③ 时间盒未定。

## §6 冻结记录（实测）

待冻结时填：冻结提交、dll SHA256、check-release 六项、deploy 读数、baseline 哈希。
