# 账本证据可用性核对（observer · 2026-10-18）

> 卡面来源：Lead 2026-10-18 追加小卡（只读）——「A8/A9 账本里到底有没有**逐格 tiles** 与**每次 observe 的原始计数**？」
> 目的：判定 T8/T10 能否在**既有账本**上复算（`blockers_zone` 新旧差、双轨 VERIFIED、每日观测份数），还是必须等新跑。
> 写范围：仅本文件（`docs/_observe-*.md`）。未改生产代码、未动任务板、未碰游戏、未 deploy。
> 路径约定：`brain/agentfarm/*.py`、`mod/AgentFarm.Bridge/*.cs`、`tools/*.py`、账本 `logs/*.jsonl`。

## 0. 结论速览（先看这三行）

| 复算目标 | 能否在**既有 A8 账本**上复算 | 关键依据 |
|---|---|---|
| `blockers_zone` **新口径**（목표：BLOCKER_KINDS ∪ clump）新旧差 | **部分**：旧口径 12 天可复算；新口径（需按区拆 clump）**仅 5 天 / 仅 field_ne 可复算**；farm 级障碍 **不可复算** | §4.1 |
| **双轨 VERIFIED**（tail VERIFIED ∩ 当日有实质工作） | **可以**（字段齐；`verify-run3.py` 已有 0 格工作守卫） | §4.2 |
| **每日 ≥2 份独立观测**计数 | **不可复算**（账本无逐次 observe 记录；`obs_seq` 仅 9 处） | §4.3 |

一句话：**"清空归零"能验旧口径、验不了新口径（缺按区 clump 拆分）；"每日观测份数"必须等新跑插桩。**

## 1. 账本清单

| 文件 | 行数 | 字节 | 说明 |
|---|---:|---:|---|
| `logs/longrun-runA8-0743.jsonl` | 1322 | 933518 | 主账本（journal）：`event` 逐条 |
| `logs/longrun-runA8-0743-llm.jsonl` | 24 | 95440 | LLM trace：每日 1 条 `decision`（new_day 边界）+ 1 条 `review`，含 `prompt`/`raw` |
| A9 | — | — | **【不存在】** `logs/` 内无 `runA9*` 文件 ⇒ A9 相关一切【无法判定】 |
| `logs/runA8-0743-sixchain-progress.jsonl` | — | — | **【缺失】** 该文件名实际不存在（Lead 提到的名字在磁盘上没有；最近的进度文件见 `logs/` 列表，非此名） |

写入器：`brain/agentfarm/longrun.py:1163-1168`（主 journal 与 `<stem>-llm.jsonl` 路径派生）；
LLM trace 落盘 `brain/agentfarm/planner.py:2503-2530`（`prompt` 上限 8000 字，`planner.py:403 LLM_TRACE_MAX_PROMPT_CHARS=8000`、`planner.py:2314/2524`）。A8 各条 `prompt_chars` 约 850–1560，`prompt_truncated=False` ⇒ 本 run 未截断。

## 2. A8 主账本：事件与字段

顶层事件直方图（`event=` / 无 event 用 `stage=`）：`clear_area`×417、`outcome`×172、`decision`×164、`intent_verdict`×160、`stage_stop_named`×95、`stage_shortfall`×95、`idle`×93、`encircled`×91、`plot`×47、`day_end`×12、`day_start`×12、`stamina_budget`×12、`lessons`×12、`sleep`×12、`review_llm`×12、`seed_gate`×10、`no_seed_for_sale`×12、`tool_upgrade_skipped`×12、`buy`×1 …（共 46 种）。

### 2.1 逐格（坐标）tiles —— 有坐标，**无 kind**
A8 中 `tiles[]` 以 **`[x,y]` 坐标对**形式出现（路径来自递归扫描）：
- `day_end.stages[].cleared_tiles[][]`（172 条记录，共 578 组）—— 真正发生 kind 变化的格
- `day_end.stages[].already_tiles[][]`（100）、`encircled_tiles[][]`（182）、`unreachable_tiles[][]`（44）
- `stage_stop_named.tiles[][]`（218）、`stage_exhausted.tiles[][]`（20）、`unreachable_summary.tiles[][]`（40）、`encircled_summary.tiles[][]`（4）
- `day_end.unreachable_tiles[][]`（50）、`day_end.encircled_tiles[][]`（4）、`day_end.scope_shed_tiles`（12）、`day_end.deferred_tiles`（12）、`day_end.stages[].alloc_capped_tiles`

