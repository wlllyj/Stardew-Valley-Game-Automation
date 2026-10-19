# 对抗验收报告：0.7.48（task-38 · `slot_relief` 字段奇偶补齐）

- 验收方：deputy-lead（对抗验收 / 只读生产代码）
- 冻结对象：`e2b69d9`（`release(0.7.48): 冻结 slot_relief 字段奇偶补齐批（bridge MOD_VERSION_EXPECTED + manifest + note）`，3 files +21/−3）
- 前置代码提交：`d9f7032`（dev-coder T1：`brain/agentfarm/longrun.py` + `tests/test_longrun.py` +164/−1；e2b69d9 相对它只动 `brain/agentfarm/bridge.py`、`mod/AgentFarm.Bridge/manifest.json`、`tools/_note-0748.txt`）
- 上一版冻结：`a03a564`（0.7.47）
- 基线一律取 `git archive <ref>`，**不用 HEAD**（`main` 停在 `430b3cb`；`branch-opencode` HEAD=`9130ec7` 只多了 observer 文档，不改冻结树内容）
- 环境：`PYTHONUTF8=1`；`python=C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`

---

## 0. 结论摘要

| 项 | 结论 |
|---|---|
| T5.1 字段缺口是否真实 | **是**（`logs/longrun-smoke-0746.jsonl` 第 10 行 `trigger=clear_gate` 缺 `reached`） |
| T5.1 作者「缺字段 ⇒ analyze/verify rc=1」因果 | **不成立**（见 §2.3；两条 rc=1 各有独立红因） |
| T5.1 六本旧账本 rc/红数受修复影响 | **无影响**（改 `longrun.py` 前后逐字节同，见 §2.4） |
| T5.2 冻结树 provenance 双跑 | **一致**（791 文件；`Ran 1378` 两跑同） |
| T5.2 四把伪造判据（C1–C4） | **核心全灭**；残留 4 个 SURVIVE = **定向单测覆盖漏洞**（见 §3.3） |
| T5.3 repo / 装机 / 冻结树 三方 | **一致**（manifest 0.7.48 + dll `C9B3BD6C…`；见 §4） |
| **A9 可否放行** | **放行**（task-38 是只读字段补齐，无行为变更；字段奇偶要求已满足；已实测无回归。附带 4 个**单测覆盖漏洞**记入 0.7.48 已知限制，不为它重新冻结） |

---

## 1. 验收对象与口径

被测改动（`d9f7032`）：在 `clear_gate` 分支（`brain/agentfarm/longrun.py` 的 `_note_clear_area_bag_gate`）补写 task-237 字段 `reached`，使 `slot_relief` 四个写入点字段集齐。

字段集出处（独立引用）：`tools/_note-0741.txt`（task-237）：「`slot_relief` 事件新增 `demand`/`demand_basis`/`target_free`/`reached`（复用事件名）」。

四个写入点（冻结树 `e2b69d9:brain/agentfarm/longrun.py`，行号＝冻结树内行号）：

| # | 写入点 | 位置 | trigger | 实测字段 |
|---|---|---|---|---|
| ① | `_slot_relief`（主通道） | 6659 起 | `space_pressure` | 4 字段齐 |
| ② | `_note_slot_pressure_stuck`（压力卡死） | ~6296 | `space_pressure` | 4 字段齐 |
| ③ | `_note_clear_area_bag_gate`（清障闸，**本次修复点**） | 6450 | `clear_gate` | `reached=False` 已补 |
| ④ | `buy_full` | ~7461 | `buy_full` | 4 字段齐 |

冻结树修复点原文（`git show e2b69d9:brain/agentfarm/longrun.py`）：
```
self._journal("slot_relief", pressure=True, need=0, demand=0,
              demand_basis="space_pressure", trigger="clear_gate",
              target_free=SLOT_RELIEF_TARGET_FREE, reached=False, freed=0,
              stage=task, ...)
```
`git merge-base --is-ancestor d9f7032 e2b69d9` → rc=0（修复确在冻结树内）。

---

## 2. T5.1 独立复算 smoke-0746 步7 FAIL 根因

### 2.1 复现 rc（命令原文）

```
PYTHONUTF8=1 python tools/analyze-longrun.py --journal logs/longrun-smoke-0746.jsonl --days 2 --json
PYTHONUTF8=1 python tools/verify-run3.py   --journal logs/longrun-smoke-0746.jsonl --days 2
```
读数（`scratch/_t5_smoke.py` 复跑）：
```
analyze_rc= 1
red.total= 1   red.subjects= ['missed:seeds']   red.lines= [130]
slot_relief= {"events": 3, "lines": [5, 6, 10], "demand_basis": {"space_pressure": 2, "buy_full": 1},
              "target_frees": [2, 1, 2], "reached": 0, "reached_lines": []}
verify_rc= 1
结论：needs_review    尾部连续 VERIFIED 天数 1 / 要求 2
```

