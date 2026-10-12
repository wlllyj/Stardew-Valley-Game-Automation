# task-22 独立复核（deputy-lead）

判定：**PASS-WITH-NITS** —— 任务书条款①–⑥ 全部满足；`tools\verify-run3.py` 的 12 本账本我独立复跑与 Lead 自测**完全一致**；新增 4 条 nit（N4-1 是 task-22 未覆盖的**同类**瞬时状态，建议单独立卡，不阻塞本卡完成）。

验收基线：HEAD `99d3eaf`（当时工作树 clean）。复核过程中 task-11 已开始改 `longrun.py` / `mod\AgentFarm.Bridge\{Contracts,UiRead,WorldSnapshot}.cs` / `tests\test_longrun.py`，故本报告的指纹只对 `99d3eaf` 的内容成立。

## 1. 冻结指纹与轻量冒烟（我独立跑）

| 文件 | SHA256(前12) | LastWriteTime |
|---|---|---|
| `brain/agentfarm/farmwork.py` | `E087DD1663EC` | 2026-10-13 00:48:28 |
| `brain/agentfarm/longrun.py` | `DFE13E247892` | 00:44:13 |
| `mod/AgentFarm.Bridge/UseToolSkill.cs` | `CB7D285CC18D` | 00:44:28 |
| `tests/test_farmwork.py` | `47BAA759C48B` | 00:47:54 |
| `tests/test_longrun.py` | `35F81E0184E3` | 00:46:35 |

跑测试前后重新取哈希：五个文件**逐字未变**（验证期间没人动它们）。

- `py_compile`（`brain/agentfarm` + `tests` 全量）→ exit 0。
- `PYTHONUTF8=1 PYTHONPATH=<repo>\brain python -m unittest discover -s tests` → **`Ran 249 tests in 2.294s` / `OK`**（复跑一次同结论；与 dev-coder 自述 249 一致）。
- `dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` → **0 个警告 / 0 个错误**（exit 0，1.38s）。
- 版本未被擅自 bump：`mod/AgentFarm.Bridge/manifest.json:4 "Version": "0.7.21"`、`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.21"`。

## 2. 任务书逐条打勾

**① 三类常量互斥 + 覆盖（farmwork.py）**
`TILE_INERT_STATUSES = ("tool_ineffective", "precondition_failed")` :74；`ENV_BLOCK_STATUSES = ("no_save", "ui_modal", "world_fading")` :80；`INCONCLUSIVE_STATUSES = frozenset({"timeout", "error"})` :90。互斥与覆盖由 `tests/test_farmwork.py:474-503` 钉住（`mod_codes` 7 个码并集覆盖 + 三类精确集合断言）。

**② `_classify_status` 语义（Lead m01763 裁定 A）**
`farmwork.py:383-407`：ENV→`(True, False)`；INCONCLUSIVE→`(False, True)`；**其余一切**（`TILE_INERT`、`ok`、`""`、未枚举码）→`(False, False)`=「Mod 真回应了」。空串语义论证见 :422-423。单测逐支断言：`("ok")==(False,False)`、`("")==(False,False)`、`("brand_new_code")==(False,False)`、`("timeout")==(False,True)`、`("error")==(False,True)`、`("no_save")==(True,False)`（`tests/test_farmwork.py:498-503`）。
辅助：`_mark_status` :410-416（就地累加）、`_exc_status` :419-425（**没带 status 的异常按 `error` 算** ⇒ inconclusive，不会被当成"真实回应"）。

**③ 出口覆盖 + `sow` 继承**
`_mark_status`/`_exc_status` 调用点：`move_to` :655、`ensure_location` :676、`clear` :788-813（`TILE_INERT`→conclusive :788-790；env→`r.env_block=True` :803；inconclusive→`r.inconclusive=True` :813）、`till` :878/:889、`plant` :929/:944、`water` :1009/:1021、`harvest` :1056/:1066、`refill_can` :1104/:1114、`sleep` :1193。
`sow` 继承底层标记：`farmwork.py:973-974` `pr.env_block = pr.env_block or wr.env_block` / `pr.inconclusive = pr.inconclusive or wr.inconclusive`。
`clear()` 的"封格"只在**挥满上限或 Mod 自己回工具全无效**时发生（:820-826），env/inconclusive 都走提前 return（:800-818）⇒ 两者都不会被写成 `proven_inert`。

