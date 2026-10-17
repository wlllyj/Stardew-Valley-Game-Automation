# A″/B″ 验收判据 vs `tools/compare-runs.py` 一致性审计（task-215）

> 只读审计（卡 task-215，rev2）。**本卡不改 `tools/`**：发现的工具问题在 §4 列清并由 Lead 修 + 补用例。
> 依据：`docs/_run10-criteria.md`（57 行，下文行号均为该文件）+ `tools/compare-runs.py`（513 行）+ `brain/agentfarm/planner.py`（2370 行）+ 真账本。

## 0. 结论速览（TL;DR）

- **L0–L5 的机械部分在代码里都有对应实现**，但存在 **4 条实质偏差 + 1 条口径缺口**：
  1. **L0** 文档要求 `lessons.total>=1` **且至少 1 条 `count>=1`**；代码只判 `len(lessons)>=1`（`compare-runs.py:320`）⇒ 少了 `count` 条件。
  2. **L1 分母**未过滤 `kind`：`prompts_of()`（`:234-243`）把所有带 `prompt` 的行都算进 run B 调用集，**含 `kind="review"` 复盘行** ⇒ 与卡面「L1 分母只算决策行」不符（实测 runB 文件 = 70 决策 + 2 review ⇒ 工具报 72 次）。
  3. **L2 的 `improved` 判定是假阳性源**：`:316` `improved = (count_a == 0) or (count_b < count_a)` —— `count_a==0` 时**即使 run B 出现了更多次也报「✅ 减少」**（实测 runA→runB 打出三行 `runA=0 → runB=0 ✅ 减少`）。
  4. **L5 结论未按文档门禁 L3**：文档 §1-L5 要求「L0–L3 任一不成立 ⇒ 结论写不足以判定」；`criteria()`（`:337-346`）只串行判 L0→L1→L2，`tail_b<3` 还**硬编码 3**（文档 §0 是 5 天轮/§1-L4 是尾部窗口）。
  5. **恒退码承诺有洞**：docstring（`:16`）承诺「恒退 0；读不到退 2」，实测**缺账本=2 ✅**，但**账本里有一行坏 JSON ⇒ rc=1**（`load_rows` 里 `raise SystemExit("[exit 2] …")` 的字符串参数被 CPython 当错误消息、rc 记 1）；坏 `-lessons.json` ⇒ 未捕获 `JSONDecodeError` ⇒ rc=1；且文案仍写 `[exit 2]`（误导）。
- **L1 三信号与教训节抬头【逐字一致（子串口径）】✅**：代码常量 `LESSON_SECTION_MARK="从过去几天的账本里总结的教训"`（`:186`）正是 `planner.py:798` 抬头 `lessons（从过去几天的账本里总结的教训，只作参考）:` 的子串；三信号 `lessons_total`/`lessons_hits`/`lesson_section_present` 都在输出与 JSON 里（`:369-370`、`:463-469`、`:491-493`）。
- **六串配对**：现成脚本 **13 份**，但每份都**按 run 写死窗口/路径**；本卡补了**通用** `scratch/_t215_pair_newday.py`（一条命令出配对表，已实测 run9=0/4 缺组、runA-0732=5/5 成组）。

## 1. L0–L5 逐条对账表

| 判据 | 文档（`docs/_run10-criteria.md`） | 代码（`tools/compare-runs.py`） | 一致性 | 差异类型 |
|---|---|---|---|---|
| **L0** | L18：`lessons.total>=1` **且至少 1 条 `count>=1`** | `:320 l0 = len(lessons) >= 1`；教训条目由 `lessons_of()` `:161-182` 读 | ⚠️ 部分 | **文档有代码无**（`count>=1`）|
| **L1** | L19 + L25-28：教训文本进 run B **某次真实调用**提示词 ≥1 条；且报三信号 | `:323 l1 = bool(lessons) and bool(prompts_b) and hits>0`；`hits` 由 `:446-462` 子串比对（`norm()` 归一化）；三信号 `:357-360` | ⚠️ 部分 | **口径缺口**：run B 调用集含 review 行；文档只写"真实调用"，卡面明写"只算决策行" |
| **L2** | L20：按 `(kind, scope)` 聚合同形态，run B **严格小于**（或为 0） | `:262-269 _LESSON_SIGNAL` 5 条 kind→`ended_by`/`event` 计数；`:304-317` `improved=(count_a==0) or (count_b<count_a)` | ❌ 实质不符 | **名不同义不同**：①`count_a==0` 当改进（假阳性）②**忽略 `scope`**（教训条目里就有 `scope` 字段）③信号表只有 5 类，且 `stuck_with_leftover→ended_by:stuck` 与现行形态（`day_end.stages[].stopped=incomplete`、`ended_by=sleep`）对不上 |
| **L3** | L21：≥1 条 run B 边界决策的 `intents`/`reason` 明确体现该教训；L28 提醒**别拿 `lesson_full_text` 做子串比对** | `:326-336` 只算"同指涉"旁证：`_tokens()`（`:294-296`，田区名 + ≥2 位数字）在 `decision_texts`（`:139-144`，intent 的 `reason`+`expected_evidence`）里出现几次 | ⚠️ 部分（工具自己声明只做旁证） | **文档有代码无**（"明确体现"无法机械判；现为宽泛词表命中）|
| **L4** | L22：run B **尾部窗口** VERIFIED 天数 ≥ run A；无新增硬失败类别 | `:325 l4 = (tail_b>=tail_a) and not new_false`；`tail_verified()` `:276-284` 数**整本账本**尾部连续天；`new_false` `:319` 用 `checks_false` 集合差 | ⚠️ 部分 | **名不同义不同**：不是 `--days 3` 尾部窗口；`new_false` 把任何新变为 false 的 `checks` 键都算"新失败类别"（实测把 `zero_action_evidenced` 报成新增失败项）|
| **L5** | L23 + L37：逐条列证据；**L0–L3 任一不成立 ⇒ 写"不足以判定"** | `:337-346` verdict 只门禁 L0/L1/L2；`tail_b<3` 硬编码；`:504-508` 末尾打印 4 条"正式判决请跑" | ❌ 实质不符 | **文档有代码无**（L3 门禁、窗口口径）|

