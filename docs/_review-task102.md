# task-103 独立对抗验收：task-102（0.7.28 背包空格死锁 + 0 动作不许睡觉）

- 验收人：deputy-lead（独立复核，只看代码 + 自跑输出，不看作者结论）
- 对象：`9b09735`（dev-coder，4 文件 +678/−15：`brain/agentfarm/farmwork.py` +87、`brain/agentfarm/longrun.py` +267、`tests/test_farmwork.py` +67、`tests/test_longrun.py` +272）
- 判定：**PASS-WITH-NITS**（无必修项；4 条 NIT 均不影响 run9 的账本可信度）
- 证据脚本：`scratch/_t103_adv.py`（真 `FarmWorker` + 真 `LongRun` + 进程内 `tools/verify-run3.py`）
- 原始读数：`scratch/_t103_adv_out.txt`（40 条断言 **PASS 40 / FAIL 0**）；每例的真账本落在 `scratch/_t103_j/case*.jsonl`（工具判决就是在这些**真账本**上跑出来的）

## 1. 一句话结论

卡面四个重点全部成立：① 腾格卖出**结构性**只碰 `SURPLUS_MATERIAL_IDS` 白名单材料，种子/工具/武器一件不碰，且 **K=10 不破**（真代码端到端 + 单元级各一）；② `no_space` 有界性跨天有效（每天 buy 尝试 `[1,2,1]`、两天共 3 次，对比 run8 的 13+11）；③ 睡前清模态失败**fail-closed**（异常与 `ok=False` 两态都判 `sleep_failed`、游戏日不动）；④「0 农场动作 **且有活**」既不推进游戏日也不达标（`slept_without_work` + `verified=false` + 工具 `needs_review`），且腾出格子后当天**真的**买到了种子。NIT 全部是 docstring/最小损失/多余一次请求级别的问题。

## 2. 范围与读数（我亲跑）

| 项 | 结果 |
|---|---|
| `git show --stat 9b09735` | 恰 **4 文件** +678/−15，与卡面一致 |
| 越界扫描（`^mod/\|^tools/\|manifest.json\|bridge.py\|^logs/\|00-开发日志`） | **零命中** |
| SHA256 前 16（作者自报逐字核对） | `farmwork.py 3D2A9E5AD4B84A7A`、`longrun.py BBB6EAFB4F1A2449`、`test_farmwork.py FA074DF53FAA251B`、`test_longrun.py 145314694C32069F` **全部一致** |
| `tools/verify-run3.py` | `7356D4CB…`（未变；本卡未碰工具） |
| `py_compile -W error::SyntaxWarning`（4 文件） | exit 0 |
| `python -m unittest tests.test_longrun tests.test_farmwork` | **Ran 277 / OK**（= 作者自报） |
| 全量 `unittest discover -s tests` | **Ran 607 / FAILED (failures=1)**，唯一红 = `test_analyze_longrun.TestEventMappingDrift.test_event_buckets_cover_every_brain_journal_name`（新事件 `slept_without_work`/`buy_no_space` 未进 `EVENT_BUCKETS` ⇒ 已派 task-106 给 log-analyst；**如实记录，不算 task-102 的缺陷**） |

注：pwsh 会把 unittest 的 stderr 报成 `[exit code: 1]`，是已知噪声；上面两个 OK 均为 stdout 原文。

## 3. 逐条对卡

### B3（卡面 ③：背包 0 空格 + 钱 188g + 无种子 + 石头 200 一叠 + 农场有干作物）

真代码一天（`LiveFarmWorld`，farm 块与世界一致），日志原文：

- `journal sell ×1: [{ok:True, code:'ok', why:'need_slot', slot:6, qid:'(O)390', stack:200, below_keep:True}]`
- `journal surplus_sell ×1: [{ok:True, why:'need_slot', sold:200, below_keep:True}]`
- `journal buy ×2: [{ok:False, code:'failed', attempt:1}, {ok:True, code:'ok', attempt:2}]`
- 钱 **188 → 88**、种子进背包（10 包 ×10g），石头真的进了出货箱