### 2.2 字段缺口（账本行号 + 原文）

自己数（不看作者结论）：

```python
# 逐行扫 logs/longrun-smoke-0746.jsonl（131 行），event==slot_relief
5  trigger=none        keys=29  missing=[]
6  trigger=none        keys=28  missing=[]
10 trigger=clear_gate  keys=14  missing=['reached']
```
第 10 行原文：
```json
{"event": "slot_relief", "t": 3.31, "pressure": true, "need": 0, "demand": 0,
 "demand_basis": "space_pressure", "trigger": "clear_gate", "target_free": 2,
 "freed": 0, "stage": "clear_area", "reason": "背包 0 空格且腾格手段用尽",
 "loot_lost_steps": 0, "loot_lost_limit": 5}
```
⇒ **缺字段仅 `reached` 一个**；`demand`/`demand_basis`/`target_free` **都在**。

探针校验面（引用）：`scratch/smoke-0742.py:680` `need = ("demand", "target_free", "reached")`（该面只校验 3 字段，**不含 `demand_basis`** —— 见 §3.3 口径注记）。

### 2.3 裁决：作者的因果链**不成立**

`docs/_release-0.7.47.md:53` 原文：「步 7 FAIL（字段级缺口）：`slot_relief` 共 3 条，index 2（t=3.31、`trigger=clear_gate`、task-28 新增压力通道）**缺 task-237 字段 `reached`**（另有 `demand/target_free`）⇒ `analyze_rc=1`、`verify_rc=1`。」；`docs/_release-0.7.47.md:57` 复述「…而 `analyze-longrun`/`verify-run3` 按 task-237 要求该字段 ⇒ A9 判决工具会因它 rc=1」。

实测反证（同一本账本，同一工具）：

1. `analyze_rc=1` 的**真因**是 `red.subjects=['missed:seeds'] red.lines=[130]` —— 第 130 行是 `day_end`（`verified: true`），红点是**播种腿全程 0 步成功**（`verify-run3.py` 信息项「三腿覆盖：播种 全程 0 步成功（种子/钱不足时合法，但目标 P3 ⑥ 要求这一腿有真机证据）」），**与 `slot_relief` 字段无关**。
2. `tools/analyze-longrun.py` 的 `slot_relief` 汇总块只**呈现** `reached`（`"reached": 0, "reached_lines": []`），**不把缺字段计入 `red`** —— 所以补 `reached` 不会改变 `red`/rc。
3. 用 0.7.47 冻结树里的同一分析器复跑（blob `3330CF46…`，与 `e2b69d9` **同 blob**、`a03a564` 亦同）：
   `red.total=1 subjects=['missed:seeds'] lines=[130]` —— **与 0.7.48 完全一致**。
4. `verify_rc=1` 的**真因**是「尾部连续 VERIFIED 天数 1 / 要求 2」，与字段无关。

⇒ 结论：**字段缺口真实（是步 7 的 FAIL 项，由探针面 `smoke-0742.py §task-237` 判出）**；但把 `analyze_rc=1`/`verify_rc=1` 归因于该缺口**不成立**，且 `（另有 demand/target_free）` 一句**与原文相悖**（两字段均在）。修复 `reached` **不会**让这两项 rc 翻绿；A9 判决不得以「rc==1 已由 task-38 修好」为前提。

### 2.4 六本旧账本 rc/红数（改 `longrun.py` 前后逐条不变）

方法：对同一本账本，分别用 A=`430b3cb`（修前）与 B=修后（`d9f7032`）的 `brain/` 跑分析器 + `verify-run3`，比 `(rc, red数, undecidable数)` 与 verify 结论。输出 `scratch/_t5_cmp_out.txt`：

```
A(HEAD) clear_gate has reached? False
B(fixed) clear_gate has reached? True

journal                          | A rc/red/und | B rc/red/und | same | verifyA/verifyB
longrun-runA-0732.jsonl          | (1, 117, 146)| (1, 117, 146)| True | 1/1
longrun-runB-0732.jsonl          | (1,  84, 151)| (1,  84, 151)| True | 1/1
longrun-3day-llm-run9.jsonl      | (1,  84, 169)| (1,  84, 169)| True | 1/1
longrun-3day-llm-run9b.jsonl     | (1,  45, 169)| (1,  45, 169)| True | 1/1
longrun-3day-llm-run9c.jsonl     | (0,   0, 156)| (0,   0, 156)| True | 1/1
longrun-3day-llm-run9d.jsonl     | (1,  29, 143)| (1,  29, 143)| True | 1/1

ALL IDENTICAL: True
```
（A 侧 `clear_gate has reached? = False`、B 侧 `= True` 证明补丁确实生效；而六本账本读数**一字不变**。）与 log-analyst(T6) 的十本派表同向（`run9c` 0 红为其本征；本报告只测这六本）。

