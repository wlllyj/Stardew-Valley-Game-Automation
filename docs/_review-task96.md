# task-97 对抗验收：task-96 的 farm 证据 fail-closed 修法

**判定：FAIL**（一条 fail-open 残留，旧 Mod `<0.7.22` 可达、且版本闸门只 WARN ⇒ 真的能白过一天）
**但**：该残留**在 0.7.27 装机下不可达**（0.7.22 起 `FarmView` 必有 `dryCrops`）⇒ **不影响 run8/task-89 的部署决定**；
最小修法一行（§5），是否先修再跑由 Lead 定。主攻四条（B 段）全部 FAIL→PASS，C 段其余四项全部拦住。

写范围：`docs/_review-task96.md` + `scratch/`。未碰 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs/00-开发日志.md`、`manifest.json`、`bridge.py`。

---

## §1 基线（我亲跑，HEAD `d849cd7`）

| 项 | 读数 |
|---|---|
| HEAD / 工作树 | `d849cd7`；`git status --short` 干净 |
| 被验对象 | `git show --stat 486203d` = 恰好 2 文件：`brain/agentfarm/longrun.py` **+77/−31**、`tests/test_longrun.py` **+208** |
| 越界扫描 | `git show --name-only 486203d` 对 `manifest\|bridge\.py\|^logs/\|00-开发日志\|^tools/\|^mod/` **零命中** |
| SHA256 | `longrun.py` `2CAFA9F82A408914D5711962E624B571AAA188678EDEA20C408641B867D02DDE`；`tests/test_longrun.py` `9E4EFEE907BC2BAE101B1570A46834B6FEE0D62F0613F448CB792E166BF129B8`；`tests/test_farmwork.py` `04AC1FBDF79DE76F0D8209A2F06089B42D32307FC483027D2D1D3F64792EA8C6`（未变）；`brain/agentfarm/farmwork.py` `8B62190A7E4010B835A122360E794ADD82B28D7068DA58855CA43C377672509C`（未变）；`tools/verify-run3.py` `7356D4CBA1D0A1EE3DFDB5F2723EB39E615C0795C289122863A46730A9A965C3` |
| 版本 | `mod/AgentFarm.Bridge/manifest.json:4` = `0.7.27`；`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.27"` |
| `py_compile -W error::SyntaxWarning` | exit 0 |
| `tests.test_longrun tests.test_farmwork` | **Ran 258 / OK** |
| 全量 `unittest discover -s tests` | **Ran 588 / OK**（Lead 报 587，以我的 588 为准；差 1 条是 tree 里其他卡的用例） |
| 账本矩阵 `--days 3` | `journal-green` rc0/VERIFIED、`_t5x_vacuum` rc1、run2 rc1、run3 rc1、run5 rc1、run6 rc1、run7 rc0/VERIFIED ⇒ 与 Lead"一字未变"一致 |

## §2 A 段范围

`486203d` 只动两文件、不 bump、不动 Mod/tools/logs；`mod/`、`tests/` 其余文件、`docs/00-开发日志.md` 未动。task-96 的夹具改动集中在 `tests/test_longrun.py`（见 §3.2），生产代码只有 `longrun.py` 的三处。

## §3 B 段：task-92 的四条进攻必须 FAIL→PASS

### 3.1 逐条结果（真代码，`T92_ROOT`=仓库）

| task-92 探针 | 修前 | 修后 | 被哪条拦住（行号） |
|---|---|---|---|
| C6c 活苗谎报 dead + `farm.complete=false` | 假 VERIFIED | **stuck + `watered_outdoor=false`，不 VERIFIED** | `longrun.py:782-801`（`_farm_scope_work` 不再对在场返回 None）+ `:1527`（`work_reasons` 给理由）+ `:1713-1718`（`sleep_guard` fail-closed） |
| C6d "没有 farm 块" | 假 VERIFIED | **探针失效** → 重建为 B2（obs 无 `farm` 键）：stuck + false | 同上（`:760-780` 返回 None ⇒ `:1713`） |
| C8b 真·窗外没浇活苗 + 证据不可用 | 假 VERIFIED | **stuck + false** | 同上 |
| C8c 同上（另一世界） | 假 VERIFIED | **探针失效** → 重建为 B1（`farm={}`）：stuck + false | 同上 |

