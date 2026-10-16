# task-171 独立对抗验收：task-170（harvest 判据改游戏口径 `ready`）

对象：`d88498d`（12 文件 +688/−37）。验收人：deputy-lead（只读生产代码，只写本文件与 `scratch/`）。
判定：**PASS-WITH-NITS（无必修项）⇒ 0.7.33 可以据此冻结**（理由与残余风险见 §7）。

---

## §1 一句话

Mod 侧用反射 `HoeDirt.readyForHarvest()` 把"熟"升级成"游戏口径真能收"，脑侧 `tile_ready` fail-closed、
`harvest()` 在回执 `acted==false`/`ok==false` 时如实 `failed`、`longrun` 新增同格上限 `harvest_gave_up`
解开"摘不到的熟作物把守卫钉死"的死结；**六条进攻通道全部实测、10 条作者单测 + 3 个变异的非空转
我自己复现（control 0 红 / m170a 5 红 / m170b 3 红 / m170c 1 红）**；唯一"看起来修好其实只是把判据放宽"
的地方是 `harvest_gave_up` 这个**新的部分豁免通道**（§5 NIT-1），它不阻塞冻结。

## §2 A 段读数（亲跑）

| 项 | 读数 |
|---|---|
| 对象 | `d88498d`（HEAD 链：`fb1f613` docs 069 → `d64e527` docs 0.7.33 计划 → `d88498d`） |
| `git show --numstat d88498d` | **12 文件 +688/−37**：`brain/agentfarm/farmwork.py` 76/8、`brain/agentfarm/longrun.py` 84/18、`brain/agentfarm/planner.py` 5/1、`mod/AgentFarm.Bridge/Contracts.cs` 58/0、**`CropMeta.cs` 186/0（新文件）**、`FarmScan.cs` 8/0、`Skills.cs` 12/4、`UseToolSkill.cs` 19/1、`WorldSnapshot.cs` 8/1、`tests/test_farmwork.py` 3/1、`tests/test_longrun.py` 225/1、`tests/test_planner.py` 4/2 |
| 越界扫描 | `manifest.json` / `brain/agentfarm/bridge.py` / `^logs/` / `00-开发日志` **0 命中** |
| SHA256 前 16 | farmwork `494E84C81FCD4C11`、longrun `2C5DEAAA0368B0C1`、planner `CB9A078A78FD3D45`、Contracts `C02F011C3CC3A815`、CropMeta `8C59B5C8D94124D4`、FarmScan `28647908799805A1`、Skills `E2FC66220E5FC187`、UseToolSkill `423715D763D5F300`、WorldSnapshot `7EACD034D0155318`、test_farmwork `9BC8B5FEFE889425`、test_longrun `9A65AF1DD5A18CCD`、test_planner `74072668B73B47E4` |
| `py_compile -W error::SyntaxWarning` | farmwork/longrun/planner/bridge **rc=0** |
| 定向 | `tests.test_farmwork tests.test_longrun tests.test_planner` = **Ran 509 / OK**（与 Lead 一致） |
| 全量 | **工作树 = Ran 889 / OK（0 红）**；提交态 = Lead 报的 `889 / 2 红`（两条都在 `tests/test_analyze_longrun.py`，缺 `harvest_gave_up` 桶 ⇒ task-172）。两种口径都记录，红与本卡无关 |
| `dotnet build --no-incremental` | **rc=0、0 警告 0 错误**（`scratch/_t171_build.txt`） |
| 工作树 | 仅 ` M tools/analyze-longrun.py`（task-172 在制，非我） |

原始留档：`scratch/_t171_targeted.txt`、`scratch/_t171_full.txt`、`scratch/_t171_build.txt`、
`scratch/_t171_diff_mod.txt`（432 行）、`scratch/_t171_diff_brain.txt`（435 行）。

## §3 六条通道实测（探针 `scratch/_t171_probe.py`，25 PASS / 0 FAIL，rc=0）

原始输出：`scratch/_t171_post_out2.txt`。

**① 回执洗白** — 5/5 PASS
- 1a `{ok:false, status:"no_action", acted:false}` ⇒ `code=failed`，reason 原文
  `Mod 回执说没有真的动手（acted=False，status=no_action）：…`；