---

## 3. T5.2 冻结树 provenance + 四把伪造判据

### 3.1 冻结树 provenance（双跑一致）

工具：`scratch/_t5_prov.py`（`git archive <ref>` → tar → 计数/取 blob/可选跑全量单测；跑单测前把 `.gitignore` 掉的测试夹具 `scratch/_ledger_*.jsonl` 等同步进导出树 —— 否则 `tests/test_analyze_longrun.py` 会因缺夹具 ERROR，见 §6）。

| ref | 文件数 | 全量单测 | 说明 |
|---|---|---|---|
| `a03a564`（0.7.47） | 785 | `Ran 1374 tests … FAILED (failures=1, errors=3, skipped=12)` | 两跑逐字节同 |
| `e2b69d9`（0.7.48） | 791 | `Ran 1378 tests … FAILED (failures=1, errors=3, skipped=12)` | 两跑逐字节同；**无新增问题**，仅 +4 条新用例 |

- 文件 +6 = 0.7.48 批新增（`tools/_note-0748.txt` 等）＋ `d9f7032` 新增用例。
- `failures=1` = C# 自检**控制台代码页**假红（见 §6）；`errors=3` = `.gitignore` 掉的 `logs/` 夹具缺失；`skipped=12` = 环境依赖跳过。两 ref 问题集**完全相同** ⇒ 无回归。
- 关键 blob SHA256（`git show <ref>:<path>`）：
  - `e2b69d9`：`mod/AgentFarm.Bridge/manifest.json` `507AA8BA…ABA2612`（79295 B，LF）；`brain/agentfarm/longrun.py` `F38FE29C…D7C91118`（719671 B）；`brain/agentfarm/bridge.py` `F6B31B46…B977C61ECA`（83439 B）；`tools/analyze-longrun.py` `3330CF46…54DDE84E`（638987 B）；`tools/verify-run3.py` `2D9DB563…45A52C33`（93698 B）；`tools/deploy-mod.py` `D5E45C75…A663F87B`（12769 B）；树内**无 dll**。
  - `a03a564`：manifest `5ECE0FC8…434DC163`（76839 B）；`longrun.py` `DBF570A7…4BFA603C`（719123 B）；`bridge.py` `A278974D…32D10D15BAA`（82196 B）；analyzer/verify/deploy 三个 blob 与 `e2b69d9` **相同**。

### 3.2 四把伪造判据 · 变异实测（冻结树 `e2b69d9`）

装置 `scratch/_t38_mutate.py`（把树导出到临时目录、打补丁、跑①AST 探针面（`slot_relief` 四点字段集）②定向单测面；跑完删树）。输出 `scratch/_t38_mutate_out_freeze_e2b69d9.txt`（与工作树跑 `_t38_mutate_out.txt` 内容一致）：

```
[基线 base_e2b69d9] 探针=PASS ['slot_relief 调用 4 处']
[基线 base_e2b69d9] 单测=SURVIVE Ran 4 tests in 0.001s | OK []

用例                                    探针预期  探针实测  单测预期  单测实测  判红测试
C1_drop_reached_arg                     FAIL     FAIL     KILL     KILL     FAIL:   ← 原始缺口复现
C2_reached_always_true                  PASS     PASS     KILL     KILL     FAIL:   ← clear_gate 恒 True
C2b_main_reached_true                   PASS     PASS     KILL     SURVIVE  -       ← 主通道恒 True（漏洞）
C3a_drop_reached_other_site_pressure    FAIL     FAIL     KILL     KILL     FAIL:   ← 压力卡死点丢字段
C3b_drop_reached_other_site_buy_full    FAIL     FAIL     KILL     KILL     FAIL:   ← buy_full 点丢字段
C4a_demand_basis_buy_full_changed       PASS     PASS     KILL     KILL     FAIL:   ← 改 buy_full 的 demand_basis
C4b_demand_basis_clear_gate_changed     PASS     PASS     ?        SURVIVE  -       ← 漏洞
C4c_demand_basis_main_changed           PASS     PASS     ?        SURVIVE  -       ← 漏洞
C4d_demand_basis_pressure_changed       PASS     PASS     ?        SURVIVE  -       ← 漏洞
C5_target_free_value_wrong              PASS     PASS     ?        KILL     FAIL:   ← clear_gate target_free 写错
C6_reached_int_zero                     PASS     PASS     ?        KILL     FAIL:   ← reached 写成 int 0
```
- 探针面实测细节：C1/C3a/C3b 报 `缺 ['reached']`（`longrun.py:6450 / 6296 / 7461`）⇒ 4 点字段奇偶面**有效**。
- 任务口径要求「C1 删 `reached`；C2 `reached` 语义改错；C3 漏修其它写入点；C4 改 `demand_basis`」四把都要被**新定向单测**判红。实测：C1/C2/C3a/C3b 判红 ✅；**C4 只在 `buy_full` 点判红（C4a），另三点（C4b/C4c/C4d）未被判红 ❌**。