- 拦截理由原文（C8b/B1，`ended_reason`）：`stuck:连续 3 轮世界没有任何变化（最后意图：['review']…）；守卫仍说还有活：人在农场里且 farm 证据不可用（farm.complete=None/loaded=None/dryCrops=None）⇒ farm 口径不算证据，不许据此判『没有活』：窗口的 crops==0 不是证据（run7 那颗没浇的活苗就在窗口外）`。
- 工具侧同向：`ok=False / needs_review`，problems = `ended_by=stuck（不是我们主动睡过去的）` + `day_end verified=false`。
- 未变的对照：C6a（farm 真值 `dryCrops=1`）仍 stuck/`watered_outdoor=false`；C6b 仍被工具 `ended_reason 以 no_work 开头，但 day_end.dry_dead=1` 判红；C7 仍 needs_review；账本级 F1/F2/F3 **全部** needs_review（F1 旧 exit-0 盲区已被 Lead `23e13c7` 关掉）。
- 补充：`farm={}`（有键但空）与**完全没有 `farm` 键**（B2，`obs.pop("farm")`）**行为逐字相同** ⇒ 两种"旧 Mod"形态都 fail-closed。

### 3.2 ⚠️ 夹具改动确实掩盖了东西（Lead 点名要查的）

`tests/test_longrun.py:167`：
```python
"farm": dict(self.farm) if self.farm is not None else self.farm_scan(),
```
配合 `_EMPTY_FARM_SCAN`（`:54-60`）与新增 `farm_scan()`（`:176-212`），**`w.farm = None` 的语义从"没有 farm 块"变成了"按世界状态自动生成一份良构扫描"** ⇒ 所有用 `None` 表示"证据不可用"的**既有探针/用例**都静默变成"证据可用"（我的 C6d/C8c 就这样从"假 VERIFIED"变成"合法 VERIFIED"，看着像修好了）。
要造"证据不可用"必须显式写 `{}` / `{"complete": False}` / `{"loaded": False}`，或把键 pop 掉。**建议**：给 `FakeWorld` 加 `farm_missing = True` 之类的显式开关，别再让 `None` 兼职两种含义（NIT-6）。
另：`farm_scan()` 的 `crops` 把死苗也算进去（`:191-204` 的 `crops += 1`），与它自己 docstring 的"只算活苗"（`:187-189`）不符（NIT-2，仅夹具）。

## §4 C 段：朝修法本身进攻

探针：`scratch/_t97_c.py`（输出 `scratch\_t97_c_out.txt`，118 行）、`scratch/_t97_c2.py`（边界，输出 `scratch\_t97_c2_out.txt`）。

| # | 攻击 | 结果 |
|---|---|---|
| ① | 部分可用证据 | **fail-open（§4.1 确认）**：`complete=true` + **`dryCrops` 缺失** + `ripeCrops==0` ⇒ `no_work`+`watered_outdoor=true`+`verified=True`，工具 **ok=True / VERIFIED** |
| ② | 真没活 + 证据不可用 + 空世界 | **有界**：`entries=8 / actions=1`，以 `stuck:守卫说还有活（…证据不可用…）但没有任何作业区拿得出目标` 收尾，`verified=false`、`watered_outdoor=false` ⇒ 不死循环、不洗白（工具 needs_review）|
| ③ | 窗口 `crops>0` 但全是死苗 + 证据不可用 + 窗外没浇活苗 | `ended_by=stuck`、`verified=false`、`watered_outdoor=true`（窗口 24 格全活苗已浇）⇒ 当天没白过，但 `watered_outdoor=true` 与"窗外活苗的干无法证明"冲突（NIT-3）|
| ④ | 窗口 `dry==0` vs farm `dryCrops=2` 打架 | **farm 优先**：守卫 `keep_working` ⇒ `stuck`、farm 口径 `dry=2`、`watered_outdoor=false`、不 VERIFIED ✓ |
| ⑤ | 畸形 `complete` | `complete="true"`（字符串）+ 窗外没浇活苗 ⇒ fail-closed（stuck、不 VERIFIED）✓；`loaded=False` ⇒ 同样 fail-closed ✓ |

### 4.1 ①的最小触发条件与可达性（本次判 FAIL 的唯一依据）

边界实验（同一世界：窗外一株真·没浇的活苗 + 窗内一株浇好的活苗 + 无耕地）：

