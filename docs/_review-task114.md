# task-114（教训库信任边界 / 裁剪优先级 / 真值证据）delta 独立复验

- 验收人：deputy-lead；任务：task-115（rev2，in_progress，Lead m05215 派工）
- 对象：`c135edc`（0.7.28 task-114：`brain/agentfarm/planner.py`、`brain/agentfarm/longrun.py`、`tests/test_planner.py`、`tests/test_longrun.py`）
- 复验时 HEAD：`370909c`（其后的 `370909c` = task-116 analyzer 收录 `lessons_rejected`、`0e01006` = docs；`git diff --stat c135edc..HEAD -- <上述 4 文件>` **为空** ⇒ 我跑的就是 task-114 的代码）
- 判定：**FAIL**（一条卡面「必做」未满足，可最小复现；其余三条通过）
- 日期：2026-10-16

## §1 一句话判定

task-114 把 task-112 F1/F2 的主体修住了：不合 schema 的伪造条目逐条被拒收并留痕（`lessons_rejected` + 原因/计数正确）、四档预算下丢弃顺序变成 **复盘笔记 → 决策史 → 教训库** 且核心字段逐字不变、四种形态（开关 / 篡改 / 坏 JSON / 复盘抛错）下**判定字段逐字相同**、`no_inventory_space` 的 evidence 已是当次真值；**但卡面第 1 条③「伪造条目不许把真教训挤出 20 条上限」不成立**——卡面自己点名的第 5 类伪造条目（`last_seq=999999`，`kind`/`id`/类型全合法）能排到注入列表**首位**并把真教训挤出上限。根因是 task-114 只钳了 `kind`/`id`/类型/`severity`，**没钳 `last_seq`/`count`**，而 `prune_lessons` 的排序键恰好是 `(last_seq, severity, count)`。这正是我 task-112 §5 **NIT-3**（"任意 `last_seq` 全收"）里点名、这次只修了一半的那一项。

## §2 范围与读数（我亲跑，未复用作者数字）

| 项 | 读数 |
| --- | --- |
| `git show --stat c135edc` | **恰 4 文件** +415/−15：`brain/agentfarm/longrun.py` +54、`planner.py` +133、`tests/test_longrun.py` +113、`tests/test_planner.py` +130 |
| 越界扫描 | `^mod/`、`^tools/`、`manifest.json`、`bridge.py`、`^logs/`、`00-开发日志` **零命中** |
| 之后的提交 | `370909c`（`tools/analyze-longrun.py` + analyzer 测试，task-116）、`0e01006`（docs）；**都不碰上述 4 文件** |
| SHA256 前 16 | `planner.py B34B435CFF45C547`、`longrun.py 858A96ECDB42AB28`、`test_planner.py A183E90924D65DF0`、`test_longrun.py F950FCD982CD38F7`；未变：`farmwork.py 3D2A9E5AD4B84A7A`、`tools/verify-run3.py 7356D4CBA1D0A1EE`、`tools/compare-runs.py CC86CAEAB38363CF` |
| `py_compile -W error::SyntaxWarning` | exit 0（planner / longrun / farmwork） |
| `tests.test_planner tests.test_longrun` | **Ran 272 / OK** |
| 作者两个零影响类（独立复跑） | `TestTask59ReviewNotes` + `TestTask82Lessons` ⇒ **Ran 10 / OK** |
| 全量 `discover -s tests` | **Ran 677 / OK**（HEAD `370909c` 已含 task-116；Lead 的"672 带 2 条 analyzer 红"是 task-116 之前的状态） |
| 我的探针 | `scratch/_t115_probe.py` ⇒ **25/28 PASS**（`scratch/_t115_probe_out.txt`），3 条 FAIL 同根（卡面①末句：名额竞争） |

## §3 逐条对卡（只做 Lead 列的四条）