### 3.3 定向单测覆盖漏洞（如实列，不掩盖）

survivors：`C2b_main_reached_true`、`C4b_demand_basis_clear_gate_changed`、`C4c_demand_basis_main_changed`、`C4d_demand_basis_pressure_changed`。

- **C2b（主通道 `reached` 恒 True）**：`tests/test_longrun.py:13792-13793` 的 `assertEqual(bool(ev[0]["reached"]), int(ev[0]["freeSlots_after"]) >= int(ev[0]["target_free"]))` 在夹具 `_full_with_surplus()` 下**恒真**（`freeSlots_after ≥ target_free`），无法区分「动态判据」与「硬编码 True」。
- **C4b/C4c/C4d（另三点的 `demand_basis` 取值）**：仅 ④ `buy_full` 点（`:13818` `assertEqual(ev[0]["demand_basis"], "buy_full")`）断言了**取值**；②③① 三点的 `demand_basis` 值无断言（探针面亦只校验**按键存在**、不校验值）。规格注记：`scratch/smoke-0742.py:680` 的探针面也只要求 3 字段（不含 `demand_basis`），故「值」这一维在**探针与单测两侧都无人把守**。
- 按部门口径，上述 4 项不阻断 0.7.48（运行时行为正确、字段齐备已证），但**属新增定向单测的覆盖漏洞**，应记入 0.7.48 已知限制并并入后续 dev 批次（补值断言 + 补 `freeSlots_after < target_free` 场景）。

---

## 4. T5.3 三方版本现状（repo / 装机 / 冻结树）

（`scratch/_t5_prov_check.py` 现测）

