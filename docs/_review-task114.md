# task-114（教训库信任边界 / 裁剪优先级 / 真值证据）delta 独立复验

- 验收人：deputy-lead；任务：task-115（rev?，in_progress，Lead m05215 派工）
- 对象：`c135edc`（0.7.28 task-114：`brain/agentfarm/planner.py`、`brain/agentfarm/longrun.py`、`tests/test_planner.py`、`tests/test_longrun.py`）
- 复验时 HEAD：`370909c`（其后的 `370909c` = task-116 analyzer 收录 `lessons_rejected`、`0e01006` = docs；`git diff --stat c135edc..HEAD -- <上述 4 文件>` **为空** ⇒ 我跑的就是 task-114 的代码）
- 判定：**PASS-WITH-NITS**（四条 delta 项全部通过；另有 1 条"修了但没修完"的排序面缺口，见 §4/§5 NIT-1）
- 日期：2026-10-16

## §1 一句话判定

task-114 把 task-112 F1/F2 两条 FAIL 的**主体**修住了：五类伪造条目里不合 schema 的四类被逐条拒收并留痕（`lessons_rejected` + 原因/计数正确）、四档预算下丢弃顺序已变成 **复盘笔记 → 决策史 → 教训库** 且核心字段逐字不变、四种形态（开关 / 篡改 / 坏 JSON / 复盘抛错）下**判定字段逐字相同**、`no_inventory_space` 的 evidence 已是当次真值（`free_slots=8/ok seeds=0 money=500g item=472`）；剩下的缺口只有一条，且是 task-112 §5 **NIT-3 里点名过、这次只修了一半**的那一项：`last_seq`/`count` 不钳 ⇒ 外部写入的**合法 schema**条目仍能与真教训平等竞争 20 个名额、并把自己排到注入列表**首位**（3 个最小反例见 §4）。

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
| 我的探针 | `scratch/_t115_probe.py` ⇒ **19/22 PASS**（`scratch/_t115_probe_out.txt`），3 条 FAIL 同根（排序面） |

## §3 逐条对卡（只做 Lead 列的四条）

| 卡面（m05215） | 结论 | 证据 |
| --- | --- | --- |
| ① F1 五类伪造条目逐条再喂 ⇒ 不进次日提示词 + `lessons_rejected` 计数对 + 不许把真教训挤出 20 条 | **拒收/计数 PASS；末句 FAIL（见下）** | A1 逐条：`unknown_kind` / `id_mismatch` / `bad_count` / `not_a_mapping` 各 `dropped=1`、`in_prompt=False`；A1b 五类一起喂 ⇒ `dropped=4`、`reasons=['unknown_kind','id_mismatch','bad_count','not_a_mapping','truncated:symptom']`（≤6 上限）、`kept=20`；A1d 五个标记里只有合法 schema 那条的 `MARKER-SANITIZE` 进提示词（其余零泄漏，已折叠成单行、`(12,30)`→`某格`、截断）；**A1c：20 条真教训 + 五类 ⇒ 真教训存活 19/20**（合法 schema 那条占一席） |
| ② F2 三档预算（我跑四档）⇒ 顺序 = 笔记→决策史→教训库 + 核心字段逐字不变 | **PASS** | B1：四档实测 `(lessons,decisions,notes)` 出现情况 `(T,T,T) → (T,T,F) → (T,F,F) → (F,F,F)`；B2：四档判决本体都是输出前缀（逐字完整）；B3：可选节要么整节进要么整节不进（不切半节）；四档总长 2042 / 2041 / 2040 / 1947（`PROMPT_BRIEF_MAX_CHARS=2048`） |
| ③ 零判定影响回归（开关 / 篡改 / 坏 JSON / 复盘抛错 四形态） | **PASS** | C1 开关：`verified`/`day_justified`/`ended_by`/`checks`/`final_water`(剔 t)/`final`/`stages`/`intents` 逐字相同 + 退出码相同；C2 库被篡改（合法 schema ⇒ 保留）：逐字相同；C2b 不合 schema 篡改 ⇒ `lessons_rejected dropped=1 reasons=['unknown_kind']` 且判决逐字相同；C3 坏 JSON ⇒ `lessons_load_failed=1` + 判决逐字相同；C4 复盘抛错 ⇒ 判决逐字相同 |
| ④ NIT-1：`no_inventory_space.evidence` 必须是当次真值 | **PASS** | D1：真 `FarmWorker`+回 dict 的 `no_inventory_space` ⇒ `run.buy_no_space_facts = {'free_slots': 8, 'free_slots_status': 'ok', 'seeds': 0, 'money': 500, 'item': '472', 'price': 0}`，journal `buy_no_space` 带 `free_slots=8`；D2：教训 evidence = `free_slots=8/ok seeds=0 money=500g item=472`，不含写死的"空格=0"，与实测 `free_slots=8` 一致 |