| 卡面（m05215 / task-115 rev2） | 结论 | 证据 |
| --- | --- | --- |
| ① F1 五类伪造条目逐条再喂 ⇒ 不进次日提示词 + `lessons_rejected` 计数对 + **不许把真教训挤出 20 条** | **拒收/计数 PASS；末句 FAIL** | A1 逐条（卡面点名的五类）：`未知 kind`→`unknown_kind`、`id 与 kind|scope 不符`→`id_mismatch`，各 `dropped=1`、`in_prompt=False`；`合法 kind 自由文本`、`severity 被改`、`last_seq=999999` 三类结构全过 ⇒ 保留（前者 `reasons=['truncated:symptom']`、已折叠单行/无坐标/截断；`severity=9999` 被按 kind 重算为 3，A2f PASS）；A1b 五类一起喂 ⇒ `dropped=2`、`reasons=['truncated:symptom','unknown_kind','id_mismatch']`；A1d 拒收两类的标记零泄漏；**A1c：20 条真教训 + 卡面五类 ⇒ 真教训存活 18/20**（`last_seq=999999` 那条占首位，另两条结构合法各占一席） |
| ② F2 三档预算（我跑四档）⇒ 顺序 = 笔记→决策史→教训库 + 核心字段逐字不变 | **PASS** | B1：四档出现情况 `(T,T,T) → (T,T,F) → (T,F,F) → (F,F,F)`；B2：四档判决本体都是输出前缀（逐字完整）；B3：可选节要么整节进要么整节不进；四档总长 2042 / 2041 / 2040 / 1947（上限 2048） |
| ③ 零判定影响回归（开关 / 篡改 / 坏 JSON / 复盘抛错 四形态） | **PASS** | C1 开关、C2 合法 schema 篡改、C2b 不合 schema 篡改（`lessons_rejected dropped=1 reasons=['unknown_kind']`）、C3 坏 JSON（`lessons_load_failed=1`）、C4 复盘抛错 ⇒ `verified`/`day_justified`/`ended_by`/`checks`/`final_water`(剔 t)/`final`/`stages`/`intents` **逐字相同** + 退出码相同 |
| ④ NIT-1：`no_inventory_space.evidence` 必须是当次真值 | **PASS** | D1：真 `FarmWorker` + 回 dict 的 `no_inventory_space` ⇒ `run.buy_no_space_facts = {'free_slots': 8, 'free_slots_status': 'ok', 'seeds': 0, 'money': 500, 'item': '472', 'price': 0}`，journal `buy_no_space` 带 `free_slots=8`；D2：教训 evidence = `free_slots=8/ok seeds=0 money=500g item=472`，不含写死的"空格=0"，与实测 `free_slots=8` 一致 |
| ⑤ 范围/越界/读数 | **PASS** | 见 §2；全量无红（task-116 已把 analyzer 漂移归零） |

## §4 对抗矩阵与三个最小反例

### A 段（卡面点名的五类 + 结构拒收面）

| 用例 | 结果 |
| --- | --- |
| A1 未知 `kind` | PASS（`unknown_kind`，拒收 + 不进提示词） |
| A1 `id` 与 `kind|scope` 不符 | PASS（`id_mismatch`） |
| A1 `severity` 被改（`9999`，kind 合法） | PASS（保留，但 `severity` 被按 kind 重算为 3；原文仍进提示词——已报备遗留） |
| A1 合法 kind 的自由文本（多行 + 坐标 + 超长） | PASS（保留但已洗：单行、`(12,30)`→`某格`、截断；`reasons=['truncated:symptom']`） |
| A1 `last_seq=999999`（kind/id 合法） | **暴露**：结构全过 ⇒ 保留；**A2g 实测排到注入列表首位** |
| 附加（task-114 新增的拒收面） | `bad_count`、`not_a_mapping` 均 PASS（拒收 + 不进提示词） |
| **A1c 20 条真教训 + 卡面五类** | **FAIL：真教训存活 18/20** |
| A2a 合法 kind + `last_seq=999999` | **暴露**：排首位（`kept=20`、`in_prompt=True`），注入文本出现在教训列表**第一行** |
| A2b 同上 + 20 条真教训 | **FAIL：19/20**（挤掉 `stage_incomplete|g1`） |
| A2c 合法 kind + `last_seq=21`（"像下一天"） | **FAIL：19/20**（同样挤掉 `g1`）——不是只有离谱值才成立 |
| A2d 合法 kind + `last_seq=1` + `count=10**9` | **FAIL：19/20**（同 seq 组内靠 `count` 顶掉 `g1`） |