- 1b `ok=true` 但 `acted=false` ⇒ 仍 `failed`（不以 `ok` 为准，只认 `acted`）；
- 1d 回执不是 dict ⇒ 退回观测差分仍能判 `failed`；1e 回执非 dict 而作物真没了 ⇒ `ok`（观测兜底）；
- **1c【INFO】**`ok=false` 而世界已变 ⇒ 记 `failed` 且 `harvested={}`：回执判定**先于**重观测 ⇒ 属
  "回执优先于观测"的误报失败（fail-closed 方向，不产假绿）。

**② 判据偷换** — 5/5 PASS（四类差分 + 旧字段保留）
- 2a 裸 `ripe=true`/`ready=false` ⇒ 不是目标、`harvest` skipped；2b `ripe=false`/`ready=true` ⇒ 是目标
  （旧口径会漏收）；
- 2c farm `readyCrops=0`/`ripeCrops=5` ⇒ 农场级熟作物 `(0,0)`（不吃旧字段）；2d 反向 `(0,5)`；
- **2e【口径】**旧 Mod 缺 `readyCrops` ⇒ 退回 `ripeCrops=3`（作者用例⑩，兼容性代价，见 §6）；
- `ripe`/`Dead`/`Watered`/`ripeCrops` 字段**未被删**（Contracts 只增不改，grep 三处残留裸 `ripe`
  均非判据：`farmwork.py:1370` 状态指纹、`longrun.py:1151` 陈旧 docstring、`planner.py:582/:1077` 标签表）。

**③ 缺字段 fail-closed** — 3/3 PASS
- 3a 缺 `ready` ⇒ 无目标 + `skipped` + reason `这一格缺 ready 字段（Mod 判不了是否可收）⇒ 不摘`；
- 3b `ready=null`（Mod 自己判不了）⇒ 不摘；3c `tile_ready`/`harvest_tool` 纯函数语义。

**④ 同格上限** — 5/5 + 1 自造
- 4a 同格试满 `MAX_TILE_ATTEMPTS=2` ⇒ 进 `harvest_gave_up` + **恰 1 条** journal（`limit=2`）；
- 4b 之后不再是目标、不在 `_pending_work`、无守卫理由；
- **4c【核心】**`_leftover("harvest")` **仍如实算它**（窗口内 ⇒ `no_unmet_stages` 不会被洗）；
- 4d 守卫解钉：允许收工且理由 `no_work:确实找不到可做的活…`；4e 该格不在 `blocked`/延后集合里；
- **4f【自造】**放弃后**离开观测窗口**（`window_has_tile=False`）⇒ `now_leftover=[]`、`reasons=[]`、
  `guard=no_work`，而 `farm_scan()["readyCrops"]==1`、`gave_up=[(60,10)]` ⇒ **诚实性只成立于窗口内**（§5 NIT-1）。

**⑤ 守卫：不许被钉 / 不许变假阴** — 2/3 PASS + 1 INFO
- 5b 真可收且没试过 ⇒ 守卫照旧拒绝收工（`reasons=['有 1 格作物熟了']`）⇒ 没修成假阴；
- 5c 放弃 1 格、另 1 格真可收 ⇒ reasons `农场口径还有 2 格熟作物（当前窗口只看到 0 格）` ⇒
  按数量扣**不会抹平别的格**；
- **5a【INFO】**`_unfinished_work()` 仍为 True（用未扣 `harvest_gave_up` 的 farm 级计数），与
  `work_reasons`（已扣）口径不一致；但 gave_up 需要同格 ≥2 次非 skipped 失败、这些失败步计入
  `farm_actions_today`（实测 2）⇒ `_do_sleep` 的 `require_work` 分支实际恒过 ⇒ 潜在/防御性不一致（§5 NIT-2）。

**⑥ 镰刀类** — 3/3 PASS
- 6a `harvestMethod="Scythe"` ⇒ 走 `use_tool(tool="scythe")`、`interacted=[]`、作物消失、`swings=1`；
- 6b 镰刀类但 `ready=false` ⇒ **一刀都不挥**（没造出新的"挥空报 ok"）；6c 镰刀路径 `acted=false` ⇒ `failed`。