⚠ **关键缺口**：这些坐标对**不含 `kind`**。执行器**算过**逐格 kind（`longrun.py:8463-8470`：`before_kind=(s.before or {}).get("kind")` / `after_kind=...`，不相等才记入 `cleared_tiles`），但落盘只写坐标（`longrun.py:8705 "cleared_tiles": [list(t) for t in cleared_tiles]`）⇒ **"这格清掉的是 clump 还是 weed"在账本里查不到**。

另有 `tiles` 作为**整数计数**的位置（易与坐标列表混淆）：`day_end.plots[].tiles`（每区格数，47 条）、`day_end.final_water.tiles`（=farm.hoeDirt，整数）。

### 2.2 观测计数 —— 只有"派生摘要"，**没有原始 observe payload**
- `day_end.final.farm` = **白名单**：`longrun.py:3252-3256` 只写 `("loaded","complete","crops","dryCrops","dryDeadCrops","unwateredCrops","hoeDirt","deadCrops")`。
  ⇒ **无 weeds/stones/twigs/trees/clumps/stumps/boulders 计数**。Mod 其实**有**这些（`mod/AgentFarm.Bridge/Contracts.cs:938-993`：`Weeds/Stones/Twigs/Trees/Stumps/Boulders/ClumpsTotal/Clumps/ClumpsUnclassified`），但被 runner 丢弃。
- `day_end.final.counts_scope = "window"`（`longrun.py:3252`）：明确标注窗口口径（≤400 格、截断）。
- **唯一带 kind 直方图的字段**：`day_end.intent_coverage[].evidence.counts`（含 `blockers/clumps/trees/weeds/stones/twigs/tillable/dirt/...`）+ `evidence.obs_seq`。写入 `longrun.py:1690-1736 _no_target_evidence()`（`evidence["counts"]=dict(brief.counts)`；`evidence["obs_seq"]=obs["worldSeq"]`，`longrun.py:1706-1708`），仅在构造 `no_target` 证据包时产生 ⇒ **A8 只有 9 条**（覆盖 5 个不同日：winter7/8/9/10/18，且**只有 field_ne 一个区**）。
- `-llm.jsonl` 的 `prompt` 内嵌：`counts={...}`（**窗口口径**，含 `clumps`）+ 逐区行 `- field_ne 农场东北田区：可锄 N 格、待清理 M 格…`（`fields.py:329-340 zone_brief_lines`）。**每日 1 条 decision**（new_day 边界），非每次观测。
- `receipt.worldSeqBefore/After`：仅 1 条（`buy` 事件）。
- **无 `event=="observe"`**；递归扫描**全账本无任何原始 `tiles[]`（含 kind/toolOk）快照**。

## 3. 直接回答卡面两问

**Q1「逐格 tiles 有没有？」** —— **有坐标、无 kind**（§2.1）。原始 `observe?detail=full` 的 `tiles[]`（≤400 格、含 `kind/toolOk`）**未落盘**。

**Q2「每次 observe 的原始计数有没有？」** —— **没有原始 payload**。只有 (a) farm 白名单（无障碍计数）、(b) 9 条按区 `evidence.counts`（含 clump 拆分）、(c) LLM trace 的 prompt 文本（窗口口径 + 逐区"待清理"数，**不含 clump**，因 `fields.py:315` 用 `BLOCKER_KINDS`）。

## 4. 复算判定

### 4.1 `blockers_zone` 新旧差 —— **部分可复算**
- **旧口径**（仅 `BLOCKER_KINDS`）按区按日：**12 天可复算**——源=`-llm.jsonl` 每日 prompt 的逐区行（`待清理 M 格`，`fields.py:337`）+ 顶层 `counts.blockers`。
- **新口径**（`BLOCKER_KINDS ∪ clump`）按区：需**按区拆 clump** ⇒ 只有那 **9 条 `evidence.counts`（5 日 / field_ne）**含 `clumps` 字段可加总 ⇒ **其余区/日【无法判定】**。
- **farm 级障碍**（AGENTS.md 提的 `farm` 计数）：**不可复算**（白名单丢弃，§2.2）。
- **附加风险**：zone 行/窗口 counts 均来自**截断观测**（A8 有 59 处 `tilesTruncated`；`day_end` note 明写"数据不完整"）⇒ 即便算得出，也是**下界**，不等于"区内实际 blocker 数"。

