# task-178 独立对抗验收：task-176（0.7.34 harvest 判据改游戏口径）

**对象**：`037e599`（"0.7.34 task-176: harvest 判据改游戏口径 `ready` + `GetHarvestMethod()` + `acted` 诚实化"）
**验收人**：deputy-lead（只读生产代码；只写本文件 + `scratch/_t178_*`）
**判定**：**PASS-WITH-NITS（无必修项）⇒ 0.7.34 可以据此冻结**
**结论一句话**：三条必修（`Crop.GetHarvestMethod()` 取代不存在的字段、`harvestMethod`/`readySource` 无条件出键、`acted` 由目标格签名差分决定）实现与 Lead 的 IL 口径逐条一致；脑侧四类伪造（谎报 `acted`、缺键冒充 null、`ready=null` 当可收、Scythe 走 `interact`）全部骗不过；`readySource="fields"` 的等价兜底**确实可达**（未 fail-closed 过头）。两条护栏缺口（测试杀不死"兜底被改成 null"的变异、作者的变异-用例映射不实）与两条 Mod 侧 NIT 均**不阻塞冻结**，已逐条给出修法与理由。

---

## §1 判定与要点

| 项 | 结论 |
|---|---|
| 三条必修实现是否与口径一致 | ✅ 逐条一致（§2、§3） |
| 卡面 §2 六条作弊通道 | ✅ 6/6 拦住（§3） |
| 作者 10 条用例是否真的在验东西 | ⚠️ 5 条源码契约 + 5 条脑侧行为都有效，但**变异-用例映射虚高**（GAP-2） |
| 作者自报 4 变异 | ⚠️ 实测 a=1 / b=**0** / c=2 / d=1（b 完全不被杀 ⇒ GAP-1） |
| 越界 / 版本 / 读数 | ✅ 7 文件、零越界、`py_compile` 0、519 OK、904 OK、build 0 警 0 错 |
| 是否阻塞 0.7.34 冻结 | **不阻塞** —— 代码本身正确，缺口在"回归护栏薄弱" |

---

## §2 A 段：范围、读数、指纹（全部亲跑）

**HEAD `037e599`**（父 `dec8ac9` 0.7.34 诊断更正 + `01d3d75` task-173 doc）；工作树干净。

`git show --numstat 037e599` = **恰 7 文件 +480/−40**：

| 文件 | +/− |
|---|---|
| `docs/_t176-harvest-ready-findings.md` | 119/0（新文件） |
| `mod/AgentFarm.Bridge/Contracts.cs` | 27/3 |
| `mod/AgentFarm.Bridge/CropMeta.cs` | 77/21 |
| `mod/AgentFarm.Bridge/FarmScan.cs` | 1/1 |
| `mod/AgentFarm.Bridge/Skills.cs` | 76/9 |
| `mod/AgentFarm.Bridge/WorldSnapshot.cs` | 5/1 |
| `tests/test_longrun.py` | 175/5 |

越界扫描（`manifest.json`、`brain/agentfarm/bridge.py`、`^logs/`、`00-开发日志`）**0 命中**。

**SHA256 前 16 / 字节数**（我自己的读数，工作树 == 提交）：

| 文件 | SHA256(16) | 大小 |
|---|---|---|
| `mod/AgentFarm.Bridge/CropMeta.cs` | `430CDEDA994A2142` | 12484 |
| `mod/AgentFarm.Bridge/Contracts.cs` | `0A068F2DE09338BF` | 68630 |
| `mod/AgentFarm.Bridge/Skills.cs` | `37AFADAEC607AB09` | 37369 |
| `mod/AgentFarm.Bridge/WorldSnapshot.cs` | `9F10D1CD93A6A52E` | 53629 |
| `mod/AgentFarm.Bridge/FarmScan.cs` | `FDD4F32A3E89E9CD` | 19091 |
| `tests/test_longrun.py` | `09509632AE511A08` | 487337 |
| `docs/_t176-harvest-ready-findings.md` | `D1C10B31EB17C3CD` | 6991 |

**读数**（与作者自报、Lead 亲核三方一致）：