⇒ 卡面要求的"为腾格整叠卖出（`why=need_slot`）⇒ 当天不再重试（≤3）⇒ 买到**当季在售**种子"**全部成立**，而且是**真 `FarmWorker` 的端到端**证据（作者用例 `:4992` 用的是假 worker，只断言 `buy_requests==1`，没证明腾出的格子真让买成功 —— 这一块由本实验补上）。

### B4（卡面 ④：钱够但买不到 + 干作物够不着）

- `ended_by='slept_without_work'`、`day_after=None`（**游戏日根本没被推进**）、`ok_steps=0`、`verified=False`
- `journal slept_without_work{why:'gave_up_dry:…1 格在玩家窗口之外…已试 2 次都够不着…这不是「没活可做」…'}`
- 工具（真账本 10 行）：`ok=False / needs_review`，problems = `ended_by=slept_without_work（不是我们主动睡过去的）`、`checks.watered_outdoor=false（睡前还有没浇的作物）`、`day_end verified=false`
- 直接调 `_do_sleep`（`farm_actions_today=0` 且守卫说有活）⇒ `by='slept_without_work'`、`w.day` 6→6、journal 落盘

⇒ 「0 动作 + 有活」不许睡觉、不许算达标、不许推进游戏日，四条证据齐。

### C 段（朝修法本身进攻，真代码）

| 攻击 | 结果 | 证据 |
|---|---|---|
| ⑤ 谎报 buy 成功（回执 ok、钱/背包没变） | **PASS** | 被 `have_after>have_before and money_after<money_before` 判 `failed`、只试 1 次、钱恒 188 |
| ⑥ 腾格卖出碰种子/工具/武器 | **PASS（结构性排除）** | 只有工具/作物/空叠 ⇒ `slots=[]` + skip 原文点名白名单；白名单实文 `['92','330','378','380','382','384','386','388','390','766','771','909']`；`whitelist=['(O)390']` 无工具 |
| ⑦ 破 K=10 | **PASS（不破）** | 同 id 240 叠卖 200 ⇒ `left=40 ≥ 10`、`keptBelowKeep=False`；唯一一大叠整卖 ⇒ `belowKeep=True` 且 journal 如实记 `below_keep` |
| ⑧ 连续两天 `no_space` 有界性 | **PASS** | 每天 buy 尝试 `[1,2,1]`（≤3/天）、两天共 3 次；`buy_no_space` journal ×2；卖不出去时如实记 `sell failed`（不静默） |
| ⑨ 睡前清模态失败 fail-closed | **PASS** | dismiss 抛异常 **与** 回 `ok=False` 两态 ⇒ `sleep_failed`、`w.day` 6→6、`sleep` journal `ok=False`，异常态另有 `modal_dismiss_failed` |
| ⑩ 两条门闸同时成立（钱 30 < 5×10 但 ≥ 10 + 0 空格 + 有耕地） | **PASS（有界、无死循环）** | 卖货尝试 2 次 ≤3、`buy` 1 次、一天跑完落 `day_end`、工具 VERIFIED（真没活） |

## 4. 工具侧判决（真账本）

| 例子 | 真账本 | 工具判决 |
|---|---|---|
| B3 | `case01.jsonl` 69 行 | `needs_review`（`ended_by=stuck` + `no_hard_failures=false` + 18 格硬失败；**均来自我的夹具**：非耕地 till 失败，与 task-102 无关） |
| B4 | `case02.jsonl` 10 行 | `needs_review`（`slept_without_work` + `watered_outdoor=false` + `verified=false`）✅ 期望的 fail-closed |
| C5 | `case03.jsonl` 12 行 | `VERIFIED`（谎报的 buy 被判失败后，那天确实只剩"没活"⇒ 合法 `no_work`；`弱日：1 步` info） |
| C8 | `case05.jsonl` 47 行 | `needs_review`（两天都 `stuck`、`verified=false`；`stuck 日翻篇 2 天 / journal stuck_flush ×2`） |
| C10 | `case06.jsonl` 16 行 | `VERIFIED`（0 阶段 + 有"无活可做"证据 ⇒ 既有 0 步豁免接受） |

