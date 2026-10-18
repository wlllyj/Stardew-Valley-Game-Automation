# 0.7.48 正式对抗验收（deputy-lead）

## 1. 范围与冻结树
- 冻结树基线：`e2b69d9`（0.7.48 deploy），本会话在此基础上追加 P0-1..P0-7 代码改动（commit `0f72f3c`..`bbb6a89`）。
- 本验收针对代码树（brain/mod/tests/tools），不含真机长跑（A9/B9 由 machine-runner 负责）。

## 2. Provenance
- manifest Version = 0.7.48；brain MOD_VERSION_EXPECTED = 0.7.48（check-release 通过）。
- dll mtime 23:39:02 vs Skills.cs 20:26:30（dll 新于源，check-release 通过）。
- 全量 py_compile -W error::SyntaxWarning：35 文件 0 警告（check-release 通过）。

## 3. 变异/单测
- 全量单测：`Ran 1392 tests`，FAILED 1 = `test_csharp_rules_self_test_passes`（已知假红：subprocess.run 未指定 encoding → cp1252 解码 UTF-8 中文；AGENTS.md §2 已登记；C# 自检原文 OK 97 断言 rc=0）。非本会话引入。
- analyze-longrun：334 tests OK。
- test_fields：20 tests OK。
- test_verify_run3：80 tests OK。

## 4. P0 交付清单（本会话）
- P0-1 zone-clump-blockers：`fields.ZONE_BLOCKER_KINDS` = BLOCKER_KINDS ∪ {stump,log,boulder,rockPile,greenRain}；zones_from_observe/plot_in_zone 改用；farmwork.CLUMP_KINDS 交叉引用。commit `0f72f3c`。
- P0-2 zone-level-clear：`fields.zone_blockers_total(zone, obs)`，tilesTruncated → None（fail-closed）。commit `3a22b97`。
- P0-3 zone-retention：`tools/verify-zone-retention.py` 跨日 diff，exit 0/1，tilesTruncated → 【无法判定】。commit `5434acd`。
- P0-4 no-work-dualtrack：verify-run3.py 新增 `_day_non_empty` + empty_days/non_empty_day_count（仅呈现，rc 不变）。commit `e34e5cc`。
- P0-5 economic-buy-seed：`planner.TASK_KINDS` 加 `buy`；longrun._execute 分支调用 `_preconditions`（游戏入口 buy）+ journal。commit `bbb6a89`。
- P0-6 economic-upgrade-tool：`planner.TASK_KINDS` 加 `upgrade_tool`；longrun._execute 分支调用 worker.upgrade_tool("axe")（游戏入口 tryToPurchaseItem）+ journal。commit `bbb6a89`。
- P0-7 planner-wire：TASK_KINDS 含 buy/upgrade_tool；prompt __KINDS__ 自动渲染。commit `bbb6a89`。

## 5. 已知限制
- `day_end.zone_clear[zone]` 字段未接入 longrun DayReport（fields 层已具备 zone_blockers_total；verify-zone-retention 独立观测工具已交付；longrun 接线延后以避免破坏 1392 测试）。
- `state.zones_cleared_last` 未接入 longrun state（verify-zone-retention 工具承担跨日对比）。
- 经济买种/升级的 LLM 策略触发依赖 planner 输出；真机 A9/B9 长跑尚未执行，经济闭环的"钱实际分配"需真机观测差分证实。
- 铜斧升级材料链（铜矿/煤/熔炉）在 winter26 结构性不可达；升级路径评估按 task-14 在 A9/B9 后进行。

## 6. 结论
- 代码树：py_compile 0 警告，1391/1392 通过（1 为已知假红），provenance 通过。
- P0-1..P0-7 全部 claimed+completed。
- 剩余：A9/B9 长跑（machine-runner）、task-14 升级路径评估、analyzer 收口（log-analyst，P0-4 已提供双轨字段）。
- 判定：PASS（代码层），真机验收待 A9/B9。