**④ longrun 记账**
`_mark_blocked`（`longrun.py:863-899`）：准入仍是 `s.failed or s.proven_inert` + `action in ("till","clear","sow")`，**:887-889 跳过 `s.env_block or s.inconclusive`**（注释 :876-879 写明两类失败如实卡在 `leftover` ⇒ 当天 `met=False`）。
`_count_attempts`（:901-923）：**:920-921 只跳过 `env_block`**，`inconclusive` 照计配额（注释 :914-915 给出理由：持续无结论应被限流成 `capped` 而不是无限磨到天亮）。
stage 记录 :1028-1034 带 `env_block` / `inconclusive` 计数；journal `env_fail` :1037-1041、`inconclusive_fail` :1042-1046（含 `tiles` 与 `statuses`）；`day_text()` 摘要 :1065-1068。
task-9 语义未回归：`met = bool(all_steps) and not leftover` :1021 未动，env/inconclusive 失败仍卡在 `leftover` ⇒ 当天判不了 VERIFIED。

**⑤ 集成层用例（非空断言，逐条读过）**
`tests/test_longrun.py:1285-1392`，4 条：
- `test_clear_env_block_retries_same_day_and_never_seals`（:1303）：断言 blocked 不含该格、`tile_attempts` 无该键、有 `env_fail` 无 `blocked`，并**第二轮同一天真清掉**（:1323-1326）。
- `test_inconclusive_spends_quota_and_caps_without_sealing`（:1328）：配额 1→2、`MAX_TILE_ATTEMPTS` 后 `capped` + `terminal="needs_review"`、仍不封格、有 `inconclusive_fail`。
- `test_sow_env_block_never_seals_or_spends_quota`（:1354）：`ui_modal` 经 `sow` 继承。
- `test_water_env_block_never_spends_quota`（:1373）：`world_fading` 在**无动作过滤**的 `_count_attempts` 上不吃配额。
基建：`FakeWorld.fail_status`/`take_fail_status`、`FakeClient.use_tool` 按注入抛 `BridgeError(status=…)`。都是真断言，不是空跑。

**⑥ N2 / D1（两条 nit 的修复）**
N2：`farmwork.py:779` `第{i}次请求`（不再是"刀"），四个出口的 `after` 都带 `requests`/`statuses`（:784、:805、:815、:825）。
D1：`UseToolSkill.cs:536-540` `KindNow()` 只留一行；长 `<summary>`（:554-562）挂在 `Done()` :563 上。task-7 ② 同时复核：`if (tf is StardewValley.TerrainFeatures.Grass) return false;` :591 在 `return true` :592 之前。

**口径一致性（四处）**：`farmwork.py` 常量+分类 ⇄ `longrun.py` 记账 ⇄ `tests` 假桥注入 ⇄ `tools\verify-run3.py:194-218` —— 无冲突。工具对键名两种拼法都容错（:194-195 `env_block_count` else `env_block`），与 `longrun.py:1032` 实际写出的 `env_block` 对得上。

**越界检查**：task-22 writeScopes 之外的文件（`brain/agentfarm/__main__.py`、`bridge.py`、`tools/verify-run3.py`、`tests/test_bridge_client.py`）改动分别属 task-26 / task-13 / Lead / task-13；dev-coder 未越界；`manifest.json` 与 `MOD_VERSION_EXPECTED` 未碰。

## 3. 工具侧独立复跑（Lead `bfb8649`，12+ 本）

命令：`python tools\verify-run3.py --journal <账本>`（我独立跑，不看 Lead 结论）。

| 账本 | exit | 结论 |
|---|---|---|
| `scratch\journal-green.jsonl` | 0 | VERIFIED |
| `scratch\review-neg-G-env-info-item.jsonl` | 0 | VERIFIED + 3 条 env 信息项 |
| `scratch\review-neg-I-env-explained.jsonl` | **0** | VERIFIED + 逐日 1 条差额信息项 |
| `neg-A/B/C/D/E/F/H` | 1 | needs_review |
| `scratch\review-neg-J-env-understated.jsonl` | **1** | 「解释不完（账目不可信）」 |
| `logs\longrun-3day-llm-run2.jsonl` | 1 | needs_review |

- neg-I 的信息项原文：`[spring 10] failed_steps=0 < stages 求和 3；差额 3 = 环境挡路 3 + 无结论 0（task-15 ④ 口径，不计为当天硬失败）` —— 与 Lead 自测一致。
- neg-J 的问题原文：`自述 failed_steps=0 比 day_end.stages 求和 3 少 3，而环境挡路 1 + 无结论 0 解释不完（账目不可信）`；neg-B 同形但「环境挡路 0」。
- **I/J 已并入我的生成器** `scratch\_review_neg_gen.py`（新 mode `env_explained` / `env_understated`，见文件 `day_block()` 尾部与 `main()` 列表）。重新生成后我版 I/J 的判定与文案与 Lead 版一致（字节不同，字段更全）。
- ⚠️ 跑矩阵时别把 Lead 的 3 本探针账本当绿账本：`scratch\_ledger_green.jsonl` / `_ledger_fallback.jsonl` / `_ledger_leftover_verified.jsonl` 都 exit 1，原因是**只有 1 天**（`尾部连续 VERIFIED 天数 0 / 要求 3`），不是缺陷。