## §4 逐条对卡面：10 条单测 + 3 个变异（我自己复现）

- 作者用例 `tests/test_longrun.py:8608 TestTask170HarvestReady` 10 条：与探针 1c/2a/2b/2c/3a/4a/4b/6a/2e
  一一对上；**10/10 通过**。
- **变异装置**：作者 docstring 引用 `scratch/_t170_mutate.py`，实测 `Test-Path` = **False**（文件不存在）
  ⇒ 我自建 `scratch/_t171_mutate.py`（拷 `brain/`+`tests/` 到独立临时树 → 注入 → 跑同一测试类）。
  结果（`scratch/_t171_mut_out.txt`，每个变异的完整输出在 `_t171_mut_*.txt`）：

| 变异 | 命中 | rc | 红数 | 红在哪些用例 |
|---|---|---|---|---|
| control（无变异） | – | 0 | **0** | – |
| m170a `tile_ready` 换回裸 `ripe` | 1 | 1 | **5** | `test_missing_ready_field_is_fail_closed`、`test_not_ready_crop_is_not_a_harvest_target`、`test_regrow_forage_and_dead_shapes_are_not_harvest_targets`（3 个子形态各红一次） |
| m170b 去掉 `_note_harvest_gave_up` 调用 | 1 | 1 | **3** | `test_gave_up_cap_is_journalled_and_the_tile_stops_being_chosen`、`test_guard_is_not_pinned_by_an_unharvestable_crop`、`test_leftover_still_counts_the_gave_up_tile` |
| m170c `sleep_guard` 不扣 `harvest_gave_up` | 1 | 1 | **1** | `test_guard_is_not_pinned_by_an_unharvestable_crop` |

⇒ 三个变异**都不是空转**，红数 5/3/1 与作者自报逐字一致；m170c 精确落在"守卫解钉"这一条上。
**NIT-4**：作者 docstring 引用的变异脚本不存在（文档-实物不一致，建议补脚本或改文案）。

## §5 点名"看起来修好、其实只是把判据放宽"的地方

**NIT-1（唯一实质放宽，不阻塞）**：`harvest_gave_up` 是一条**新的部分豁免通道**——
`work_reasons`/`sleep_guard`/`_farm_totals` 都按"数量"扣掉已放弃的格（`ripe_live = ripe − len(gave_up)`），
而 `_leftover("harvest")` 只在**窗口可见**时才算它。探针 4f 实证：放弃格一旦离开窗口（人回 FarmHouse），
当天可以 `no_work` 收工（`reasons=[]`），而 `farm.readyCrops` 仍是 1 ⇒ 只要当天有 ok 步/无活证据，
**这一天可能被判 `verified=true` 且农场仍留着一格可收作物**。放宽的边界之所以可接受：
①它需要游戏自己两次拒绝 `interact`（`acted=false`/`no_action`）才成立，属"如实放弃"家族（task-52/63 同族）；
②作物不丢——次日它重新成为目标；③三件事都有留痕（`harvest_gave_up{attempts,limit,codes}` + `rep.notes`）；
④**工具链侧已有 info 级警告**：`tools/analyze-longrun.py:4588` 收 `warn_gave_up_but_verified_lines`
（并在 `:5331-5333` 明写"`verify-run3` 对 `harvest_gave_up` 零命中 ⇒ 本工具不判红、不进 rc"）。
我实测 `tools/verify-run3.py` 对 `harvest_gave_up`/`ready`/`readyCrops`/`ripeCrops` **零命中** ⇒ 账本层
不判红、不进退出码（既有 ledger-trust 类，非新增洗白通道）。建议（0.7.34 择一，随 Lead 定）：
(a) 保持现状 + 把 analyzer 的 `warn_gave_up_but_verified` 写进口径表当 info；
(b) 收紧 `_leftover("harvest")`：gave-up 格即使在窗口外也计入 leftover（`no_unmet_stages=False`，
    代价是"如实放弃"的一天又拿不到绿）。

