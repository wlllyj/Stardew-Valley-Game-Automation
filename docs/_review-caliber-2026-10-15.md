# task-86 独立验收：`tools/verify-run3.py` 的"尾部达标窗口"口径变更（`7c4ff68`）

- 验收人：deputy-lead（只读 `tools/`、`brain/`；未碰游戏/桥；自写脚本都在 `scratch/`）
- 对象：`7c4ff68`（`docs/_run6-criteria.md` +5、`scratch/_run7_summary.py` +44、`tests/test_verify_run3.py` +35、`tools/verify-run3.py` +30，共 114 insertions / **0 deletions**）；父 `1ffe2ca`
- 冻结副本（`python scratch/_t86_freeze.py` 可随时重生成）：`scratch/_t86_tool_old.py` = `7c4ff68^`（1109 行，**LF** sha256 `7532E7836F75417E5D61E6BB150BC858FF6EC6D47FAD5F877BC888C8888E0872`；早前我用 `git show > file` 生成的副本是 CRLF，sha256 `EB186584…`，行数与行为相同）、`scratch/_t86_tool_new.py` = `7c4ff68`（1139 行，sha256 `3573A39700B9BDD397023DDA6B60B9C7F2AD4C34432B7F17E6A1F973CAA46EA0`，与仓库现行 `tools/verify-run3.py` 逐字节相同）

## §1 判定

**FAIL**（2 条独立理由，均可复现）

1. **打穿要求 ④：窗口内的 fatal 问题可以被"改 key"降级成 `history_problems` ⇒ 结论从 `needs_review` 变 `VERIFIED`。** 只要把该日 `day_start.day[1]`（季节）写成含 `]` 的字符串（例 `spring]x`），问题前缀变成 `[spring]x 11] …`，`report()` 用 `p[1:].split("]", 1)[0]` 解析出的 head 是 `spring`，与 `tail_names` 不匹配 ⇒ 被当成"窗口之外"。该通道在 `7c4ff68` **之前不存在**（旧口径该问题一律 fatal）⇒ 属新口径引入的降级通道，不是既有盲区。见 §3 A4b。
2. **回答 Lead 的问题："会"——账本越长、窗口外问题越多，窗口之外的系统性缺陷会被一路放过。** A6 = 27 天全程"浇水没做完"（每天 5 条问题）+ 尾部 3 天全绿 ⇒ 新口径 `VERIFIED`（135 条 history），旧口径 `needs_review`。若这是刻意取舍，须在口径文档与发布清单里写死"验收只覆盖尾部 N 天"，并给历史问题加可视门槛（§6 NIT-2）。

设计本身（窗口 = 尾部连续 N 天、`streak < --days` 不降级、全局问题永不降级、`verified_streak_tail`/finish 自洽不受影响）**实现与文档一致**，除上述文本解析缺陷外，窗口边界本身打不穿（A2/A3/A4a/A5 全按预期）。

## §2 两侧并排（全部既有账本）

命令：`python scratch/_t86_side.py --days 3`（78 本 = `scratch/*.jsonl` + `logs/*.jsonl`，逐本跑冻结的旧/新工具，`--json` 落 `scratch/_t86_json/`）。原始表：`scratch/_t86_side_d3.txt`（另有 `_d1/_d2/_d5`）。

| 账本 | 旧 rc | 新 rc | 旧问题 | 新问题 | history | streak | 旧判定 | 新判定 |
|---|---|---|---|---|---|---|---|---|
| `logs/longrun-3day-llm-run7.jsonl` | 1 | **0** | 9 | 0 | **9** | 3 | needs_review | **VERIFIED** |
| 其余 77 本 | — | — | — | — | 0 | — | — | **逐字不变** |