| 变体 | `farm` 块 | 结果 |
|---|---|---|
| **C1 / C1b** | `complete=true, crops=2, ripeCrops=0`（**无 `dryCrops`**） | **`no_work` + `verified=True` + 工具 VERIFIED（假绿）** |
| C1c | 同上但 `ripeCrops=2` | 守卫以 ripe 否决 ⇒ `stuck`、不 VERIFIED ✓ |
| C1d | `complete=true, crops=2`（`dryCrops`/`ripeCrops` 都缺） | `_farm_totals` 返回 None ⇒ fail-closed ✓ |
| C1e（对照） | `complete=true, dryCrops=0, ripeCrops=0`（完整证据） | `no_work`+VERIFIED —— **正确**（证据说真没活）|

⇒ **最小触发 = `farm.complete is True ∧ loaded is not False ∧ "dryCrops" 缺失 ∧ ripeCrops == 0`**；
根因 `longrun.py:776-780`：
```python
dry = farm.get("dryCrops")
ripe = farm.get("ripeCrops")
if dry is None and ripe is None:
    return None
return (int(dry or 0), int(ripe or 0))     # ← dry 缺失 + ripe=0 ⇒ (0, 0)："未知"被当成"0"
```
⇒ `work_reasons`（`:1527`）不给理由、`sleep_guard`（`:1713` 之前的 `farm_work is not None` 分支）不否决、`_water_evidence` 退回窗口口径（`crops>0` 且都浇过 ⇒ `dry=0` ⇒ true）⇒ `day_justified=true` ⇒ 假 VERIFIED。

**可达性证明（这是它不属于"纸面畸形输入"的原因）**：
- `git log -S '"ripeCrops"' -- mod/AgentFarm.Bridge/Contracts.cs` ⇒ `5c4b2d8`（P2 里程碑A，**最早的桥协议**）；
- `git log -S '"dryCrops"' -- mod/AgentFarm.Bridge/Contracts.cs` ⇒ `bacd55a`（**0.7.22**，task-23）；
- `git show 5c4b2d8:mod/AgentFarm.Bridge/Contracts.cs` 实证旧 `FarmView` 有 `crops`/`ripeCrops`/`unwateredCrops`/`complete`、**没有 `dryCrops`**；
- 版本闸门只警告不停机：`watchdog.py:139-148` 的 `mod_version_mismatch` 是 **LEVEL_WARN**；`longrun.py:3534-3537` 只记 journal；
⇒ **任何 `<0.7.22` 的 Mod**（含 0.7.21、0.7.22 之前全部）都能跑完全程，其 `farm` 块正好是 `complete=true` + `ripeCrops` 有值 + `dryCrops` 缺失 —— 与 C1 逐字同形。task-96 要关的"旧 Mod / 证据不可用"场景，**在"旧 Mod 恰好没有成熟作物"（最常见）时仍会白过一天**。

## §5 最小修法（一行，Lead 决定是否先修再跑 run8）

`brain/agentfarm/longrun.py:776-780`：
```python
dry = farm.get("dryCrops")
ripe = farm.get("ripeCrops")
if dry is None:                      # 旧 Mod（<0.7.22）没有 dryCrops ⇒ 干作物数"未知"，不是 0
    return None
return (int(dry), int(ripe or 0))
```
**代价（必须同时接受）**：旧 Mod（`<0.7.22`）下**每个在场日都会 fail-closed** ⇒ 以 `stuck` 收尾（有界，C2 形态：`entries=8`）、永远拿不到 VERIFIED ⇒ **旧 Mod 再也跑不出绿 run**。这正是"诚实优先"的形态（题面要求"旧 Mod 必须无法判定，不许当 0"），但它把"旧 Mod 兼容"从"会给错结论"改成"明确做不到"。若 Lead 想保留旧 Mod 的可跑性，替代方案是**只在 `dry is None and (ripe or 0) == 0` 时 fail-closed**（即堵住 C1 的精确触发，C1c 保持现状），代价是"未知"仍被部分当成"0"。两条都可由我下一轮验。

## §6 D 段 NIT 表