- `py_compile -W error::SyntaxWarning`（longrun/farmwork/planner/bridge）**rc=0**
- 定向 `tests.test_farmwork tests.test_longrun tests.test_planner` = **Ran 519 / OK**
- 全量 `python -m unittest discover -s tests` = **Ran 904 / OK（0 红）**
- `dotnet build mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` = **0 警告 0 错误**（1.38 s）

留档：`scratch/_t178_targeted.txt`、`scratch/_t178_full.txt`、`scratch/_t178_build.txt`、`scratch/_t178_diff_mod.txt`（365 行）、`scratch/_t178_diff_tests.txt`。

---

## §3 卡面 §2 六条通道实测（探针 `scratch/_t178_probe.py`，23/23 PASS）

探针用真 `FarmWorker` + 假世界（`FakeWorld` 现算 `farm` 块），源码契约部分**自己解析** C# 文本、不复用作者的断言。原始输出 `scratch/_t178_probe_out.txt`。

| 通道 | 实测 | 证据 |
|---|---|---|
| ① 伪造 `readySource` | ✅ 拦 | 4a `ready=null` + `readySource="game"` ⇒ 不是目标、`code=skipped`、零 `interact`；4b `ready=false` + `fields` ⇒ 不是目标；7b 键缺失 ⇒ 同样不摘 |
| ② `harvestMethod` 缺键冒充 null | ✅ 拦 | 5c 缺键 ⇒ `harvest_tool is None` 但**仍是目标**；5d 实跑 ⇒ `ok=False code=failed`、`interacted=[CROP]`、作物还在（284×0 形态被复现并如实判失败）；5e 显式 `null` ⇒ 同样判不了；1b 契约断言 `ReadMember(crop,"HarvestMethod")` 已不在 |
| ③ `worldSeq` 前进但格未变仍报 `acted=true` | ✅ 拦 | 6a 谎报 `{ok:True,acted:True}` 而世界没变 ⇒ **failed**（reason 含"游戏口径可收但作物还在"）；6b 回执缺 `acted` 且世界没变 ⇒ failed；3a-3c 契约：`TileSig` 前后两次 + `observedChange` 要求两者非 null 且不等 + 三态 `Status`/`Acted` |
| ④ `ready=null` 被脑侧当可收 | ✅ 拦 | 4a/7b：`tile_ready` 只认 `ready is True`，缺键/None ⇒ skipped + reason "这一格缺 ready 字段" |
| ⑤ Scythe 类被 `interact` 摘走 | ✅ 拦 | 5a/5b：`harvest_tool=="scythe"` ⇒ 走 `use_tool`（`interacted==[]`、`swings={(60,10):1}`、作物消失、`ok=True`）；6c 正对照 Grab 走 `interact` 真摘到 |
| ⑥ fail-closed 过头（等价兜底被当 null） | ✅ 代码侧不成立（⚠️ 护栏见 GAP-1） | 我读 `mod/AgentFarm.Bridge/CropMeta.cs:110-140`：游戏分支 `if (direct != null) return (direct, "game")` 之后**字段路径完整**（`:132` 只在 `fullyGrown/dayOfCurrentPhase/currentPhase/phaseDays/dead/forage` 任一为 null 时 `(null,null)`），`:137-138` 给出 `(false,"fields")`/`(true,"fields")`；探针 7a 实测 `readySource="fields"`+`ready=true` ⇒ 仍是目标且真摘到 ⇒ **没有把整片可收作物变成不可收** |

**附加**：8a 整天跑完（Scythe 作物）⇒ 作物被真挥镰摘走、零 `interact`；日级 verdict 作 info：`code=1 verified=False ended_by=stuck`，`checks` 10 键（含 task-149 的 `zero_action_evidenced`）中只有 `slept_by_us=False`/`day_justified=False`（夹具当天没睡 ⇒ `stuck`），与 task-176 无关。

---

## §4 作者 10 条用例 + 我的 4 个变异（`scratch/_t178_mutate.py`）

作者 docstring 引用的 `scratch/_t176_mutate.py` **不存在**（与 task-171 同一模式），变异装置我自建：拷 `brain`+`tests`+`mod` 到 `scratch/_t178_mut/<case>`（**必须带 `mod`**，否则 5 条源码契约用例假绿），跑 `tests.test_longrun.TestTask176HarvestMethodSourceAndActed`。原始输出 `scratch/_t178_mut_out.txt`。