**最小复现**（只读 + scratch）：

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:PYTHONPATH="<repo>\brain"
& $py scratch\_t115_probe.py     # 看 A1c / A2b / A2e 三行（25/28，3 条 FAIL 同根）
```

构造：20 条真教训 `stage_incomplete|g1..g20`（`last_seq=1..20`）+ 卡面点名的伪造条目各一条。根因两处：

1. `planner.py:_sanitize_lesson`（task-114 新增）校验了 `kind`/`id`/字段类型/文本长度，并把 `severity` 按 `kind` 重算，**但没有钳 `last_seq`/`count`**；
2. `planner.py:579-618 prune_lessons` 的排序键是 `(last_seq, severity, count)` 降序 ⇒ 任何写入者把 `last_seq` 写大（或同 seq 下把 `count` 写大）即可排到最前；`LESSONS_MAX=20` 是硬上限，`kept=20` 时必有一条真教训被挤掉。

**影响面（如实说明）**：当天/当轮的**判定完全不受影响**（③ 已逐字验证）；受损的是"演进"机制本身——(a) 伪造/外部条目可占据注入列表**首位**（A2a；且 B1 已证"简报再紧也保教训"，所以这行几乎必然进最终提示词）；(b) 真教训的 `count`/`first_day` 累计历史被顶掉（条件复现时会重建，累计计数丢失）。威胁模型与 task-112 F1 相同：任何能写 `logs/<run>-lessons.json` 的进程/人。

**为什么算卡面以内**：task-115 rev2 第 1 条把「**`last_seq=999999`**」与「合法 kind 的自由文本、未知 kind、id 不一致、severity 被改」并列为要逐条再喂的五类，同条③明写「伪造条目不许把真教训挤出 20 条上限」；A2b 就是这一句的字面反例。Lead 已报备的豁免是"**内容**仍进提示词"，不覆盖"**名额竞争**"；而 `last_seq` 是**结构性字段**，正是 task-112 NIT-3 点名要锁的对象。

**建议最小修法**（择一，均不碰判定路径、无判定影响）：
1. 载入时把外部条目的 `last_seq` 钳到本次运行已知上界（`len(self.days)+1` 或库内真序最大值）、`count` 钳到合理上界；或
2. `prune_lessons` 排序键改为 `(severity, count, last_seq)`，并把"结构与真教训无法区分"的条目一律排在后面；或
3. 给 `make_lesson` 加来源标记（`src:"agentfarm"`），载入时把无标记条目排在末位（可与 1 合用）。

作者侧覆盖缺口：`tests/test_planner.py:1066 test_load_rejects_foreign_rows_and_reports_them` 里那条 `last_seq=999999` 恰好是**未知 kind**（被别的规则拒掉），且库里只有 2 条记录 ⇒ **没有任何用例覆盖"20 条满库 + 合法 schema 外部条目"的淘汰竞争**。

### B 段（F2 四档预算）

| 档位 | lessons / decisions / notes | 总长 |
| --- | --- | --- |
| 全放得下 | ✅ / ✅ / ✅ | 2042 |
| 挤掉笔记 | ✅ / ✅ / ❌ | 2041 |
| 再挤掉决策史 | ✅ / ❌ / ❌ | 2040 |
| 三节全丢 | ❌ / ❌ / ❌ | 1947 |

⇒ 与卡面⑤/实现 docstring 一致（`planner.py:1030-1050`：核心字段 > 教训库 > 决策史 > 复盘笔记；`if room < len(block): break` 保证整节进/出）。

### C 段（零判定影响，四形态）

C1 开关 / C2 合法 schema 篡改 / C2b 不合 schema 篡改 / C3 坏 JSON / C4 复盘抛错 ⇒ **全部逐字相同**。

### D 段（NIT-1 真值证据）

`FarmWorker.buy` 判据 = "钱降且物品增"（回执 ok 不算数）；`status=no_inventory_space` ⇒ `code=no_space`；`longrun._buy_seed` 随即 `_snap()` 取真值 ⇒ `buy_no_space_facts` 与 journal `buy_no_space` 都带 `free_slots=8`，当晚教训 evidence 用同一份真值 ⇒ **不再有写死的"空格=0"**。

## §5 NIT 与 INFO 表

| 编号 | 级别 | 内容 | 位置 / 复现 |
| --- | --- | --- | --- |
| **FAIL-1** | **卡面①末句未满足（判 FAIL 的唯一一条）** | 合法 schema 的外部条目能与真教训平等竞争 20 个名额并排到首位：`last_seq`/`count` 不钳 + 排序键 `(last_seq, severity, count)` | `planner.py:_sanitize_lesson`、`planner.py:579-618 prune_lessons`；`scratch/_t115_probe.py` A1c / A2b / A2c / A2d / A2e / A2g |
| NIT-1（原） | 已修复（PASS） | `no_inventory_space.evidence` 已是当次真值 | `longrun.py:_lessons_from_day` + `_buy_seed`；探针 D1/D2 |
| NIT-2 | 已报备遗留（Lead 明确"不算 FAIL"），但**影响面比"文字会出现"更大** | 合法 kind 的自由文本仍进提示词；配合 FAIL-1 可**排到教训列表第一位**，且 B1 证明"简报挤干时教训仍优先保留" ⇒ 这段文字几乎必然进最终提示词 | `planner.py:_sanitize_lesson`（只锁结构） |
| INFO-1 | INFO | `buy_no_space` 的 `price` 在我的夹具里是 0（货架清单只在拒绝回执里出现，`_buy_seed` 记的是下单时的价格）；与四条判据无关 | `scratch/_t115_probe_out.txt` D1 |

**NIT-2 的取舍意见（Lead 要我给的理由）**：我认同"完整内容模板校验属行为变更、可留 0.7.29"，但按 FAIL-1 的实测，**它的实际影响不是"某段文字可能出现"，而是"敌意文本能占据最高优先级位置 + 顶掉真教训"**。演进机制的价值取决于"注入的教训是账本产物"，这个保证现在只到"结构正确"。建议：**FAIL-1 随 0.7.28 修**（2~3 行、纯载入侧、作者测试扩一条负例即可），NIT-2 做**最小版**（无来源标记的条目排在真教训之后、不参与 20 名额抢占），完整模板校验留 0.7.29。

## §6 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:PYTHONPATH="<repo>\brain"
& $py scratch\_t115_probe.py                              # 25/28；3 条 FAIL 全在名额竞争
& $py -m unittest tests.test_planner tests.test_longrun   # Ran 272 / OK
& $py -m unittest discover -s tests                       # Ran 677 / OK
```

## §7 结论

- **判定 FAIL**（一条）：卡面第 1 条③「伪造条目不许把真教训挤出 20 条上限」在卡面自己点名的第 5 类（`last_seq=999999`）下不成立，且有 3 个确定性最小反例（A1c 18/20、A2b/A2c/A2d 各 19/20）；根因 = `last_seq`/`count` 未钳 + `prune_lessons` 排序键，属 task-112 NIT-3 未修完的部分。
- **其余全部通过**：五类的拒收与留痕/计数、F2 四档丢弃顺序与核心字段、零判定影响四形态、NIT-1 真值 evidence、范围/越界/全量读数。
- 修复成本极低（2~3 行、无判定影响），建议随 0.7.28 修；若 Lead 认为可保持冻结，则请把 FAIL-1 与 NIT-2 一起列入 0.7.29 批次并附负例。