| # | 现象 | 位置 | 建议 | 阻塞 run8？ |
|---|---|---|---|---|
| NIT-1 | §4.1 的 fail-open（旧 Mod 可达） | `longrun.py:776-780` | §5 一行修 + 用例（`dryCrops` 缺失 ⇒ 当天不 VERIFIED） | 否（0.7.27 不可达），但**不应宣布 task-96 已关闭** |
| NIT-2 | 夹具 `farm_scan()` 的 `crops` 含死苗，与 docstring 不符 | `tests/test_longrun.py:191-204` vs `:187-189` | 改注释或改实现 | 否 |
| NIT-3 | 窗口全死苗 + 证据不可用 ⇒ `watered_outdoor=true`（窗外活苗的干无法证明） | `longrun.py:1056-1082` | 与 NIT-1 同源；修 NIT-1 后自然消失 | 否 |
| NIT-4 | 真没活 + 证据不可用只能以 `stuck` 收尾（拿不到 `no_work` 的合法收工） | `longrun.py:1713-1718` | 设计代价，保持（有界：`entries=8`）；若想区分"真没活且证据不可用"，需 Mod 侧给出可信空读数 | 否 |
| NIT-5 | 我的探针 `journal 时间戳回退` info（夹具 `t=0` 起） | `scratch/_t97_c*.py` | 夹具问题，非产品 | 否 |
| NIT-6 | `FakeWorld.farm = None` 语义兼职（§3.2） | `tests/test_longrun.py:167` | 显式开关 | 否 |

## §7 D 段：run8"不做操作员预置"的风险评估（Lead m04324 点名）

证据：`logs/run7-baseline.json`（day `[1,summer,3]`、`money=14`、**`seeds: []`**、`farmingLevel=0`、`crops=35`、`dryCrops=35`、`waterLeft=23`、`tillableCount=147`、`tilesTruncated=true`）+ `logs/longrun-3day-llm-run7.jsonl`（7 天 1230 行；`scratch/_t97_run7.py` 汇总）+ 事件计数。

1. **"day1 没种子卡成 `stuck`"这个担心的答案：不会（有界且能合法收工）。** run7 的 summer 8/9 就是形态证明：当天只干 5–6 步（浇完水、没种子可买）⇒ `no_work:确实找不到可做的活` ⇒ 当天 **VERIFIED**。我的 C1e 探针同样形态。钱不够买种子（14 < 20，`seed_gate` 5 次）**不会**造成硬失败或空转。
2. **但"经济闭环"这一步在 run8 里很可能走不到。** run7 全程 **harvest/sell/buy 事件 0 个**、`money` 恒 14、`finish.code=0/verified_streak=3/actions=683`；基线 `seeds: []`。`sell` 需要背包里有可卖物、`buy` 需要次日到账后 `money ≥ 20` ⇒ 只有当窗口里真有作物成熟并被收掉，才能走 `harvest → sell →（次日）→ buy → plant`。**账本与 baseline 都不记录成熟数**（`day_end` 的 farm 块没有 `ripeCrops`），所以我无法从离线证据断定 run8 三天内会不会有收获。
   ⇒ 若这个经济闭环是 run8 的验收项之一，建议 Lead：(a) 装机后先 `observe` 一次看窗口 `tiles[].ripe` 有没有熟作物；(b) 或者接受"run8 可能只验证到浇水腿、经济腿算 INFO"。
3. **残留 0/3 风险来自别处**：旧存档里的不可达簇（run7 有 69 个 `unreachable_stage`、14 个 `unreachable` 事件、1 次 `stuck_flush`，summer 6 以 `stuck` 收尾）是物理障碍，不随"不做预置"改变；若 run8 的三天窗口里再出现一个 `stuck` 日就断连。这与 task-96/97 无关，但值得知道。

## §8 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"; $env:T92_ROOT = (Get-Location).Path
& $py scratch\_t92_adv.py   ; & $py scratch\_t92_adv2.py      # B 段（C6d/C8c 已失效，见 §3.2）
& $py scratch\_t97_c.py     ; & $py scratch\_t97_c2.py        # C 段 + 边界
& $py -m unittest tests.test_longrun tests.test_farmwork -v   # 258 OK
& $py -m unittest discover -s tests                            # 588 OK
& $py scratch\_t97_run7.py                                     # run8 风险评估证据
```

## §9 结论

- **B 段（主攻）四条全部从 FAIL 变 PASS**，且拦截点单一（`_farm_scope_work`/`work_reasons`/`sleep_guard` 三处同源），有界性、farm 优先、畸形 `complete` 都过。
- **一条 fail-open 残留（§4.1）**，触发条件窄（`complete=true` + `dryCrops` 缺失 + `ripeCrops==0`）但**旧 Mod `<0.7.22` 真实可达**、版本闸门只 WARN ⇒ 按卡面"若确实白过直接判 FAIL"的口径，**判定 FAIL**。
- **对 run8 无影响**：装机版 0.7.27 的 `FarmView` 必有 `dryCrops`；修复建议一行（§5），可先跑 run8 再补卡（NIT-1 已写明"不应宣布 task-96 已关闭"）。