### 4.2 双轨 VERIFIED —— **可以复算（且工具已在）**
- 账本齐备：`day_end.verified`、`day_end.ended_by/ended_reason`、`day_end.stages[].ok / requested_tiles / cleared_tiles[][]`、`checks.no_unmet_stages / day_justified`、`slept_without_work`。
- `tools/verify-run3.py` **已实现**"0 格工作却 VERIFIED"守卫：`:1071-1097`（`verified is True 且 无 / 0 格 ok` ⇒ problem）、`:1111-1126`（`ok_self<=0` ⇒ problem；`0<ok<5` ⇒ info）。⇒ 双轨**字段与工具都够**。
- A8 实测（本审计复算）：7 个 VERIFIED 日 = winter **8/10/11/13/15/16/17**，`ok_steps` 分别 69/12/12/12/12/12/16，`ended_reason` 全以 `no_work:当季（winter）没有可种的种子` 开头、`ended_by=sleep`、`slept_without_work=False`。
  ⇒ **它们不是"零动作"，而是"当季无种可种"提前收工却仍 VERIFIED**；"白拿"点**不在"有无工作"**（ok>0），而在**"提前收工的口径正当性（`day_justified`）"**与**"指定区残留未清"**两个判据上。

### 4.3 每日 ≥2 份独立观测 —— **不可复算**
- 账本无逐次 observe 记录；`obs_seq`（=WorldSeq）仅出现 **9 次**（全在 §2.2 的 evidence 内），且是**全局单调**值（14…2518），**无法**据此换算"某日观测了几次"。
- 最接近的替代指标：`verify-run3.py:161-180 _FARM_SIGNAL_EVENTS` + `:248-255`（`farm_signals` 逐日累加）——但那是**"在户外农场动过手"的事件量**（presence 证据），**不是"独立观测份数"**。
  ⇒ **【无法判定】；需新跑时**在每次 `observe` 落一条 `{event:"observe", t, worldSeq, scope}` 才能计数。

## 5. 附：对 T7 第 4 条的补充证据（供 T13 对抗核验采信）

T7 文档第 4 条（"`no_work` VERIFIED 白拿 / 缺双轨"）据本次独立核验需**补强**（非推翻）：
- 事实更正：`tools/verify-run3.py:1071-1097,1111-1126` **已有**"0 格工作却 VERIFIED ⇒ problem"守卫 ⇒ 不是"完全缺双轨工具"。
- 真实缺口收窄为两点：① A8 的 7 个 VERIFIED 日**都有 ok>0**，故逃过该守卫；② 账本**无"指定作业区残留"字段**，无法判"提前收工但指定区没清空"。
- 依 Lead 指示（m00277）**不自行改 T7 措辞**，本补强仅作 T13 证据。

## 6. 已知限制 / 建议插桩（谁写什么）

- 本审计**只读**既有 A8 账本 + 代码；**未跑**任何游戏或长跑；A9【不存在】。
- 建议（供 Lead 派卡，不构成本人动作）：
  1. `longrun.py:3252-3256` 白名单增补 `weeds/stones/twigs/trees/stumps/boulders/clumpsTotal`（只写字段、不改判定）⇒ farm 级障碍可复算。
  2. `longrun.py:8705` 旁增 `cleared_kinds[]`（`before_kind→after_kind`）⇒ 清障按 kind 可复算。
  3. 每次 `observe` 记 `{event:"observe", worldSeq, scope}` ⇒ "每日观测份数"可复算。
  4. `zone_brief_lines`（`fields.py:329-340`）按区补 clump 拆分 ⇒ 新口径 `blockers_zone` 当场可算。
- **结论须逐条有 `文件:行号`**；缺失项一律【缺失】/【无法判定】，不以推断代实测。