## §4 对抗矩阵与三个最小反例

### A 段（F1 五类 + 排序面扩测）

| 用例 | 结果 |
| --- | --- |
| A1 未知 kind / id 不符 / 字段类型错 / 非 Mapping | PASS（逐条拒收 + 留痕 + 不进提示词） |
| A1-合法 schema + 多行/坐标/超长 | PASS（保留但已洗：单行、无坐标、截断；`reasons=['truncated:symptom']`） |
| A1b 五类一起喂 | PASS（`dropped=4`、原因齐全、`kept=20`） |
| A1c 20 条真教训 + 五类 ⇒ 真教训存活 | **FAIL：19/20**（`stage_incomplete|g1` 被挤出） |
| A1d 只有合法 schema 那条能进提示词 | PASS（`leaked=[]`，即四个不合 schema 的标记零泄漏） |
| A2a 合法 kind + `last_seq=999999` | **暴露**：被排到首位（`kept=20`、`in_prompt=True`）——注入文本出现在教训列表**第一行** |
| A2b 同上 + 20 条真教训 | **FAIL：19/20**（挤掉 `g1`） |
| A2c 合法 kind + `last_seq=21`（像"下一天"） | **FAIL：19/20**（同样挤掉 `g1`）——不是只有离谱值才成立 |
| A2d 合法 kind + `last_seq=1` + `count=10**9` | **FAIL：19/20**（同 seq 组内靠 count 顶掉 `g1`） |