- 特别核对"看似该变却没变"的：`scratch/journal-green-bad.jsonl`（9 问题、streak 3）、`scratch/_t5x_vacuum.jsonl`（3 问题、streak 3）、`scratch/review-neg-B/C/D/E/F/H/J`（各 3 问题、streak 3）⇒ 全部仍 rc=1：因为它们的**整本账本就是那 3 天窗口**，问题落在窗口内 ⇒ 正确地不降级。
- `--days 1` / `--days 2`：同样只有 run7 改变（窗口取 `days[-streak:]`，即 3 天）。`--days 5`：**零本改变**（run7 `streak(3) < 5` ⇒ 不降级）⇒ "窗口没打满维持原判"实测成立。
- run7 读数：1230 行 / 7 天 / `finish{code:0, verified_streak:3, actions:683, minutes:25.2}`；尾部 summer 7/8/9；9 条 history = summer 3（2 条）+ summer 5（2 条）+ summer 6（5 条），原文：

```
历史问题（达标窗口之外的日子，不影响结论，共 9 条）：
  - [summer 3] checks.watered_outdoor=false（睡前还有没浇的作物）
  - [summer 3] day_end verified=false
  - [summer 5] checks.watered_outdoor=false（睡前还有没浇的作物）
  - [summer 5] day_end verified=false
  - [summer 6] ended_by=stuck（不是我们主动睡过去的）
  - [summer 6] checks.watered_outdoor=false（睡前还有没浇的作物）
  - [summer 6] 睡前 unwatered_crops=1（窗口口径，要求 0）
  - [summer 6] checks.crops_watered=false（窗口口径，睡前还有没浇的作物）
  - [summer 6] day_end verified=false
结论：VERIFIED
```

## §3 对抗矩阵（我自造账本，`scratch/_t86_adv.py` → `scratch/review-t86-*.jsonl`）

| # | 构造 | 旧 rc | 新 rc | 新判定 | 说明 |
|---|---|---|---|---|---|
| A1 | 尾部 3 天全绿 + 前 5 天全坏（浇水没做完） | 1 | **0** | VERIFIED（25 条 history） | 设计允许；"过的是最后 3 天"，坏日逐条列出、未被抹掉 |
| A6 | 27 天全坏 + 尾部 3 天全绿（同因系统性缺陷） | 1 | **0** | VERIFIED（**135 条** history） | **侵蚀实证**：窗口外系统性缺陷不影响结论（§1 理由 2） |
| A2 | 窗口内中间日"账目自相矛盾"（`verified=true` + 谎报 `no_unmet_stages`，stage `leftover=5`） | 1 | **1** | needs_review | 窗口内问题仍 fatal ✅ |
| A3 | run 停在坏的一天（尾部一天 `verified=false`） | 1 | **1** | needs_review（streak 0、history 0） | 窗口没打满 ⇒ 不降级 ✅ |
| A4a | 3 天账本，中间日同 A2（**正常** day 标签） | 1 | **1** | needs_review | 对照组 ✅ |
| A4b | 同 A4a，只把中间日 `day_start.day[1]` 改成 `spring]x` | 1 | **0** | **VERIFIED** | **打穿（要求 ④）** |
| A5 | A1 的 8 天 + 早期一条 `bridge_down` 事件（全局问题） | 1 | **1** | needs_review（25 条日级降级、全局那条保留） | 全局问题永不降级 ✅ |

### A4a / A4b 原文对照

```
===== a4a-inwindow-contradiction-normal-key =====
旧 rc=1 问题 ["[spring 11] checks.no_unmet_stages=True 与自算不一致（有目标阶段遗留 leftover=5 格，
          扣掉不可达豁免 0 + 锄不动豁免 0 后剩 5 格、当天成功动作 32；期望 False）"]
新 rc=1 verdict=needs_review streak=3
新 问题 [同上一条]        新 历史 []

===== a4b-inwindow-contradiction-injected-key =====
旧 rc=1 问题 ["[spring]x 11] checks.no_unmet_stages=True 与自算不一致（…剩 5 格…；期望 False）"]
新 rc=0 verdict=VERIFIED streak=3
新 问题 []                新 历史 ["[spring]x 11] checks.no_unmet_stages=True 与自算不一致（…）"]
```