| 变异 | 内容 | 实测红数 | 红的用例 |
|---|---|---|---|
| control | 无变异 | 0（10 OK） | — |
| m178a | `HarvestMethodOf` 头部插回 `return ReadMember(crop,"HarvestMethod")?.ToString();` | **1** | `test_cropmeta_uses_the_public_get_harvest_method` |
| m178b | 游戏分支后插 `return (null, null);`（= 卡面点名的"fail-closed 过头"） | **0（不被杀）** | — |
| m178c | 2 处 `[JsonIgnore(Condition = Never)]` → `WhenWritingNull` | **2** | `test_harvest_method_key_is_always_written`、`test_ready_source_is_exposed_and_carried_into_the_snapshot` |
| m178d | `bool acted = err == null && handled;` | **1** | `test_interact_acted_comes_from_an_independent_tile_comparison` |

作者自报"4/4 各杀 1 条"：**a 实测 1（与自报一致）**、**c 实测 2（比自报更强）**、d 一致；**b 实测 0 —— 自报不实且该变异正是本卡最要害的失败模式**（详见 §5 GAP-1）。

---

## §5 点名的护栏缺口与 NIT

### GAP-1（不阻塞，但建议下一卡加固）：「等价兜底被改成 null」这条变异**杀不死**

`m178b` 在 `if (direct != null) return (direct, "game");` 之后插一句 `return (null, null);`，语义上**就是** Lead 点名的 fail-closed 过头（反射拿不到就不再走字段判据 ⇒ 整片可收作物变不可收），但 10 条用例**全绿**。原因：作者的契约断言是**源码文本存在性**——

```python
fields = src.split("bool? direct = InvokeReadyForHarvest(dirt);", 1)[1]
self.assertIn('return (true, "fields")', fields)
```

只要那句文本还在（无论是否可达）就通过；而脑侧 5 条用例全部由假世界驱动、**根本看不到 C#**。

- 现状判断：**代码是对的**（我读源码确认字段路径可达、探针 7a 也实测通过）⇒ 不判 FAIL。
- 建议修法（任选，均 1 张卡内）：①把 `Ready()` 的判据/分支决策提成一个**可单测的纯函数或可注入的反射入口**，让"反射失败 ⇒ 仍走 fields"成为**行为断言**；②退一步，用**顺序/结构断言**替代文本存在性断言（例如断言 `(null, null)` 只出现在字段 gate 之后、或断言游戏分支之后不存在无条件 `return (null, null)`）；③若愿意引入最小 C# 测试工程（当前仓库没有），可真正锁住 Mod 侧行为 —— 这也是 GAP-2 的根治。

### GAP-2（不阻塞）：作者 docstring 的"变异 ⇒ 用例"映射不实

作者称"m176a ⇒ 契约 + 镰刀用例红，m176b ⇒ fields 用例红"。实测：镰刀用例是**脑侧假世界**驱动（`FakeWorld.harvest_now`），C# 改成什么都不影响它 ⇒ m178a 只红 1 条；"fields 用例"（`test_ready_reports_its_source_and_keeps_the_equivalent_fields_path`）是文本断言 ⇒ m178b 0 条。**建议修正 docstring 措辞**，避免后人误以为 Mod 侧行为已被行为测试锁住。

### NIT-1（Mod 侧，不阻塞，实际不可达）：等价 gate 没把 `which` 纳入 null 判据

`mod/AgentFarm.Bridge/CropMeta.cs:123` 读 `which`，`:131` 的判据是 `... || dead == null || forage == null`（**没有 `which == null`**），`:137` 却用 `forage.Value && which == "2"`。⇒ 采集作物（`forageCrop=true`）若 `whichForageCrop` 读不到（`which == null`），第 ④ 条判据**无法评估**却会走到 `(true, "fields")`，与文档 `:106`"任一判据字段读不到就返回 `(null, null)`（fail-closed）"字面不符。
**可达性**：`whichForageCrop` 是 1.6.15 的真实 `NetString` 字段 ⇒ 实际不可达；且只影响采集作物。
**建议**：把 `which == null` 也加进 gate（或 `forage == true && which == null ⇒ (null,null)`），一行。

### NIT-2（INFO）：门/入口类 `interact` 的 `acted` 文案与事实不符