### 三类差异汇总

- **文档有、代码无**：L0 的 `count>=1`；L5 的「L0–L3 任一不成立 ⇒ 不足以判定」；L4 的「尾部窗口」定义；§1-L3 的"明确体现"判定（只做旁证）；§5 的 `worldSeq` 三条测量规则（L47-48）与六串配对（L49）；§6 的三条判据层修正（L55-57）——后两类**本就不属 compare-runs 职责**，验收时必须并列 `verify-run3`/`analyze-longrun` 的原文（文档 L37/L42 已要求）。
- **代码有、文档无**：`:435-444` 的 [1]–[4] 四张计数表（意图形态/取消/stage 失败/stage 成功）；`:486-497` 的 `--json` 结构化输出；`:93-103` 的 `ended_by`/`checks_false` 汇总；`:262-269` 的 `_LESSON_SIGNAL` 映射表；`:32-35` 的 `PROBLEM_STOPPED` 词汇表；`:276-284` 的 `tail_verified`；`:390-513` 的恒退码与末尾"正式判决请跑"清单。
- **名不同义同/近**：`lessons_hits`（代码/文档 L27）vs `lesson_hits`（文档 L28）——同一量两种写法，建议统一为 `lessons_hits`；教训节抬头代码常量缺 `lessons（` 前缀与 `，只作参考）:` 后缀（子串口径，见 §2）；`lesson_hits` 文档说"子串命中（注入后被预算裁掉的部分算未见）"与代码 `norm()` 归一化后子串一致。

## 2. L1 三信号与教训节抬头（逐字原文）

**工具侧**（`tools/compare-runs.py`）

```
:186  LESSON_SECTION_MARK = "从过去几天的账本里总结的教训"
:225-231 def lesson_section_present(prompts): return any(LESSON_SECTION_MARK in p ...)
:323  l1 = bool(lessons) and bool(prompts_b) and hits > 0
:357-360  "lesson_hits"/"lessons_total"/"lesson_section_present" 三值一起输出
:463-469  「教训节抬头「…」在 run B 提示词里：✅ 出现 / ❌ 未见」
:465-473  节在 + 逐条 0 命中 ⇒ 「比对口径警告」（不断言"没送到"）；节与逐条都无 ⇒ 「注入口径警告」
```

**brain 侧**（`brain/agentfarm/planner.py`，教训节渲染 `render_lessons()`）

```
:798  head = "lessons（从过去几天的账本里总结的教训，只作参考）:"
:800-817  每条渲染成一行： "- {mark}{symptom}｜{evidence}｜{HINT_UNVERIFIED_PREFIX}{hint}"
:475/627  UNTRUSTED_LESSON_PREFIX = "[外部条目·未验证] " / HINT_UNVERIFIED_PREFIX = "[模型自述·未验证] "
:615  _strip_coordinates(text)   # 渲染前洗坐标（双保险）
```

**结论**：工具常量与 planner 抬头**逐字一致**（工具取的是抬头的子串，两侧都是 UTF-8 中文原文）；三信号口径在 0.7.37 代码上仍是三值同报 ✅。
**附注（薄弱点）**：`lesson_text()` 优先取 `hint`（`:189-204`），而渲染行里 `hint` 会被 `_strip_coordinates`（`:615`）洗过坐标、并加 `[模型自述·未验证] ` 前缀 —— 若某条 `hint` 含坐标，归一化子串可能命不中（目前实测 4/6 命中，未见此坑）。

