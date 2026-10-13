# task-19 在制品独立验收（deputy-lead / task-35）

判定：**PASS-WITH-NITS**（六条验收条款全部成立；1 条建议提交前修的潜伏缺陷 + 3 条可见性/覆盖度 NIT，均不阻塞 run3 前置）

日期：2026-10-13 傍晚 · 验收对象 = **未提交在制品**（不是 HEAD）· 只读源码，只写 `docs\_review-task19.md` + `scratch\`

---

## §1 验收对象与基线（全部我亲跑）

| 项 | 读数 |
| --- | --- |
| `git status --short` | ` M brain/agentfarm/longrun.py`、` M tests/test_longrun.py`（另 `?? scratch/_probe_save_bed.py`、`?? scratch/_probe_save_raw.py` 非本任务）；`mod/`、`farmwork.py`、`tools/`、`docs/00-开发日志.md`、`logs/` 均未动 |
| `git diff --stat` | longrun.py **+143**、test_longrun.py **+151**（291 insertions / 3 deletions） |
| HEAD | 开验时 `d2fe2ed`；期间 Lead 提交 **`4b3addf`**（task-29，只碰 README + `__main__.py` + `test_main_pid_gate.py`）⇒ **未触碰这两个文件**，快照有效性不受影响 |
| SHA256 前 12 | longrun.py **331dedede388** / 120754 B / mtime 10-13 01:26:54；test_longrun.py **f27b12950f11** / 105273 B / 01:27:41（`4b3addf` 之后复算**不变** ⇒ 无并发修改） |
| `py_compile` | `brain\agentfarm\longrun.py` + `farmwork.py` ⇒ **exit 0** |
| 全量单测 | `unittest discover -s tests` ⇒ **Ran 293 tests / OK**（开验时为 **Ran 290 / OK**，差额 3 条即 task-29 新增；两个读数都在本冻结快照上） |
| 浇水用例 | `discover -s tests -p test_longrun.py -k Task19 -v` ⇒ **Ran 6 tests / OK** |
| 未 bump | manifest 与 `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED` 仍 **0.7.22**，本次在制不改版本 |

探针与产物（`scratch\`）：`_t35_probe.py`（直接调用产线 `_water_evidence` + 改 green 账本造 3 本破坏性账本 + 真跑一天）、`review-t19-B1-window-dry.jsonl`、`review-t19-B2-farm-dry.jsonl`、`review-t19-B3-empty-window-true.jsonl`、`_t35_unittest.txt`。

---

## §2 六条验收条款逐条

### ① `checks.watered_outdoor` 双口径 —— 成立
- 实现：`brain/agentfarm/longrun.py:529-597 _water_evidence()`。
- farm 口径闸门 `:556-557`：`farm.get("complete") is True and farm.get("loaded") is not False and farm.get("dryCrops") is not None` ⇒ `dry = int(farm.dryCrops or 0)`、`return dry == 0`（`:558-574`）。
- 窗口口径 `:585-597`：`win = FarmWorker.tiles_of(outdoor_obs)`（`farmwork.py:492-499`）、`crops_t = [t for t,v in win.items() if v.get("crop")]`、`dry_t = [t for t in crops_t if not win[t].get("watered")]` ⇒ `return len(dry_t) == 0`。
- 无户外快照 `:575-584` ⇒ **False**（`tiles=0, crops=0, dry=None` + note 明示"禁止默认 true"）。
- 我的实测：A1（室内末快照 + 户外有未浇作物）⇒ `False, scope=window, (tiles,crops,dry)=(1,1,1)`；A2（全浇）⇒ `True, (1,1,0)`；A6（旧 Mod 无 dryCrops）⇒ `False, window, (1,1,1)`。见 §3。

### ② `final_water` 六键 + scope 语义 —— 成立
- 六键 `t / location / tiles / crops / dry / scope`（farm 分支 `:561-567`、无快照分支 `:576-583`、窗口分支 `:588-594`），另加 `note` 说明证据来源（farm 分支注明 `tiles=farm.hoeDirt`、`crops=farm.crops`、`farm.unwateredCrops` 不是干格数；window 分支注明覆盖多少格）。
- `scope ∈ {"farm","window"}`；`day_end.final_water` 在**顶层**输出（`DayReport.as_dict` `:281-283`），与 `final`（窗口口径）分开的理由写在 `:240` 注释（"≤400 格、以玩家为中心、室内恒 0，两套仪器不许同列"）。
- 我的实测 JSON 逐键打印见 §3 A1/A4；作者用例⑥ `assertNotIn("unwateredCrops", fw)`（`tests/test_longrun.py:2001`）把"不许混列"钉死了。

### ③ 两套计数分名、`crops_watered` 降为旁证 —— 成立
- `_essence` 加 `"counts_scope": "window"`（`:523`）与独立命名空间 `"farm": {loaded,complete,crops,dryCrops,unwateredCrops,hoeDirt}`（`:524-525`）⇒ 窗口计数与 farm 读数不再同列。
- `checks.crops_watered` 仍读窗口 `rep.final["unwatered_crops"]`（`:1900`），但日级证据是 `checks.watered_outdoor`（`:1903`），`rep.verified = all(rep.checks.values())`（`:1907`）。run2 的白过机制（室内窗口恒 0 ⇒ `crops_watered=true`）**不再是充分条件**：A1/B1 实测"窗口会说没浇"时 `watered_outdoor=False` ⇒ 当天不 VERIFIED。

### ④ `complete==false` / 旧 Mod / 未加载 ⇒ 退回窗口，不得把 0 当"没干格" —— 成立
- 三条都不满足 farm 分支条件 ⇒ 必走窗口（`return` 语句结构上互斥，`:556` 与 `:585`）。
- `FarmScan.cs:119` 的真实形态 `{Loaded=false, Complete=true}`（`Game1.getFarm()` 为 null 时）被 `loaded is not False` 挡住；`FarmScan.cs:204 _acc.Complete = true` 只在整轮（terrain+objects）跑完后设置 ⇒ `complete=true` 确实是"全农场扫完"。
- 作者用例③（`tests/test_longrun.py:1920-1938`）同时覆盖 `complete=false` 与"无 dryCrops 字段"两态；用例④后半（`:1952-1959`）覆盖 `loaded=false`；我实跑 **Ran 6 / OK**，并另跑 A6（旧 Mod）得 `False, window, dry=1`。

### ⑤ 5 条假世界单测的断言"真的在验东西" —— 成立（卡面 5 条，实现 6 条，共 6 条全绿）
类 `TestTask19WaterEvidence`（`tests/test_longrun.py:1865-2004`），辅助 `_run`(:1873)/`_with_crop`(:1880)/`_indoor`(:1886)：
1. `test_indoor_final_snapshot_does_not_white_pass`(:1894) —— `False`、`scope=="window"`、`(crops,dry)==(1,1)`、`tiles>0`（**核心负例**）。
2. `test_all_watered_is_true`(:1907) —— `True`、`(1,0)`、`tiles>0`（正向 + coverage）。
3. `test_farm_incomplete_or_old_mod_falls_back_to_window`(:1920) —— 两态都 `False` + `window` + `tiles>0`（**不许采信"没扫完的 0"**）。
4. `test_no_outdoor_snapshot_is_false_never_default_true`(:1940) —— 关键设计：**作物其实浇好了但没有户外快照**，仍必须 `False`（证明不是恒真）+ `(tiles,dry)==(0,None)` + note 含"没有任何 location.isOutdoorFarm==true 的快照"；再测 `loaded==false` 的 0 不算证据。
5. `test_farm_scope_uses_dry_crops`(:1961) —— `(tiles,crops,dry)==(5,5,3)`、`scope=="farm"`；`dryCrops=0` ⇒ `True` **即使 `unwateredCrops=5`**（证明用的是干格数而不是 `needsWatering()`）。
6. `test_day_end_carries_watered_outdoor_and_final_water`(:1981) —— 端到端：`rep.checks["watered_outdoor"] is True`、`final_water` 含六键、`("farm",25,25,0)`、`assertNotIn("unwateredCrops", fw)`、`day_end` 事件里 `end["final_water"] == fw`。

### ⑥ 字段名/闸门对齐 —— 成立（并有实证）
- 闸门读的就是这两个键：`day_end.final_water`（`tools\verify-run3.py:383`）与 `day_end.checks.watered_outdoor`（`:315-322`，`:382-389` 互检）；大脑侧写 `longrun.py:283` / `:1903`。
- `_water_evidence` **永远返回 bool**、`final_water` 永远写（`:550-551` docstring 明示）⇒ 闸门"缺字段即问题"不会因大脑省略字段而触发。
- **实证**：我用产线函数的真实返回值造了 3 本账本，闸门全部识别并按语义判定（§3 B1/B2/B3）⇒ 字段名/语义两侧确实对齐，不是纸面比对。

---

## §3 破坏性实验（我亲跑，`scratch\_t35_probe.py`）

命令：`$env:PYTHONUTF8="1"; & $py scratch\_t35_probe.py`（`$py` = 主运行时的 python.exe）

### 3.1 直接打点产线 `_water_evidence`

| 实验 | 输入 | 实测输出 | 期望 | 结论 |
| --- | --- | --- | --- | --- |
| A1 | 末快照=室内（`isOutdoorFarm=false`），户外快照里有 1 格未浇作物 | `ok=False scope=window (tiles,crops,dry)=(1,1,1)` | False | ✅ 不许白过 |
| A2 | 同上但作物已浇 | `ok=True (1,1,0)` | True | ✅ |
| A3 | 户外快照存在但 `tiles=[]` | **`ok=True tiles=0 crops=0 dry=0`**，而 note 写"该快照窗口里一格都没有 ⇒ 证据不足，不能自称浇过" | False | ⚠️ **NIT-1**（注释与返回值矛盾） |
| A4 | `farm={complete:true, loaded:true, dryCrops:3, crops:5, hoeDirt:5}` | `ok=False scope=farm (5,5,3)` | False | ✅ |
| A5 | `farm={complete:true, loaded:true, crops:0, dryCrops:0, hoeDirt:0}` | `ok=True scope=farm (0,0,0)` | True（真空真） | ℹ️ INFO-1 |
| A6 | 旧 Mod：有 `crops/unwateredCrops/hoeDirt`、无 `dryCrops` | `ok=False scope=window (1,1,1)` | False | ✅ |
| A7 | 窗口 `tilesTruncated=true` 且窗口内 0 格作物（作物在窗外） | `ok=True crops=0 dry=0` | — | ⚠️ **NIT-2**（截断不参与判据） |

### 3.2 三本破坏性账本 → `tools\verify-run3.py`

造法：取 `scratch\journal-green.jsonl`（3 天全绿、exit 0）的 3 个 `day_end`，把 `checks.watered_outdoor` 与 `final_water` 换成 **A1/A4/A3 的产线真实返回值**，`verified` 按 `longrun.py:1907 all(checks.values())` 同口径重算。

| 账本 | `watered_outdoor` / `final_water` | 闸门读数 | 结论 |
| --- | --- | --- | --- |
| `journal-green.jsonl`（对照） | true / 无 final_water | **exit 0**，尾部连续 VERIFIED 3/3（3 条 info：缺 final_water 无法核对来源） | 对照正常 |
| `review-t19-B1-window-dry.jsonl`（室内末快照 + 户外未浇） | false / `{scope:window,tiles:1,crops:1,dry:1}` | **exit 1**：`[spring 10] checks.watered_outdoor=false（睡前还有没浇的作物）`；尾部 VERIFIED 0/3 | ✅ 不许白过 |
| `review-t19-B2-farm-dry.jsonl`（farm 口径 3 干格） | false / `{scope:farm,tiles:5,crops:5,dry:3}` | **exit 1**：同上文案 | ✅ 不许白过 |
| `review-t19-B3-empty-window-true.jsonl`（空窗口却自称 true，**大脑同口径会判 VERIFIED**） | true / `{scope:window,tiles:0,crops:0,dry:0}` | **exit 1**：`[spring 10/11/12] checks.watered_outdoor=true 但 final_water.scope=window 且覆盖 0 格（当天没有任何户外快照）⇒ 该 true 不可采信：task-19 要求 5④ 规定此时必须如实 False/缺省，禁止默认 true` | ⚠️ 闸门抓住（NIT-1 的兜底），但大脑侧仍是"自认达标"⇒ 只能算白烧一天 |

（注：B1/B2 的 `exit=1` 是干净读数；管道 `| Select-String` 后 `$LASTEXITCODE` 会显示 `-1`，属 pwsh 管道假象，已单独复跑确认为 1。）

### 3.3 集成（真跑一天）I1：世界浇过、`farm` 块仍自述 dryCrops=1

`run.run()` ⇒ **1**；`checks = {slept_by_us:true, no_blocking_modal:true, no_hard_failures:true, no_unmet_stages:true, crops_watered:true, watered_outdoor:false, day_justified:true}`；`verified=False`；`final_water={scope:"farm", tiles:1, crops:1, dry:1}`；同时窗口口径 `unwatered_crops==0`（作物确实浇过了）。
⇒ 负路径接线正确（`watered_outdoor=False` ⇒ 不 VERIFIED ⇒ 退出码 1）；两套仪器不一致时以 farm 为准（保守方向），窗口 `crops_watered` 仍进 `all(checks)`（见 NIT-3）。

---

## §4 口径一致性 / 越界检查

- 通过形态与闸门一致：farm 口径 `scope=="farm"` + `tiles>0` + `crops>0` + `dry==0`；window 口径 `tiles>0`；`window & tiles==0` 反而是问题（B4b，`tools\verify-run3.py:382-389` 附近）—— 本次在制与它不冲突（正常 window 分支总有 `tiles>0`；唯一能产出 `tiles==0` 的是 A3 那条，见 NIT-1）。
- 越界：dev-coder 只改了 `brain/agentfarm/longrun.py` 与 `tests/test_longrun.py`（`git status`/`git diff --stat` 双证）；`mod/`、`farmwork.py`、`tools/`、`docs\00-开发日志.md`、`logs/` 未动；未 bump、未 deploy。
- 附带（非本卡要求，但相关）：我 task-15 验收时提的 **N1**（`stage_midway_leftover` 事件不存在）**已在本次在制里补齐** —— `longrun.py:1866-1882` 对"同阶段种类更早一轮 leftover>0、最后一轮归零"发 journal + `rep.notes`，**纯信息项、不改 VERIFIED/退出码**，与 Lead 的权威口径注释（`:1856-1862`）一致。

---

## §5 NIT 清单

| # | 现象 | 行号 | 建议 | 阻塞 run3？ |
| --- | --- | --- | --- | --- |
| NIT-1 | 空窗口时 note 说"证据不足，不能自称浇过"，但 `return len(dry_t) == 0` 对空窗口**恒为 True** ⇒ 自称与注释矛盾，且无用例覆盖 | `longrun.py:595-597` | 改成 `if not win: return False, info`；补一条"户外快照 0 格 ⇒ False"用例 | **否**。可达性：`ReadTiles`（`WorldSnapshot.cs:386-478`）只收 `objects`+`terrainFeatures`（全农场、按距离取最近 400）⇒ 要 `win=={}` 需**整个农场**一个对象/特征都没有，本机农场（1400+ 格、草/杂草/耕地）不可达；真出现时闸门 B4b 会判 problem（B3 实测 exit 1）⇒ 后果是"白烧一天"而不是白过 |
| NIT-2 | 窗口分支不看 `location.tilesTruncated`（上限 400、按离玩家距离，`WorldSnapshot.cs:352/475-476`），作物落窗外时 `dry=0` 会白过；`final_water` 也不记 truncated ⇒ 事后无法分辨 | `longrun.py:585-597` | `final_water` 加 `"truncated": bool((outdoor_obs["location"] or {}).get("tilesTruncated"))`；truncated 且 `crops==0` 时不做证据（False 或明确置疑） | 否（只在 farm 口径不可用时的兜底路径；0.7.22 有 `complete/dryCrops` ⇒ 正常走 farm） |
| NIT-3 | farm 口径无新鲜度判据：`final_water` 不记 `farm.scanSeq` 与 obs `worldSeq`；`FarmScan` 软生存期 `FreshSeconds=2.0`（`FarmScan.cs:31/132-133`），`observe` 只把**下一 tick** 标 force（`BridgeHost.cs:448`）⇒ 同一张快照里 `farm` 计数可能比当场算的 `location.tiles` 旧 | `longrun.py:556-574` | 把 `scanSeq`/`worldSeq` 记进 `final_water`（可见性，便于 run3 事后判定）；**不要**把 `crops_watered` 从 `checks` 删掉 | 否（当前由"窗口 `crops_watered` 仍进 `all(checks)`"兜住，方向保守；见 §3 I1） |
| NIT-4 | 负路径缺端到端用例：6 条里只有 ⑥ 走 `run.run()`，且是 farm 全干净的正面情形 | `tests/test_longrun.py:1981-2004` | 补一条"真跑一天 + `farm.dryCrops>0` ⇒ `rep.verified is False`、`run()` 退出码 1"（我已在 §3 I1 手工跑过，接线是对的） | 否 |

**INFO-1**：`crops==0` 时 `watered_outdoor=True`（真空真，A5）—— 语义上"没有作物可浇"，符合卡面定义；但它意味着这条判据不区分"全浇完"与"根本没种"。拦滥用的是阶段后置条件 + 0 步 VERIFIED 证据规则（`tools\verify-run3.py:390-402`），不是这条。
**INFO-2**：`checks.crops_watered` 名义上是"旁证、不作证据"，但 `rep.verified = all(checks)`（`longrun.py:1907`）使它成为**必要**条件 ⇒ 两套仪器不一致时当天不 VERIFIED（保守）。与卡面措辞略有张力，方向是更严，建议保留。

---

## §6 结论

**PASS-WITH-NITS。** 六条验收条款全部成立：双口径与兜底逻辑（①④）、`final_water` 六键与 `scope` 语义（②）、两套仪器分名与 `crops_watered` 降级（③）、6 条用例断言有效（⑤）、与 `tools\verify-run3.py` 闸门逐字对齐（⑥）—— 后者有实证：我用产线返回值造的 3 本账本被闸门按语义判成 exit 1（B1/B2）与 B4b problem（B3）。

**最关键的一条我确认不存在白过**：任何一天拿不到户外证据（无户外快照 / 旧 Mod / 扫描未完成 / farm 未加载）⇒ `watered_outdoor=False` ⇒ 不 VERIFIED（A1、A2 反证、作者用例④"作物其实浇好了也 False"、闸门 B1 四处一致）。

唯一建议提交前顺手修的：**NIT-1**（`longrun.py:595-597` 空窗口注释与返回值矛盾，一行改动 + 一条用例）；其余为可见性/覆盖度建议。全部不阻塞 run3 前置，也不阻塞 Lead 提交这两个文件。