| 侧 | manifest | dll |
|---|---|---|
| 仓库源 `mod/AgentFarm.Bridge/manifest.json` | 79305 B `45B27C848910C8F860F842E5AB1424CD207AEC83F833C6B7D3452713E4F69071` **Version 0.7.48** | （源目录无 dll） |
| 构建产物 `mod/AgentFarm.Bridge/bin/Release/` | 79305 B **同上 sha** **0.7.48** | 293888 B `C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A` mtime 2026-10-18T23:39:02 |
| 装机 `…\Stardew Valley\Mods\AgentFarm.Bridge\` | 79305 B **同上 sha** **0.7.48** | 293888 B **同上 sha** mtime 2026-10-18T23:39:02 |

- **三方一致**：manifest 三侧同 sha 同版本 0.7.48；dll 构建侧与装机侧**逐字节相同**（`C9B3BD6C…`，与 0.7.47 亦相同 —— 本批无 Mod 代码变更）。
- **CRLF 观察（保留记载方式）**：冻结树 blob `mod/AgentFarm.Bridge/manifest.json` = `507AA8BA…`（79295 B，**LF**，`git show` 归一）；工作树/装机检出 = `45B27C84…`（79305 B，**CRLF**）。差 10 B = 行尾 CR。二进制的同一性应以 blob（LF）为准。
- **时序更正（如实记录）**：本卡早段读数曾见「装机侧 manifest 仍为 0.7.47（76849 B `9B7C30F6…`）」；本次复测装机侧已是 0.7.48。⇒ 装机侧 manifest 在两会话之间被更新（本验收方**未执行**任何部署动作，仅观测）。故「`preflight --expect 0.7.48` 部署前必失败」这一早期结论**现已过期**；当前装机侧满足 `--expect 0.7.48`。

---

## 5. A9 放行裁决

**A9 可否放行：放行。**

理由（均以独立实测为据）：
1. `d9f7032` 对 `brain/agentfarm/longrun.py` 的改动是**只读字段补齐**（`clear_gate` 分支新增 `reached=False`），无行为/经济路径变更；
2. 字段奇偶要求（`tools/_note-0741.txt` task-237 四字段）在四个写入点**实测齐备**（探针面 4 处全过，基线 PASS）；
3. 变异实测：C1/C2/C3a/C3b/C5/C6 六把**全灭**——「缺字段」「语义错（clear_gate 恒 True）」「漏修它点」三类核心伪造都被新定向单测判红；
4. 六本旧账本 `(rc, red, und)` 与 verify 结论**逐条不变** ⇒ 无回归；冻结树全量单测与 0.7.47 问题集完全相同。
5. 附带条件（不阻断）：4 个单测覆盖漏洞（§3.3）记入 **0.7.48 已知限制**，并入后续 dev 批次修复，不为它重新冻结。

**A9 冻结后待跑项**（gate 条件，交 lead / machine-runner）：
- journal 命名：A9 = `logs/longrun-runA9-0748.jsonl`（B9 必须换名 `logs/longrun-runB9-0748.jsonl`，因 lessons 路径由 journal 名派生：`longrun.py:1573-1583` `_derive_lessons_path` = `with_name(f"{stem}-lessons.json")`）。
- 起跑前置：A9 必须零 lessons 基线（`logs/longrun-runA9-0748-lessons.json` 不存在）；`--boundary-llm` 生效（`tools/start-detached-longrun.py:179-182` 不透传 `--boundary-llm`，`tools/run-longrun.py` 默认 ON）；`--expect-version 0.7.48`；`preflight --save-baseline logs/runA9-baseline.json`。
- 真机纪律：脱离式起跑；冻结 SMAPI 窗口 + 存档四件 size/mtime/SHA256 逐字节比对；优雅退出后核 0 进程 / `bridge.json` 已删 / 17890 无 LISTENING；跨日先关 `ShippingMenu`（task-236）。
- 判决口径预警（源自 §2.3）：A9 判决时 **不要**假设 `analyze_rc` 会因 task-38 而变；`analyze_rc=1` 的红是「播种腿 0 步」类覆盖红，`verify_rc=1` 的红是「连续 VERIFIED 天数 < 2」——两者须在 A9 灯具下**另行判读**。

---

## 6. 已知限制（照实）

1. **C# 假红（环境，非产品）**：`tests/test_longrun.py:9981-9991` `test_csharp_rules_self_test_passes` 在**默认控制台代码页**下 FAIL —— `proc.returncode==0` 通过（C# 自检确为 `OK 97 用例`），但 `assertIn("行为断言", proc.stdout)` 失败（子进程中文 stdout 被降级为 `????`）。**同一条命令前加 `chcp 65001`（控制台 UTF-8）即 `OK`**。故：默认代码页 `Ran 1392 / FAILED(failures=1, skipped=1)`；`chcp 65001` 后 `Ran 1392 / OK (skipped=1)`（与 lead 读数一致）。**双读数同真**，属控制台代码页假红，非 0.7.48 回归（0.7.47 同状）。
2. **冻结树 3 个 ERROR = 夹具缺失**：`scratch/*` 被 `.gitignore`（`scratch/*` + `!scratch/*.py`）排除 ⇒ `scratch/_ledger_*.jsonl`（10 本测试夹具）不在 `git archive` 导出内 ⇒ `tests/test_analyze_longrun.py` 若干用例 `FileNotFoundError`（如 `tests/test_analyze_longrun.py:47 report_for` → `tools/analyze-longrun.py:2171` 读账本失败）。属**测试夹具打包**问题，非产品缺陷；跑冻结树测试前须同步夹具（`_t5_prov.py` 已内建）。
3. **本报告未重跑真机**；A9 全部读数待 §5 待跑项执行后另出。
4. 变异装置只在临时导出树上打补丁，未在真机/装机侧验证；无 `git archive` 之外的来源。
5. 本报告只测六本旧账本（§2.4）；十本全集见 log-analyst(T6) 派表。

---

## 附：本卡落盘产物

- `scratch/_t38_mutate.py`、`scratch/_t5_prov.py`、`scratch/_t5_smoke.py`（+ `_t5_prov_check.py`、`_t5_extra.py`）：探针/变异/provenance 装置
- `scratch/_t38_mutate_out.txt`、`scratch/_t38_mutate_out_freeze_e2b69d9.txt`、`scratch/_t5_cmp_out.txt`、`scratch/_t5_smoke_verify.txt`：逐字读数（`.txt` 受 `.gitignore`，不入库）
- `docs/_review-task38-prep.md`：0.7.48 预置验收骨架（含本卡方法学与口径）