## 3. 六串配对（NewDay 链）

### 3.1 现成脚本清单（均为**每 run 一份、窗口/路径写死**）

| 脚本 | 说明 |
|---|---|
| `scratch/runA-tools.py`、`runB-tools.py` | run A/B（0.7.32）冻结 + 六串计数 + 三检查器；`runA-tools.py:48-49` 默认 `--after 03:45:38 --before 04:23:00` |
| `scratch/run8-extract.py`、`run9-extract.py` | run8/run9 抽取 |
| `scratch/run9b-tools.py`、`run9c-tools.py`、`run9d-tools.py` | run9b/9c/9d 抽取（run9b 产出 `logs/run9b-smapi-chain.txt` = 现成的六串+逐条行号表）|
| `scratch/run7-smapi.py`、`run7-smapi-recount.py` | run7 补算 |
| `scratch/_runA3_freeze_smapi.py`、`scratch/_runA3_smapi_wincount.py` | A′（0.7.36）冻结/窗口计数 |
| `scratch/_t40_audit.py`、`scratch/_t45_mk_fixtures.py` | 引用六串做审计/造夹具（非配对入口）|

**缺口**：没有"任意冻结窗口 → 六串配对表"的通用入口；换 run 要复制改代码。
**本卡补齐**：`scratch/_t215_pair_newday.py`（只读、stdlib、UTF-8 安全）。

### 3.2 一条命令出配对表

```powershell
$env:PYTHONUTF8=1
python scratch\_t215_pair_newday.py --smapi logs\runA-0732-smapi-window.txt --after 03:45:38 --before 04:23:00 --json scratch\_t215_pair_runA.json
```

- **输入**：`logs/run*-smapi-window.txt`（`scratch/runX-tools.py` 已冻结的 SMAPI 窗口；源 = `%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`）
- **输出格式**：`[1] 六串计数（键/次数/行号）` + `[2] 按 NewDay 成组配对（每条 NewDay 后 180s 内找其余串，逐条 ✅成组 / ❌缺组⇒【无法判定】）` + 结论行 + 可选 JSON。
- **实测两例**（产物 `scratch/_t215_pair_run9.txt` / `scratch/_t215_pair_runA.txt`）：
  - `logs/run9-smapi-window.txt`（20:40:40–21:04:17，4447 行）：NewDay=4，其余**全 0** ⇒ **4/4 组缺组 ⇒【无法判定（落盘链缺组）】**（与 run9 已知"落盘 0/4"一致，可直接当反例夹具）。
  - `logs/runA-0732-smapi-window.txt`（03:45:38–04:23:00，4725 行）：NewDay/before_save/save_called/save_task/saving/completed/after_save **各 5 次** ⇒ **5/5 组成组 ✅**（逐组行号 892→895→896→897→898→900→901 等）。

### 3.3 第 4 串的两个变体（**必须两个都数**）

真实成功跨日的日志里两条都出现（runA 冻结窗口 L897/L898）：

```
[Synchronizing 'Save' task...]        ← 第 4a 串（SMAPI 任务）
[Saving without compression...]       ← 第 4b 串（游戏侧）
```

`docs/_run10-criteria.md` §5-3（L49）列的是 `Saving without compression`；Lead 转述与 `scratch/runX-tools.py` 历史实现数的是 `Synchronizing 'Save' task` —— **不是矛盾，是两个都要**（成功链上二者相邻出现、缺任一都要单列）。通用脚本已按 7 键（1+2+3+4a+4b+5+6）输出。

## 4. 薄弱点（按风险排序；前两条会**直接改变 A/B 结论**）

