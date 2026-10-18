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

## §7 smoke-0746 结果与裁决（2026-10-18 21:44–21:50；machine-runner `59eb3f4`，`docs/_smoke-0746.md` 116 行）

- **结论：六条门禁 5 PASS + 门禁②【无法判定】⇒「六条全满足」不成立，A9 不放行。**
  - ① ≥1 天 verified ⇒ **PASS**（finish `code=0`、winter28 `verified=true`）。
  - ② 0.7.45 两 FAIL 形态转 PASS ⇒ **【无法判定】**：本跑 `inventory_blocked=0`/`resume_exhausted=0`/`stuck:`=0/「守卫仍说」=0 ⇒ 两形态未触发（本档 winter28、卡面禁 restore A9-start）。本日背包确实满（free_slots 0/0/0 + relief_exhausted=true）但仍有活（139 格出手），走「满包留痕 + 继续干活 + 体力诚实收工」，不是冬26 的「无活可做 ⇒ inventory_blocked」路径。
  - ③ 0 条 `stuck:` ⇒ **PASS**。④ 建材/锭类零卖单 ⇒ **PASS（字面）**：`sell` 0 条、`slot_relief[].sold=[]`、钱 3288 未变；限制=卖材通道未触发，白名单修复未被实际验证。⑤ 背包留痕有界 ⇒ **PASS**（`buy{status:skipped,code:disabled}` 1 条、`backpack_upgrade_skip="disabled"`、`loot_lost_steps=0≤5`）。⑥ 六串 1/1/1/1/1/1 + guardian 21:50:14 判据 → stop rc=0（原 pids=[16676]）→ 进程 0 / bridge.json 无 / 17890 无 LISTENING ⇒ **PASS**。
- **逐日读数**（只有 1 个 day_end，`--days 1` 首日达标即停）：winter28 06:30→13:10、`ended_by=sleep`（`stamina:体力 11.6002 < 12`）、`ok/skip/fail=139/2/0`、checks **10/10 true**（含 day_justified）、pending 七口径 `9/9/0/0/9/0/0`（不变式成立）、`plot_pending=9`（till_area）、`free_slots 0/0/0`、`loot_lost_steps=0`、`refused=2`（[41,12][41,13] tool_ineffective，bound 28/exempt 0）、`unreachable=0`、`stages_seen=[till_area]`、finish `code=0 / verified_streak=1 / actions=148 / minutes=5.16 / unmet_days=[] / stuck_flushes=0`。
- **八步**：3 PASS、4 PASS（brain PID 12196）、5【无法判定】（整跑只做 till_area，无 clear_area ok 格）、6 PASS（六串全配对，NewDay 1403 → after 1413）、**7 FAIL**、8【无法判定】（8.1 PASS；8.2② trees PASS 依据来自旧会话观测污染，本跑 winter28 仅 +2 ⇒ 不可引为本跑证据）。
- **步 7 FAIL（字段级缺口）**：`slot_relief` 共 3 条，index 2（t=3.31、`trigger=clear_gate`、task-28 新增压力通道）**缺 task-237 字段 `reached`**（另有 `demand/target_free`）⇒ `analyze_rc=1`、`verify_rc=1`。
- **收尾/指纹**：SMAPI 窗口 `logs/smoke-0746-smapi-window.txt` **179,772B / 1,429 行 / `E84EB6C944E1058E8D824F23BAA008BBEFB167B900E0EBB534C5789F4FDB9C5E`**；journal 146,399B `B08F351BA0C998C1B8543CB9058A0C43012FE288D1638FCFE779E2F76E4F6728`；跑后存档四件 main 3,571,471B `2B1BCC1B…F669`、SaveGameInfo 32,618B `2B8140D9…8334`、_old=跑前 main `6DE8419B…B594`、info_old=跑前 info `B5B51971…10A1`；A9-start 未动（MANIFEST 1,222B `5479354B…988A3D`）；装机/`bin\Release` 全程冻结 `C9B3BD6C…` / manifest `9B7C30F6…`；journal 哈希见 `docs/_smoke-0746.md` §7。
- **Lead 裁决**：
  1. **门禁② 是卡片设计失误**（卡面既禁 restore A9-start、又在 winter28 档要求冬26/27 形态）——按「缺失≠通过」不能记 PASS；改由 **A9 热身三天（winter26/27/28）逐日核这两形态**，A9 判决必须单列该两条的读数。`docs/_release-0.7.47.md §4` 的 A9 判据据此加一条。
  2. **步 7 FAIL 是真实字段缺口**（非行为缺陷）：0.7.46 task-28 的 `clear_gate` 分支未写 `reached`，而 `analyze-longrun`/`verify-run3` 按 task-237 要求该字段 ⇒ A9 判决工具会因它 rc=1。**必须在 A9 前修**：0.7.48 快修卡（task-38）。
  3. A9 **暂不启动**：先 0.7.48（字段补齐 + 复用字段登记）→ 冻结 → 直接 A9（不重跑 smoke：0.7.48 只加只读字段，重复起游戏收益低；A9 前三天热身即 live 覆盖门禁②形态）。
- **已知限制（照实）**：本跑只有 1 天读数、卖材通道未触发、步 5/8 无有效读数、trees 判据受旧观测污染、背包升级【无法判定】、`--no-crops` 使春季农务腿仍未覆盖。