**NIT-2（潜在不一致）**：`_unfinished_work()` 未扣 `harvest_gave_up`（探针 5a：`unfinished=True` 而
`reasons=[]`）。可达性分析：gave_up 需同格 ≥2 次非 skipped 失败，这些步计入 `farm_actions_today`
（实测 2）⇒ `_do_sleep(require_work=True)` 恒过，**现实不可达**；建议顺手对齐口径。

**NIT-3（Mod 侧 fallback 漏洞，只能代码读）**：`CropMeta.Ready()` 的等价字段 fallback 要求
`fullyGrown/dayOfCurrentPhase/currentPhase/phaseDays/dead` 非 null，但第 ④ 条 `forageCrop && whichForageCrop=="2"`
在 `forageCrop`/`whichForageCrop` **读不到**时既不判否、也不返回 null ⇒ 理论上可能把"采集形态 2"报成
可收，与 docstring"任一判据缺项 ⇒ null"字面不符。反射路径是主路（`readyForHarvest()` 拿得到时不走 fallback），
旧 Mod/反射失败时才暴露；建议 0.7.34 与其"缺项 ⇒ null"的承诺对齐。

**INFO**：1c 的"回执优先于观测"误报失败（fail-closed 方向）；2e 旧 Mod 退回 `ripeCrops`
（四类形态 bug 在旧 Mod 上仍在，属兼容性代价）；`WorldSnapshot` 在 `ready=null` 时 `Tool="can"`
（会被当"该浇水"，fail-open 但无害）。

## §6 残余风险

1. **旧 Mod 路径**：`CropMeta` 反射不可用 + 判据字段缺项时退回 `ripeCrops`/裸 `ripe` ⇒ "复收冷却/末阶段/
   枯死/采集形态 2"四类假"熟"在老版本 Mod 上依旧存在（能收但脑会去 attempt ⇒ 被新回执判据挡住，不至于假绿）。
2. **真机未验**：`[60,29]` 同格形态的真机证据要等 task-173（本卡只有假世界 + 离线账本）。
3. **analyzer 桶**：`harvest_gave_up` 进桶是 task-172 的事；提交态全量 `889/2 红` 即此，工作树已 0 红。
4. **NIT-1 的窗口依赖**（见 §5）：若 run A/B 的尾链里出现"放弃格 + 在窗口外收尾"的日子，需要人工看
   `analyze-longrun` 的 `warn_gave_up_but_verified` 行。

## §7 结论：0.7.33 能不能据此冻结

**可以**。六条通道全部实测（25/25），回执洗白、判据偷换、缺字段 fail-closed、同格上限真封、
守卫解钉不假阴、镰刀不造挥空全部成立；10 条单测 + 我自建的 3 个变异（0/5/3/1 红）证明判据不是空转。
唯一实质放宽是 NIT-1（`harvest_gave_up` 部分豁免 + 窗口依赖），属"如实放弃"设计内家族、作物不丢、
有 journal 留痕、analyzer 已有 info 警告、verify-run3 不据此产假绿 ⇒ **判 PASS-WITH-NITS，无必修项**；
建议把 NIT-1 按 info 口径记账，是否收紧留给 0.7.34。

## §8 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
Set-Location "D:\Deepseek Harness Workspace\星露谷游戏自动化"
$env:PYTHONUTF8="1"; $env:PYTHONPATH="$PWD\brain"
& $py -W error::SyntaxWarning scratch\_t171_probe.py      # 期望 PASS=25 FAIL=0, rc=0
& $py -W error::SyntaxWarning scratch\_t171_mutate.py     # 期望 control 0 / m170a 5 / m170b 3 / m170c 1
& $py -W error::SyntaxWarning -m unittest tests.test_farmwork tests.test_longrun tests.test_planner
$env:PYTHONPATH=""
dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental
```

## §9 越界与写盘

只写 `docs/_review-task170.md` 与 `scratch/_t171_*.py|txt`；未改 `brain/`、`mod/`、`tools/`、`tests/`、
`logs/`、`docs/00-开发日志.md`、`docs/_run6-criteria.md`；未跑游戏、未碰桥、未 bump。