1. **L2 假阳性（高）**：`count_a == 0` 即判"减少"。实测 runA→runB 输出三行 `runA=0 → runB=0 ✅ 减少` ⇒ 只要 run A 里该形态没出现、run B 里出现更多次，L2 仍 ✅。**建议**：`improved = (count_a > 0 and count_b < count_a) or (count_b == 0 and count_a >= 0)` 之类，并把 `count_a==0` 单列为【无法判定/未出现】。
2. **L2 信号映射过期（高）**：`_LESSON_SIGNAL` 把 `stuck_with_leftover → ended_by:stuck`，但现行账本的 `stuck_with_leftover` 形态是「`day_end.stages[].stopped=incomplete` + `leftover>0`，`ended_by=sleep|sleep_failed`」⇒ 实测 `ended_by:stuck` 恒 0 ⇒ L2 自动变 ✅（叠加第 1 条）。**建议**：信号改从 `day_end.stages[]` 的 `(stage, stopped, leftover)` 聚合，并按教训里的 `scope` 比较（文档 L20 要求）。
3. **L1 分母含 review 行（中）**：`prompts_of()` 不过滤 `kind`。实测 runB-0732 = 70 决策 + 2 review（工具报 72 次调用）；旧 run（run6/7/8/9/9b）**全部行无 `kind`** ⇒ 按 `planner.py:2253` 注释（旧行按决策处理）兼容，但 review 行必须排除。**建议**：`prompts_of` 增加 `kind in ("decision", "") / kind missing` 过滤，并单列 review 调用数。
4. **恒退码有洞（中）**：缺账本 2 ✅；坏 JSON 行 ⇒ `raise SystemExit("[exit 2] …")` ⇒ **rc=1**（实测），文案却写 `[exit 2]`；坏 `-lessons.json` ⇒ 未捕获异常 rc=1；日志/lessons 读不到（`OSError`）同理。**建议**：统一 `sys.exit(2)` 或 `return 2`，并把 `load_rows` 的 JSON 错误改成返回错误标记。
5. **L0 缺 `count>=1`（低，但文档口径更严）**：现状所有 `-lessons.json` 条目 `count>=1`，暂无实际分歧；补上防止未来"空教训"误过。
6. **L5 门禁与硬编码（低）**：`tail_b<3` 写死、L3 未入门禁；文档 §0 说 A/B 是 5 天轮、§1-L4 说"尾部窗口" ⇒ 建议加 `--tail-days`（默认 3）并把 L3 结论作为 verdict 的必要字段。
7. **L4 `new_false` 口径（低）**：任何 `checks` 键在 B 里新变 false 都算"新增失败类别"（实测把 `zero_action_evidenced` 报出）——需在证据文档里人工复核它是否真"硬失败"。
8. **`_strip_coordinates` 与子串命中的相互影响（低）**：见 §2 附注；建议 L1 命中检查同时用"渲染后行"（symptom/evidence/hint 分别比对）而不是单一 `hint`。
9. **卡面先例数字与现存文件不一致（记录，不影响规则）**：Lead 提到的「runB 47 决策 + 1 review」在现存 `logs/longrun-runB-0732-llm.jsonl` 上是 **70 决策 + 2 review**（可能当时文件未写完）；另 A″/B″ 现行是 0.7.35 的 `logs/longrun-runA2-0735.jsonl` / `…runB2-0735.jsonl`，但**这两个 `-llm.jsonl` 侧车在本机不存在** ⇒ 对现行 A″/B″ 跑 L1 会得到"读不到 run B 留痕"（属预期路径缺失，不是"没注入"）。

## 5. 复现命令与读数

```powershell
$env:PYTHONUTF8=1
# ① 工具本体（真账本对照；只读，不改判据）
python tools\compare-runs.py --run-a logs\longrun-runA-0732.jsonl --run-b logs\longrun-runB-0732.jsonl --json scratch\_t215_evolve.json
# ② L0/L1 分母与 kind 分布（本卡探针）
python scratch\_t215_probe.py
# ③ 六串配对（通用；两个反例/正例已跑）
python scratch\_t215_pair_newday.py --smapi logs\run9-smapi-window.txt --after 20:40:40 --before 21:04:17
python scratch\_t215_pair_newday.py --smapi logs\runA-0732-smapi-window.txt --after 03:45:38 --before 04:23:00
# ④ 恒退码体检
python tools\compare-runs.py --run-a logs\no-such.jsonl --run-b logs\longrun-runB-0732.jsonl   # 期望 rc=2 ✅ 实测 2
python tools\compare-runs.py --run-a scratch\_t215_bad.jsonl --run-b logs\longrun-runB-0732.jsonl  # 期望 2，实测 1 ❌
```

**实测读数（2026-10-17）**：
- `compare-runs` 真跑 runA→runB：L0 ✅（6 条）/ L1 ✅（**4/6** 命中，run B **72** 次调用）/ L2 ✅（**假阳性**，三行 0→0）/ L4 ❌（尾部 0→0；新增 `zero_action_evidenced`）/ L5 =「有演进痕迹，但 run B 未达标（尾部连续 VERIFIED < 3 天）」。
- `_t215_probe.py`：runA-0732-llm = 75 决策 + 6 review；runB-0732-llm = 70 + 2；run9c = 21 + 5；run9d = 17 + 8；run6/7/8/9/9b 全 `<missing>`（旧行，按决策算）。
- 教训库形状：`id/kind/scope/symptom/evidence/hint/count/first_day/last_day/last_seq/severity/src(/untrusted)` —— 文档 L26 说的 `id/symptom/evidence/hint/count` ✅ 齐备，且**多出 `kind/scope`**（L2 应按它聚合）。
- 六串配对：run9 = 0/4 组（缺组⇒无法判定）；runA-0732 = 5/5 组 ✅。
