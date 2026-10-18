# 0.7.47 发布计划（A9 门禁批快修：背包升级对话购买默认关闭）

> 日期：2026-10-18。前置：0.7.46 已冻结（737c4a5）并装机；deputy task-31 判定四卡代码面 PASS-WITH-NITS、放行 smoke-0746；task-34 真机探针（4524665）证明 `talk` 原语可用但背包升级对话入口未取证。
> 本版动机：避免 0.7.46 的 task-25 代码在每个游戏日开头 `goto SeedShop → talk Pierre`（会触发过场事件 3102768 / Town 15389722，风险污染 smoke-0746 与 A9 五日连续证据）。功能不删，改默认关闭 + 显式 opt-in。

## §1 卡片

| 卡 | 内容 | commit | 读数 |
|---|---|---|---|
| task-35 | 背包升级对话购买默认关闭（`--enable-backpack-upgrade` / `AGENTFARM_ENABLE_BACKPACK_UPGRADE` 显式开启） | `7657239`（4 files +375/−10） | 定向 16/OK、全量 1388/OK、变异 3/3 被杀；关闭时零 goto/talk/buy 请求，只留只读 skip 留痕 |
| task-34 | 真机只读探针：talk 可用、背包对话未取得 | `4524665`（2 files +255/−23） | 相邻 talk `code=ok/applied=true/distance=1/activeMenu=DialogueBox/activeMenuText="Sigh..."/dialogueIsQuestion=false`；SeedShop 货架 20 条无背包条目 |

## §2 冻结九步（与 0.7.44/45/46 一致）

1) `tools/_note-0747.txt`；2) `_bump-mod-version.py 0.7.47`；3) `bridge.py` `MOD_VERSION_EXPECTED="0.7.47"` + 注释块；4) `dotnet build -c Release --no-incremental` + C# 自检 + py_compile；5) 按路径 commit；6) `check-release --expect 0.7.47`；7) deploy 前核 `bin\Release` dll == 冻结产物；8) `goto Farm`；9) `preflight --expect 0.7.47 --save-baseline` → 收尾。

## §3 smoke-0746 门禁（machine-runner，tag `smoke-0746`）

1) ≥1 个游戏日 `verified=true`；
2) 0 条 `stuck:`（冬26/27 旧形态不得复现）；
3) 0 笔禁售卖单（388/390/330/771/382/378/380/384/386/909）；
4) inventory_blocked 日：四门槛（free_slots==0 / relief_exhausted / pending_executable==0 / pending_malformed==0）全过 ⇒ day_justified=true；缺一即 false；
5) 冬27 形态：pending_executable 归零或改 `resume_budget_exhausted`（且不 VERIFIED）；
6) 跨日落盘六串配对 + guardian 干净退出；backpack 升级若未发生记【无法判定】（默认关闭，opt-in 未开）。

## §4 A9/B9（0.7.47）

同 docs/_release-0.7.46.md §4：先 `arm-start-helper.py restore --arm A9` 四件校验 → 起游戏生效 → 重跑 `preflight --expect 0.7.47 --save-baseline logs\runA9-baseline.json`（冬26 起点）→ guardian 先起 → start-detached `--days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs\longrun-runA9-0747.jsonl`；B9 同起点 + `logs\longrun-runA9-0747-lessons.json` 字节拷贝；判据 `verify-run3 --days 5 --smapi` + `analyze-longrun --window 5` + compare-runs L0–L5 + 三检查器；**already/attempted_ok 与 ok 双列读**。

## §5 已知限制

1) talk 已可用但背包升级入口仍未取证（货架无条目、Pierre 相邻对话仅 "Sigh..."）⇒ 机制【无法判定】，并入 task-14 升级路径评估；默认关闭避免污染。
2) Town 事件 15389722 / SeedShop 3102768 过场会卡世界（唯一恢复 load_save(force)），对农务长跑无影响但未来进城动作需事件恢复能力（backlog）。
3) 0.7.46 → 0.7.47 无 Mod 代码变更（dll 逐字节相同 293888B `C9B3BD6C…`）。

## §6 冻结记录（实测）

- 冻结提交 `a03a564`（3 files：bridge.py +18/−1、manifest.json、tools/_note-0747.txt）；前置 `7657239`（task-35）。
- build `--no-incremental` 0 警 0 错；dll 293888B `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A`（== 0.7.46，无 Mod 变更）；C# 自检 OK 97 断言。
- `check-release --expect 0.7.47` 六项全绿：版本 0.7.47/0.7.47；dll 21:42:02 不比源码旧（Skills.cs 20:26:30）；py_compile 35 文件；全量 **Ran 1388 / OK**；工作树干净。
- deploy 0.7.46→0.7.47（manifest 76849B），桥自报 modVersion=0.7.47、读档 `Wahaha_450799035`；`goto Farm` OK（landing [64,15] 7643ms，冬28 06:00 钱3288 体力270）；`preflight --expect 0.7.47 --save-baseline` ✅ 可以起跑，baseline 760B `143DBBA215AA4E0045BDF2F2BF8A791A196D059F2FF335D481F8402E6E1B4AEA`（**冬28 档**；A9 前 restore 冬26 后必须重写）。
- `stop-game --wait 45` rc=0（原 pids=[4780]）⇒ 进程 0 / bridge.json 无（root+AppData）/ 17890 无 LISTENING；装机 dll 293888B `C9B3BD6C…`、repo manifest 76849B `9B7C30F6BEA7F2BDEC8615106750F7E5F59480D62D4A4C497AD999317ADBB067`。
- 冻结后待办：docs 记录提交（本文 + 开发日志条目 091）→ task-30 smoke-0746 → A9/B9。