**根因（`tools/verify-run3.py`）**：`report()` 的窗口过滤用**文本前缀解析**日标签 —— `history_problems` 判定处 `:914-916` 的 `head = p[1:].split("]", 1)[0]`；而标签本身由 `day_key()`（`:85-96`）从**账本原文** `f"{day[1]} {day[2]}"` 拼成、未做净化，`name = d["key"]`（`:362`）。因此账本里任何含 `]` 的 season/day 都会让 head 截断成 `spring`，与 `tail_names` 不匹配 ⇒ 该日问题被降级。注意该日的 `day_start`/`day_end` 配对、`cross_day`（`day_after` 存在且 key 不同）、`verified` 全部照旧成立 ⇒ 它**确实在尾部 streak 里**，只是问题认不出它。

## §4 口径一致性

- `docs/_run6-criteria.md` §2 新增段与实现逐句对得上：窗口 = 尾部连续 N 天；窗口外 → `history_problems`（逐条列出、不影响结论）；`streak < --days` 不降级；run 必须停在窗口上。
- `verified_streak_tail`：`:894-899` 在降级**之前**计算 ⇒ 不受影响 ✅（A3 实证 streak=0、A4b streak=3）。
- finish 自洽：`:996-1027` 在降级**之后**追加，问题文本**无 `[day]` 前缀** ⇒ 结构上不可能被降级 ✅（A5 实证：25 条日级降级、`bridge_down` 全局问题保留 ⇒ rc 1）。
- `--json` 新增 `history_problems` 字段 ✅（键表已核：`['bad_lines','days',…,'history_problems','infos',…,'problems',…,'verdict','verified_streak_tail']`）。
- `tests.test_verify_run3`：**Ran 44 / OK**；`7c4ff68` 新增 2 条具名用例 `test_early_bad_day_does_not_invalidate_the_tail_streak`、`test_run_ending_on_a_bad_day_is_still_not_ok` —— 两条都是**放宽方向**的守卫（早坏日不拖累尾部；尾部坏日仍红）。**没有**用例覆盖"窗口内问题必须仍 fatal"或"NIT-1 的标签注入"⇒ 与 §3 的打穿一致（测试缺口，NIT-4）。
- 与 `tools/analyze-longrun.py`：该工具**仍按整本账本**判红（run7：`VERIFIED: 4/3 天`、`退出码 1；有红 138 条`、原文"判决权威仍是 tools\verify-run3.py"；A6 上它也照旧逐日列出所有问题）⇒ 两工具结论**反向是刻意口径差异**，但发布物里必须注明口径，否则看起来自相矛盾（NIT-3）。

## §5 三源对账 run7（只读）

工具：`scratch/_t45_three_source.py`；SMAPI 源 = `%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`（630353 B / 8533 行 / mtime `2026-10-14 23:33:13`，**仍是 run7 会话**，之后无新会话）；为防覆盖我在 `scratch/` 存了只读副本 `scratch/_t86_smapi_run7_live.txt`（sha256 `0782B2A19AB28C31B21821F35075D027C77A91A41DE98EC442CF3F4242E06EF1`）；存档 = `Saves\Wahaha_450799035`。

- ✅ 账本 6 次跨日全部恰好 +1：summer 3→4、4→5、5→6、7→8、8→9、9→10；其中 5 次与 SMAPI `Synchronizing 'NewDay' task` 逐条配对（`23:00:00` / `23:01:11` / `23:06:57` / `23:10:57` / `23:15:42` / `23:17:00`，每条都有 `SaveGame.Save() completed`）；summer 6 是 `ended_by=stuck` 翻篇 ⇒ 不要求 NewDay（info）。
- ✅ 存档主文件前进：`Wahaha_450799035` 3648782 B @ `23:33:11.539`（对比 `_old` 3614652 B @ `23:18:27`）；存档 XML 真值 `[1,'summer',11]`、`money=14`。
- ⚠️ 1 条 problem：**"存档比账本收尾还新 1 天（存档 summer 11 / 账本 summer 10）"**。原因已定位，**不是账本造假**：SMAPI 在 `23:18:27`（L8513/L8521）与 `23:33:11`（L8525/L8532）还各有一次 NewDay+Save，而 run7 的 journal 在 `23:18:29` 就停了（`finish` 之后再无写入）⇒ 收工后游戏又走了 2 天并落盘。属"跑批窗口比游戏会话短"的必然结果；建议 run 收工时先退出游戏，或把"存档比 `finish` 还新"降级为 info（NIT-5）。
- 无 run7 的 start/end 外部快照（`scratch/` 只有 run4/5/6）⇒ 窗口 delta 未判（info）；已用存档链（`_old` → 主存档 size/mtime 前进）补一侧证据。
- 请求：若要长期复核，请 machine-runner 把该会话冻结成 `logs/run7-smapi-window.txt`（我只读副本在 `scratch/`，按 gitignore 不入库）。