## 4. 新增发现（不阻塞 task-22 完成）

**N4-1（中）`busy` / `stale` 落进兜底桶 ⇒ 瞬时"请求根本没执行"被当成"这一刀白挥了"。**
- `busy`：`MainThreadDispatcher.cs:160-168`，队列积压时对**任意 skill**（含 `use_tool`）快速拒绝（`Ok=false, Status="busy"`，主线程压根没跑）；`stale`：`BridgeHost.cs:538-553`，时效拒绝，也在 `runner()` **之前**返回。
- 两者都不在 ENV / INCONCLUSIVE ⇒ `_classify_status` 归 `(False, False)`=「Mod 真回应了」。后果：`clear()` 里 `swung = True`（`farmwork.py:798`），4 次即 `r.code="skipped"; r.proven_inert=True`（:820-826，理由文案还写"连挥 4 刀"——**实际一刀都没挥**）；`till` 更是一击致命：一次 `busy` ⇒ `r.code="failed"`（:887）⇒ `_mark_blocked` 封格（`longrun.py:885-896`）⇒ 当天 `leftover>0` ⇒ needs_review，白丢一天。
- 可达性：`stale` 只可能来自 `move_to`/`move_to_location`（脑只在 `bridge.py:529-541`、`:583-602`、`:610-635`、`__main__.py:357`、`:427` 传 `based_on_seq`），`use_tool` 不带该参数 ⇒ **现网真正可达的是 `busy`**。触发时序很现实：客户端超时（run2 就有两次 180s sleep 超时）之后 Mod 仍在跑那个长技能，随后的 `use_tool` 会被 `busy` 快速拒绝。
- 建议（请 Lead 定夺）：`busy` → 按 **ENV** 处理（零成本拒绝、与地块无关 ⇒ 不封格、不占配额）；`stale` → 归 **INCONCLUSIVE**（占配额、不封格，并暴露脑侧决策过期）。若要修，建议并入 task-22 的后续小改或单开卡，改 `farmwork.py` 常量/分类 + 一组用例（clear 遇 `busy` 不封格、till 遇 `busy` 不封格且不吃配额）。

**N4-2（低，文档）** `farmwork.py:88` 声称三类"并集覆盖 **Mod 全部** status"，但单测只钉 `use_tool` 回执的 7 个码（`tests/test_farmwork.py:487-492`）；`sleep_no_question`（Mod 也会返回，见 `farmwork.py:94`）不在三类里、走兜底桶。行为正确（sleep 路径不封格），但建议把措辞收窄成"覆盖 `use_tool` 回执的 status"，或在测试注释里明说 sleep 码走兜底。

**N4-3（低）** verify-run3 差额容错的"解释项"与 `failed_steps` **同源**（都出自脑侧自报）⇒ 理论上可以"自洽地洗账"（一边少报 `failed_steps`、一边把 `env_block` 计数配平）。目前拦得住它的仍是 `leftover` / `no_unmet_stages` 交叉核对。可选加固：把 `env_fail`/`inconclusive_fail` **事件**里的 `tiles`/`statuses` 与 stage 计数交叉核对（我可造负例 K，等 Lead 同意）。

**N4-4（低，task-26 顺带）** `await_game_exit`（`__main__.py:515-563`）在 pid 未知时已如实 `return 1`（:557-560，文案"无法强杀"），但**强杀失败也 `return 0`**：`:561-563` 忽略 `kill()` 的 bool 返回值（`kill: Callable[[int], bool] = _taskkill`，`:499-503` 会返回 False）。这与"不谎报成功"是同一类残余，建议 `ok = kill(int(pid))`，更稳的是杀完再 `pid_alive(pid) is False` 复检。另外 `README.md:53-55` 与 CLI help（`__main__.py:791-792`）都只写"让游戏自己退出/等多少秒强杀"，**没写退出码语义**，建议补一句"1 = 等满仍未能确认退出（含 `bridge.json` 缺 pid、强杀失败）"。

## 5. 待办

- task-11（rev4 职业安全硬规则）验收时专门复核四态：`professionsToChoose` 非空**绝不 dismiss**、字段缺失按未知处理也不 dismiss、两种都 journal 留痕且当天不判 VERIFIED、普通升级弹窗照旧自动关 + `SaveGameMenu` 只等不关；并加"未知不许拿不确定性赌不可逆操作"的负例。
- 整链冻结后跑一次完整验收（含 `dotnet build --no-incremental`、12 本矩阵、task-15 ④ 落地后的 `failed_steps` 两侧同改校验）。