`Skills.cs:360` 的 `TileSig` 覆盖地面物体、地形特征、浇水态、作物阶段、`Action`/`TouchAction`、门；**传送**不改变格内容 ⇒ 若将来有技能用 `interact` 开门/进洞，`observedChange=false` ⇒ `acted=false`/`no_action`/`Ok=false`，而 reason 说"以 observe 到的地点为准"。
**现状**：全仓 `interact` 唯一调用点是 `harvest()`（`farmwork.py`）⇒ **今天无影响**；建议在 docstring 里写明"`acted` 只认格内签名变化，传送类交互不适用"。

---

## §6 残余风险

1. **行为层护栏依赖源码文本**（GAP-1/GAP-2）：本次冻结的代码正确，但下次有人在 `Ready()` 里加 early return / 改反射顺序，**测试不会红**。真机侧靠 task-177 的判据（键必须存在、Scythe 走 `use_tool`、`readyCrops`/`ripeCrops` 下降 + 背包 +1 + `worldSeq` 前进；仍不给收 ⇒ 必须 `no_action`/`acted=false`）兜住，属于"真机验证替代单测"，可接受但要记档。
2. **`(60,29)` 的原始缺陷是"键被全局 `WhenWritingNull` 吞掉"**（`docs/_t176-harvest-ready-findings.md`）：本次两条 `Never` 修的是**这两把键**；若将来新增"判不了"语义的字段，仍会默认被吞 ⇒ 建议在 `Contracts.cs` 顶部注释写明这条坑（现状：`:30` 全局 `WhenWritingNull` + 逐字段 `Never` 覆盖）。
3. `ready` 判不了时 `WorldSnapshot` 给 `Tool="can"`（旧为 `(Ripe || Dead)`）⇒ 只会多给一次浇水提示，无判定影响；记 info。

---

## §7 0.7.34 能否据此冻结

**可以冻结。** 依据：
- 三条必修与 Lead 的 IL 口径**逐条一致**（`Crop.GetHarvestMethod()`、两键无条件出键、`acted` = 目标格签名差分）；
- 卡面 §2 六条作弊通道 **6/6 拦住**（真 `FarmWorker` 端到端 + 源码契约双路验证）；
- 等价兜底（`readySource="fields"`）**确实可达**，没有 fail-closed 过头（我读源码 + 探针 7a 实测）；
- 读数与作者/Lead 三方一致（519 OK / 904 OK / build 0 警 0 错 / 零越界）；
- 未决项都是**护栏强度**（GAP-1/GAP-2）与**不可达/无影响**的 Mod 侧细节（NIT-1/NIT-2），无一条会把"可收"判成"不可收"或把"不可收"洗成"可收"。

**放行附带建议**（不阻塞）：把 GAP-1 的加固（行为化断言或最小 C# 测试工程）与 NIT-1 的一行修法排进下一张 0.7.x 卡；task-177 真机复测 `(60,29)` 时按 `docs/_t176-harvest-ready-findings.md` 的四条判据取证。

---

## §8 复跑命令

```powershell
$repo = "D:\Deepseek Harness Workspace\星露谷游戏自动化"; Set-Location $repo
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "$repo\brain"

# A 段读数
git show --numstat 037e599
& $py -W error::SyntaxWarning -m py_compile brain\agentfarm\longrun.py brain\agentfarm\farmwork.py brain\agentfarm\planner.py brain\agentfarm\bridge.py
& $py -m unittest tests.test_farmwork tests.test_longrun tests.test_planner
& $py -m unittest discover -s tests
dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental

# B/C 段探针（23 检查）
& $py -W error::SyntaxWarning scratch\_t178_probe.py

# 变异复现（control + m178a/b/c/d，需带 mod 一起拷）
& $py -W error::SyntaxWarning scratch\_t178_mutate.py
```

---

## §9 越界

- 我只写：`docs/_review-task176.md`（本文件）、`scratch/_t178_probe.py`、`scratch/_t178_mutate.py`、以及 `scratch/_t178_*.txt` / `scratch/_t178_mut/`（读数与临时树，跑完已清）。
- 未改任何生产代码（`brain/`、`mod/`、`tools/`、`tests/` 均只读），未 bump、未 deploy、未碰游戏与桥，未改任务板，未写 `docs/00-开发日志.md`。