## §6 NIT / 建议

| # | 内容 | 位置 | 是否阻塞 |
|---|---|---|---|
| NIT-1 | **打穿通道**：窗口过滤靠解析文本前缀，标签未净化。建议不再解析文本——建问题时带结构化 day key（`(key, text)`）或对 `day_key` 净化并校验（含 `]`/换行 ⇒ 判问题"账本 day 字段非法"）；补一条"窗口内问题 + 含 `]` 的标签 ⇒ 仍 fatal"用例 | `tools/verify-run3.py:914-916`（配 `:85-96`、`:362`） | **是（否则本卡 FAIL）** |
| NIT-2 | 窗口外系统性缺陷被放过（A6：1 天窗口干净即 VERIFIED，135 条 history）。若要保留该口径，请在 `docs/_run6-criteria.md` §2 与发布清单写死"验收只覆盖尾部 N 天、更早缺陷靠三源对账/人工"；否则给历史问题加门槛（数量/同因 ⇒ 至少不判 VERIFIED） | 口径文档 + `tools/verify-run3.py:911-919` | 需 Lead 明示 |
| NIT-3 | `analyze-longrun.py`（整本）与 `verify-run3.py`（窗口）结论反向；建议 `--json` 加 `caliber:"tail_window"` 或在输出头注明 | 两工具输出 | 否 |
| NIT-4 | 新用例只覆盖放宽方向，缺"窗口内必须 fatal"（与 NIT-1 同源）；`history_problems` 标签同源未净化 | `tests/test_verify_run3.py:702-735` | 否（NIT-1 修时一并补） |
| NIT-5 | "存档比账本新"在三源对账里判 problem，但"收工后游戏继续走"是常见情形 ⇒ 建议有 `finish` 时降 info 并注明 | `scratch/_t45_three_source.py`（我自己的工具） | 否 |

## §7 复现命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
# 先冻结两侧工具（生成 scratch/_t86_tool_old.py / _t86_tool_new.py）
& $py scratch\_t86_freeze.py
# 两侧并排（78 本）
& $py scratch\_t86_side.py --days 3      # → scratch\_t86_side_d3.txt
& $py scratch\_t86_side.py --days 5      # 零本改变
# 对抗矩阵（A1/A2/A3/A4a/A4b/A5/A6）
& $py scratch\_t86_adv.py                # → scratch\_t86_adv_out.txt
# 单侧复核 A4b
& $py scratch\_t86_tool_old.py --journal scratch\review-t86-a4b-inwindow-contradiction-injected-key.jsonl --days 3   # rc 1（旧口径）
& $py scratch\_t86_tool_new.py --journal scratch\review-t86-a4b-inwindow-contradiction-injected-key.jsonl --days 3   # rc 0 / VERIFIED
# 三源对账 run7
& $py scratch\_t45_three_source.py --ledger logs\longrun-3day-llm-run7.jsonl --smapi scratch\_t86_smapi_run7_live.txt --date 2026-10-14 --snapshots scratch\_t86_no_such_snapshots.jsonl --baseline logs\run7-baseline.json
# 工具单测
python -m unittest tests.test_verify_run3      # Ran 44 / OK
```

结论：**FAIL**（NIT-1 是可复现的降级通道；NIT-2 是口径层面的系统性放过，需要 Lead 明示取舍）。修 NIT-1 后本报告 §1 理由 1 可关闭，理由 2 仍需口径决策。