**最小复现**（只读 + scratch）：

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:PYTHONPATH="<repo>\brain"
& $py scratch\_t115_probe.py     # 看 A1c / A2b / A2e 三行
```

构造（`scratch/_t115_probe.py`）：20 条真教训 `stage_incomplete|g1..g20`（`last_seq=1..20`）+ 1 条**合法 schema** 外部条目（`kind=unreachable`、`id=unreachable|clear_area`、`last_seq=999999`）。根因两处：

1. `planner.py:_sanitize_lesson`（task-114 新增）校验了 `kind`/`id`/类型/文本长度、并把 `severity` 按 kind 重算，**但没有钳 `last_seq`/`count`**；
2. `planner.py:579-618 prune_lessons` 的排序键是 `(last_seq, severity, count)` 降序 ⇒ 任何写入者只要把 `last_seq` 写大（或同 seq 下把 `count` 写大）就能排到最前，并挤掉排最后的真教训；`LESSONS_MAX=20` 是硬上限，`kept=20` 时必有一条真教训被挤掉。

**影响面（如实说明）**：判决**完全不受影响**（③ 已逐字验证）；受损的是"演进"机制本身——(a) 伪造/外部条目可占据注入列表**首位**（A2a；且 B1 已证"简报再紧也保教训"，所以这行几乎一定进最终提示词）；(b) 真教训的 `count`/`first_day` 累计历史被顶掉（条件复现时会重建，但累计计数丢失）。威胁模型与 task-112 F1 相同：任何能写 `logs/<run>-lessons.json` 的进程/人。

**这条不是新面**：task-112 §5 NIT-3 原文就是"`load_lessons_file` 的容错面过宽：未知 `kind`、超范围 `severity`、**任意 `last_seq` 全收**"。task-114 修好了前三项中的 kind/id/类型/severity，**`last_seq`/`count` 未钳** ⇒ 属"修了但没修完"。

**建议最小修法**（择一，均不碰判定路径、无判定影响）：
1. 载入时把外部条目的 `last_seq` 钳到本次运行已知上界（`len(self.days)+1` 或库内真序最大值）、`count` 钳到合理上界；或
2. `prune_lessons` 排序键改为 `(severity, count, last_seq)`，并把"结构与真教训无法区分"的条目一律排在后面；或
3. 给 `make_lesson` 加来源标记（`src:"agentfarm"`），载入时把无标记条目排在末位（可与 1 合用）。

### B 段（F2 四档预算）

`我自造四档`（比卡面要求的三档多一档），实测出现情况：

| 档位 | lessons / decisions / notes | 总长 |
| --- | --- | --- |
| 全放得下 | ✅ / ✅ / ✅ | 2042 |
| 挤掉笔记 | ✅ / ✅ / ❌ | 2041 |
| 再挤掉决策史 | ✅ / ❌ / ❌ | 2040 |
| 三节全丢 | ❌ / ❌ / ❌ | 1947 |

⇒ 与卡面⑤/实现 docstring 一致（`planner.py:1030-1050`：核心字段 > 教训库 > 决策史 > 复盘笔记；`if room < len(block): break` 保证整节进/出）。

### C 段（零判定影响，四形态）

C1 开关 / C2 合法 schema 篡改 / C2b 不合 schema 篡改 / C3 坏 JSON / C4 复盘抛错 ⇒ **全部逐字相同**（比较字段 = `verified`/`day_justified`/`ended_by`/`checks`/`final_water`(剔 t)/`final`/`stages`/`intents`，并比退出码）。

### D 段（NIT-1 真值证据）

`FarmWorker.buy` 判据 = "钱降且物品增"（回执 ok 不算数），`status=no_inventory_space` ⇒ `code=no_space`；`longrun._buy_seed` 随即 `_snap()` 取真值 ⇒ `buy_no_space_facts` 与 journal `buy_no_space` 都带 `free_slots=8`，当晚教训 evidence 用同一份真值 ⇒ **不再有写死的"空格=0"**。

## §5 NIT 与 INFO 表

| 编号 | 级别 | 内容 | 位置 / 复现 |
| --- | --- | --- | --- |
| NIT-1 | **真实、可复现**（卡面①末句按字面即 FAIL） | 外部**合法 schema** 条目能与真教训竞争 20 个名额并排到首位：`last_seq`/`count` 不钳 + 排序键 `(last_seq, severity, count)` | `planner.py:_sanitize_lesson` / `planner.py:579-618 prune_lessons`；`scratch/_t115_probe.py` A1c/A2b/A2c/A2d/A2e |
| NIT-2 | 已报备遗留（Lead 明确"不算 FAIL"），但**影响面比"文字会出现"更大** | 合法 kind 的自由文本仍进提示词；配合 NIT-1 可**排到教训列表第一位**，且 B1 证明"简报挤干时教训仍优先保留" ⇒ 这段文字几乎必然进最终提示词 | `planner.py:_sanitize_lesson`（只锁结构）；理由与建议见下 |
| INFO-1 | INFO | `buy_no_space` 的 `price` 在我的夹具里是 0（货架清单只在拒绝回执里出现，`_buy_seed` 记的是下单时的价格）；与四条判据无关 | `scratch/_t115_probe_out.txt` D1 |

**NIT-2 的取舍意见（Lead 要我给的理由）**：我认同"内容模板校验属行为变更、不进 task-114 必修"，但按 NIT-1 的实测，**它的实际影响不是"某段文字可能出现"，而是"敌意文本能占据最高优先级位置 + 顶掉真教训"**。演进机制的全部价值取决于"注入的教训是账本产物"；现在这个保证只到"结构正确"。因此我的建议是：**NIT-1 随 0.7.28 修**（2~3 行、纯载入侧、作者测试可直接扩一条负例），并把 NIT-2 一并做**最小版**（无来源标记的条目一律排在真教训之后 + 不参与 20 名额的抢占）；完整的内容模板校验可留 0.7.29。若 Lead 选择保持 0.7.28 冻结不动，则请把这两条一起写进 0.7.29 批次（建议与 task-109/117 同批）并附负例。

## §6 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:PYTHONPATH="<repo>\brain"
& $py scratch\_t115_probe.py                              # 19/22；3 条 FAIL 全在排序面
& $py -m unittest tests.test_planner tests.test_longrun   # Ran 272 / OK
& $py -m unittest discover -s tests                       # Ran 677 / OK
```

## §7 结论

- **四条 delta 项全部通过**：F1 拒收与留痕/计数正确、F2 丢弃顺序与核心字段正确、零判定影响四形态逐字成立、NIT-1 的 evidence 已是当次真值。
- **一条残留**：卡面①末句"不许把真教训挤出 20 条"在"合法 schema 外部条目"形态下不成立（3 个最小反例；根因 = `last_seq`/`count` 未钳 + 排序键），系 task-112 NIT-3 未修完的部分。
- 判定 **PASS-WITH-NITS**；若 Lead 按字面口径要把它计入卡面①，则本条应记 FAIL（复现见 §4）。是否随 0.7.28 修见 §5 的取舍意见：**我建议修**（成本 2~3 行、无判定影响）。