附带核实：上一版探针喂的是**日级合成账本**（无 journal 行），工具里所有"journal 自算"类计数按构造为 0，`stuck_flush ×0` 就是这样来的；改成喂**真账本**后 `stuck_flush ×1/×2` 与 journal 逐字对上 ⇒ **不是工具的计数 bug**。

## 5. NIT 表（均不阻塞）

| # | 现象 | 行号 | 反例/命令 | 建议 |
|---|---|---|---|---|
| NIT-1 | docstring 说腾格路径"真盈余里挑最小的一叠"，实测挑**最大**的一叠 | `farmwork.py:1045-1056`（`surplus` 排序取 `[0]`），但该分支在"存在真盈余叠"时**不可达**（`picked` 循环 `:1006-1015` 无条件先跑）⇒ `:1048-1049` 实质死代码 | `scratch/_t103_adv.py` C7：Stone 40@slot4 + 200@slot6 ⇒ 计划 `slots=[6]`（docstring 期望 `[4]`） | 二选一：改 docstring，或把 `need_slot` 路径挪到 money 循环之前（真按"最小损失"腾格） |
| NIT-2 | docstring 说 `need_slot` 只卖一叠，实测**每个 id 一叠**（只缺 1 格却计划卖 3 叠） | 同上 `:1006-1015` | C7 三 id 各两叠 ⇒ `slots=[1,4,7]`；K 仍未破（各叠 `left ≥ 10`） | 同 NIT-1（如实性/最小损失问题，不是洗白通道） |
| NIT-3 | 卖完腾格后用**同一个过时 obs** 继续 `_sell_surplus_for_seeds` ⇒ 对已腾空的槽位再发一次 sell | `longrun.py:2040-2047`（`obs` 未在 `_sell_surplus_for_slot` 后刷新） | C10：`sell` 槽位 `[8,8]`，第二条 `code='empty_slot', qid=''`（有界，仅一条噪声 journal） | 卖成功后 `obs = self._snap()` 再往下走 |
| NIT-4 | 卡面 ④ 字面"不许推进游戏日"在 `_stuck_flush` 这条**设计内例外**上不成立：0 动作 + 有活仍会翻页（`MAX_STUCK_FLUSH=2`） | `longrun.py:2219-2276` 显式 `require_work=False`（task-73 有界翻篇） | B3/`case01`、C8/`case05`：`day_after` 有值、`ended_by=stuck`、`verified=false`、工具 `needs_review` | 不需改；**口径按"`day_after=true` ∧ `ok_steps==0` ∧ `verified=true` 三者绝不同时"记**（本实验未出现） |
| NIT-5 | 0 动作 + 真没活 ⇒ 工具用既有"0 步豁免"接受（C10 `VERIFIED`） | `tools/verify-run3.py`（task-52/task-19 既有口径，本卡未碰） | `case06.jsonl` | 留档；这是任务书 ⑥"真空农场允许 no_work 睡"的既有设计，与 task-102 无关 |

## 6. 复跑命令

```powershell
$py="C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
$env:PYTHONPATH="D:\Deepseek Harness Workspace\星露谷游戏自动化\brain;D:\Deepseek Harness Workspace\星露谷游戏自动化"
& $py "scratch\_t103_adv.py" 2>&1 | Out-File "scratch\_t103_adv_out.txt" -Encoding utf8
```

## 7. 结论

**PASS-WITH-NITS**：task-102 的四条修法（`no_space` 独立结果码 + 腾格卖出 + buy 每天上限 + 0 动作不许睡）在真代码对抗下**全部成立**，`no_space` 死锁与"0 动作白拿一天"两个 run8 病灶都被堵住；4 条 NIT 均为 docstring 与实现不一致、多余一次请求、或既有设计边界，建议归入 0.7.28 的顺手项（或下一卡），**不影响 0.7.28 上真机跑 run9**。
