# task-7 独立验收（deputy-lead；收割收窄版）

- 验收人：deputy-lead（只读代码/只写本文件与 `scratch\`）
- 基线：HEAD=`8f1134a`；被验收对象 = **工作树在制**（未提交）
- 结论：**轻量冒烟 PASS**；**完整验收（IL/口径 + 与 task-8/19 合并核对）待整链代码冻结后做一次**
- 本次复核的两条环境事实：`manifest.json:4` = `"Version": "0.7.21"`、`brain/agentfarm/bridge.py:39` = `MOD_VERSION_EXPECTED = "0.7.21"`（**未 bump**，Lead 独占，符合裁决；但"行为已变、版本未 bump"⇒ 现在部署会造成版本断言失真）

## 0. 在制范围（`git diff --stat HEAD`）

| 文件 | 增删 |
|---|---|
| `brain/agentfarm/bridge.py` | +15/-…（纯 docstring） |
| `brain/agentfarm/farmwork.py` | +100/-… |
| `mod/AgentFarm.Bridge/UseToolSkill.cs` | +164/-… |
| `tests/test_farmwork.py` | +112/-… |
| `tests/test_longrun.py` | +41/-… |
| 合计 | **390 插入 / 42 删除** |

- `git status --short` 只有上述 5 个 ` M` + 一个未跟踪 `?? scratch/run_il_probe.py`（scratch 目录，非生产件；task-7 的 writeScopes 不含 scratch\，**仅备注、不算缺陷**）。
- `mod/AgentFarm.Bridge/manifest.json` 未被任何人改（mtime 2026/10/11 21:07:23）。
- 收窄 delta（第二次提交）**只碰 `UseToolSkill.cs`**：该文件 mtime `10/13 00:32:33`，其余四个在制文件停在 `00:29:14`–`00:29:50`。

## 1. 冒烟证据（我独立跑；命令见文末）

| 项 | 结果 |
|---|---|
| `py_compile`（brain\agentfarm + tests 共 18 个 .py） | **exit 0** |
| `python -m unittest discover -s tests` | **Ran 195 tests in 2.156s / OK**（任务书基线 185，未降） |
| `dotnet build -c Release --no-incremental` | **0 个警告 / 0 个错误**，`bin\Release\AgentFarm.Bridge.dll` 重建 |
| manifest / 版本断言 | 均未变（见上） |

## 2. 条款逐条（Lead 收窄版四条 + 任务书 ⑥）

### ① 非近战起手路径与 HEAD 逐字未变 —— **PASS**
证据：`scratch\_review_cmp_use_tool.py`（我写的对账脚本，只读 `git show HEAD:…` 与工作树文件，按"签名 + 花括号配对"切函数逐行 `difflib` 比对）。输出要点：

- `private void Swing()`：HEAD `260-279`（20 行）→ 在制 `290-343`（54 行）。差异**只有两处**：
  1. 顶部新增渐黑门 `if (WorldFading()) { this._deferredByFade = true; return; }`（`UseToolSkill.cs:297-300`，在 `this._swings++` **之前**，不计刀数）；
  2. `// 2) 调游戏自己的"使用键"入口` + `Game1.pressUseToolButton();` → `bool melee = p != null && p.CurrentTool is MeleeWeapon;`（`:333` 附近）+ `if (!melee) { Game1.pressUseToolButton(); } else if (!this.BeginUse(p)) { Game1.pressUseToolButton(); }`。
- HEAD 里 `faceDirection(dir)`（面向目标格）、`this._swings++`、`try/catch` 结构与日志文案 **逐字未变**（diff 里是上下文行，无 -/+）。
- `melee` 的求值失败/读不到 player 时默认为 `false` ⇒ **默认走已验证路径**，符合 Lead 的收窄要求。
- `private bool Done()`：HEAD `427-455` → 在制 `563-595`，差异**只有新增的那一条 Grass 判据 + 注释**，其余（`hasObject`/`Tree`/`FruitTree`/`ResourceClump`/`hoe`/`can` 分支与 `return true`）逐字相同。
- 新增 `private bool BeginUse(Farmer p)`：仅工作树有，`UseToolSkill.cs:375-397`。
- 说明：脚本里我按 `private static bool ClassifyTile` 找签名（实际是 `private static string ClassifyTile(Point p)`，`UseToolSkill.cs:509` 附近），故该函数未参与比对；它不在本次改动范围内。

### ② `Done()` 的 Grass 判据 —— **PASS**
`UseToolSkill.cs:591` = `if (tf is StardewValley.TerrainFeatures.Grass) return false;`（注释 `:588-590` 说明"多刀特征，numberOfWeeds 减到 0 才移除"）。
⇒ 草格上"回执 ok"在结构上**不可能**成立：`hasObject` / `Tree` / `FruitTree` / `ResourceClump` / `Grass` 五道 `return false` 之后才 `return true`。
成功文案也已按 Lead 口径改：`UseToolSkill.cs:114` = `现在**上面已经没有东西了**（kind=「{KindNow()}」）`，另 `:119` 带 `起手={StartedText()}`。

### ③ 刀数口径（脑侧 4 次请求 × Mod 单请求 ≤6 刀）—— **PASS（1 条证据口径 nit）**
- 脑侧：`farmwork.py:67 MAX_CLEAR_SWINGS = 4`、循环 `farmwork.py:603 for i in range(1, MAX_CLEAR_SWINGS + 1)`。
- Mod 侧：`UseToolSkill.cs:54 private const int MaxSwings = 6;`、`UseToolSkill.cs:170 if (this._swings >= MaxSwings)` ⇒ 单次请求最多 6 刀。
- 最坏 = 4×6 = 24 刀/格；该上界只在"Mod 回 ok 而世界没变"（`LyingClient`）时才可能逼近 —— 真机 grass（普通镰刀 -1、金镰刀 -2，`numberOfWeeds ≤ 4`）**1 次请求**就够，所以这不是性能风险。
- **nit（口径，非缺陷）**：journal 里的 `第N刀→kind`（`farmwork.py:619 traces.append(f"第{i}刀→{kind_now or '未知'}")`）实际是"第 N 次**请求**"，且超时/异常时**根本没挥**；真实刀数只存在于 Mod 回执原文里（`UseToolSkill.cs:173` 的 `「…」挥 {_swings} 次无效（UsingTool=…）`，经 `farmwork.py:1067 _receipt_of` 带进 journal）。建议把这段文案改成"第 N 次请求"或在 reason 里显式带 `requests=/swings=`，否则读 journal 的人会把请求数当刀数。

### ④ `TILE_INERT_STATUSES` / `ENV_BLOCK_STATUSES` 分离 —— **farmwork 层 PASS / 集成层 FAIL（补记见下方 §2④-补）**
- `farmwork.py:71 TILE_INERT_STATUSES = ("tool_ineffective", "precondition_failed")`（封格）
- `farmwork.py:75 ENV_BLOCK_STATUSES = ("no_save", "ui_modal", "world_fading")`（记 `failed`、**不封格**）
- Mod 真正发出的 status 全集（`UseToolSkill.cs`）：`timeout`(:138)、`world_fading`(:165)、`tool_ineffective`(:194)、`error`(:206)、`no_save`(:218)、`ui_modal`(:221)、`precondition_failed`(:260,:272) ⇒ 两个集合的每个成员都有 Mod 出处，**无悬空常量**。
- 分离生效：`farmwork.py:629-631` 命中 ENV 立刻 `break` 并置 `env_block`；`:633-637` 记 `r.code = "failed"`、**不设 `proven_inert`** ⇒ 上层不封格、下轮可重试。
- 单测覆盖：`tests/test_farmwork.py` 的 `test_env_block_list_covers_mod_codes`（`world_fading` ∈ ENV；`tool_ineffective`/`precondition_failed` ∉ ENV）+ env_block 用例断言 `("failed", False, True)`（failed、无 proven_inert、不封格）。
- **nit（口径待裁）**：Mod 的 `timeout`(:138) 与 `error`(:206) 既不在 TILE_INERT 也不在 ENV ⇒ 连续 4 次超时后循环自然走完，落到 `farmwork.py:641-646`，仍记 `skipped` + `proven_inert = True`（why = `连挥 4 刀`）⇒ **"4 次 15s 超时"被当成"这格已被证明干不动"并封到当天结束**（最坏还能烧 60s/格）。同一份代码 `:633-636` 自己的教条是"环境挡路不算这格干不动"，两者不完全自洽。建议二选一：(a) `timeout`/`error` 并入 ENV 可重试集合；(b) 保持现状但把 `statuses_seen` 写进 reason，让 journal 能区分"4 次真挥"与"4 次超时"。**此项不影响 run3 正确性判定，属口径/健壮性。**

#### ② ④ 补记（deputy-lead 事后追查；**本条把 ④ 从 PASS 降为集成层 FAIL**）

⚠️ 行号漂移：本节上文引的 `farmwork.py:629-631/:633-637/:641-646` 是冒烟当时的行号；当前工作树已右移约 70 行 —— ENV 命中判据 = `farmwork.py:702`、env_block 出口 = `farmwork.py:706-710`、挥满出口 = `farmwork.py:712-720`（`TILE_INERT_STATUSES`/`ENV_BLOCK_STATUSES` 仍在 `:71`/`:75`）。

**结论：farmwork 层承诺的"环境挡路不封格"在 longrun 集成层不成立。**

1. 证据（当前工作树，逐行核对）：
   - `farmwork.py:706-710`：env_block（`no_save`/`ui_modal`/`world_fading`）出口是 `r.code = "failed"`，不设 `proven_inert`。
   - `farmwork.py:274-276`：`StepResult.failed` 就是 `code == "failed"` ⇒ 这些步在 longrun 眼里属于 `s.failed`。
   - `longrun.py:842`：`if not (s.failed or s.proven_inert) or not s.tile or s.action not in ("till","clear","sow"): continue`；`:845` 只在 `key in self.blocked or before.get(key) != after.get(key)` 时跳过；`:847` `self.blocked[key] = f"{s.action} 无效：{s.reason[:80]}"`（docstring `:833-836` 明写"两种来源都要封：`s.failed` …；`s.proven_inert` …"）。
   - 调用点 `longrun.py:934 self._mark_blocked(snap, self._snap(), res.steps, rep)`：**每轮**都调，覆盖 `run_stage` 刚产出的全部步。
2. 推论：渐黑/模态时这一格**必然**没变（`before == after`）⇒ `longrun.py:847` 当场封格到当天结束。所以 task-7 条款④的"不封格"**只在本层（farmwork）成立，在整机行为上被抵消**；这也解释了为什么"环境挡路 ⇒ 下轮可以再试"在 `blocked` 语义下不可能发生。实机旁证：`logs\longrun-3day-llm-run2.jsonl` 有 14 条 `event=blocked`（行 19/20/37/43/56/61-65/70/71/81/82，reason 全是 `清不掉：这一格还是 grass` 或 `四邻都站不过去`）⇒ 该封格路径在真机上确实被走到；换成 env 类 reason 时同样会写进去（旧代码里 grass 走的是 `skipped+proven_inert`，env 走 `failed`，两条都在 `:842` 的准入集合里）。
3. 对 **task-22** 的直接影响：把 `timeout`/`error` 从 `skipped + proven_inert=True` 改成 `failed + proven_inert=False`，只是把封格来源从 `s.proven_inert` 换成 `s.failed` —— **`longrun.py:847` 仍会封格**。task-22 正文"**不必**改 `longrun`：`failed` 不封格"是**事实错误**，按现文实现拿不到它要的"不封死这一格"。另 `_count_attempts`（`longrun.py:855-867`，`:864` 同样只认 `s.failed or s.proven_inert`）会把环境/无结论失败计入 `MAX_TILE_ATTEMPTS`（**= 2**，`longrun.py:62`；重试过滤 `:659-663`、`capped` 列表 `:961-962`、journal `:991`、文案 `:1006-1007`）⇒ **同一格两次瞬时渐黑/超时**就被推到 `capped` ⇒ `stage_exhausted` ⇒ leftover>0 ⇒ 当天被杀（即使封格被修好，这条配额也还在）。
4. 修法建议（**任一都要动 longrun**）：
   - (a) 给 `StepResult` 加显式标记（如 `env_block: str = ""` / `inconclusive: str = ""`，并入 `as_dict()` 落盘），`longrun.py:842` 与 `:864` **跳过带标记的步**（既有先例：docstring `:829-830` 的"浇水失败不封格"就是这类豁免）；
   - (b) 或让"环境/无结论"不写 `failed` 也不写 `proven_inert`（保持 `skipped`）—— 但 `StepResult.attempted`（`farmwork.py:278-281`）= `code != "skipped" or proven_inert`，那它连"发起过"都不算；因此需 Lead 明确定"环境类失败要不要占当天尝试配额"，否则修好封格又会从 `capped` 侧翻车。
5. 对 **task-15 ④** 的直接影响：`_stage_tiles` 排除 blocked（`longrun.py:662 if t not in self.blocked`）⇒ 已被封的格子**不会再进目标集**，④ 的"先 `_clear_modals` 再重跑同一批格子"会重跑 **0 格**（journal 只留一条空转 `env_retry`）。⇒ ④ 必须与上面的解封改动**同批落地**，或显式按 tile 列表重跑、绕过 `_stage_tiles`。

### ⑤ journal 带 Mod 回执原文 —— **PASS**
`farmwork.py:1067 def _receipt_of(res)` = `f"{res.get('status') or 'ok'}: {str(res.get('reason') or '')[:200]}"`；每次请求都写 `r.receipt`（`farmwork.py:607`），失败分支 `:614`（`BridgeError`）；`:646` 把回执拼进最终 reason。

### ⑥ 版本未 bump —— 事实陈述（Lead 裁决，不算缺陷）
`manifest.json:4` = `0.7.21`、`bridge.py:39` = `0.7.21`，行为已变 ⇒ **此刻若装机，`MOD_VERSION_EXPECTED` 断言与真实行为不符**；由 Lead 在整链冻结、我的完整验收通过后统一 bump + `tools\deploy-mod.py`，**0.7.22 装机内容 = task-7（收窄后）+ task-8 + task-19**。

## 3. 文档 nit（不影响行为；`dotnet build` 0 警）

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| D1 | `UseToolSkill.cs:536-544` → `:546` | `Done()` 的 XML `<summary>`（"按这一格现在应该长成什么样判断做完了没…"那段）现在挂在 `private string KindNow()` 头上；`private bool Done()`（`:563`）自己没有 XML 注释 | 把 `536-544` 移到 `:563` 上方（上一轮我报的同一处，WorldFading 那条已归位到 `:554-557`） |
| D2 | `UseToolSkill.cs:20-24` | 文件头注释已更新，明确区分"非近战走 `pressUseToolButton()` / 近战走 `BeginUse()`" | **已修，无需动作** |

## 4. 完整验收待办（整链冻结后；含 Lead 新追加的 task-15 ④ 对账）

1. **④ 引入后必须保持的不变式**：`tools\verify-run3.py:151-155/:190-196` 用 `day_end.failed_steps` 与 `sum(day_end.stages[].failed)` 交叉核对 ⇒ longrun 必须继续满足 `rep.failed_steps == sum(stage["failed"])`（`longrun.py:152-154` 的 property 决定）。若把 `failed` 改成"只数目标仍未完成（`s.tile in leftover`）的失败步"，两侧**同步变口径**即可，交叉核对不会误报；**但**要确认 `env_block` 另计的字段不会与 `failed` 语义打架。
2. **工具侧盲区**：`tools\verify-run3.py` **不认** `env_block` 字段（它只读 `verified/checks/ended_by/sleep/跨日/day_end.stages/final`）⇒ ④ 落地后建议工具**打印**`env_block` 汇总（信息项，不进 `problems`、不改 exit code），否则"环境挡路但已重试做成"的日子在报告里完全看不出来。
3. **对称性 nit（工具）**：`tools\verify-run3.py:193 elif sum_failed and int(failed_field) != sum_failed` —— 交叉核对只在 `sum_failed` 非 0 时触发。反向（自述 `failed_steps=5` 而 `stages[].failed` 全 0）不会被标"账目不可信"，但 `:197-198` 仍会报"当天 stages 硬失败 5 格"⇒ **exit code 仍为 1，不会假通过**，只缺一个标签。低优先。
4. **task-9 语义不许被 ④ 改掉**：`longrun.py:965 met = bool(all_steps) and not leftover`、`:976-977 stage_no_target`、`:981-989 stage_exhausted`（leftover>0 是设计语义）与 `tests/test_longrun.py:1090-1119` 必须仍全绿；task-15 的 `zero-target` 归零只施加在 `stage_no_target`，修法 A 只动 `_leftover`（定义 `longrun.py:667`、唯一调用点 `longrun.py:953`，自包含）。
5. 合并核对：task-8（sleep 跨日）/ task-19（`checks.watered_outdoor` + `WorldSnapshot.cs` `farm.dryCrops`）与 task-7 同装 0.7.22；`git status` 出现"同一文件被两个任务同时改"立即上报 Lead。
6. **封格口径必须先修再跑 ④（见 §2④ 补记）**：`longrun.py:842/:864` 目前把"环境挡路 / 无结论"的失败当封格与配额依据，与 `farmwork.py:706-710` 的承诺相矛盾；task-22 与 task-15 ④ 都建立在这个前提上，故完整验收时必须逐条确认：(i) 环境/无结论步**不写 `self.blocked`**；(ii) 不占 `MAX_TILE_ATTEMPTS`（或 Lead 明确它占）；(iii) `env_retry` 真能重跑目标格（`longrun.py:662` 的 blocked 过滤要放行）；(iv) `tools\verify-run3.py` 的 `failed_steps` 交叉核对口径与 longrun 同步。
7. **标记覆盖面必须跨动作（只给 `clear()` 打标修不干净）**：这两类 status 是**全桥通用**的。按 `mod\AgentFarm.Bridge\*.cs` 的 `Fail(` 全集核对：`timeout` 出自 `UseToolSkill.cs:138`、`MoveToLocationSkill.cs:250`、`PlantSkill.cs:187`、`SleepSkill.cs:173`、`LoadSaveSkill.cs:150`、`StepMover.cs:53`；`no_save` 出自 `WorldSnapshot.cs:160`、`UseToolSkill.cs:218`、`Skills.cs:191/:436`、`MoveToLocationSkill.cs:303/:405`、`PlantSkill.cs:42/:259`、`SleepSkill.cs:135`、`BuySkill.cs:107`、`LoadSaveSkill.cs`；`ui_modal` 出自 `UseToolSkill.cs:221`、`Skills.cs:450`、`MoveToLocationSkill.cs:269/:315`、`PlantSkill.cs:262`、`StepMover.cs:54`；`error` 出自 8 个 skill；`world_fading` **只有** `UseToolSkill.cs:165`。⇒ `_mark_blocked` 只认 `till/clear/sow`（`longrun.py:842`），但 `_count_attempts`（`:864`）**不带动作过滤** ⇒ 浇水/收获/补水/移动上的一次 `world_fading`/`ui_modal` 同样推高 `tile_attempts` ⇒ `capped` ⇒ 当天被杀。验收时逐处确认这些 BridgeError 出口都按 status 分类打标（建议集中一个 helper）：`farmwork.py:679`（clear）、`:765`（till）、`:811`（plant/sow）、`:883`（water）、`:924`（harvest）、`:969`（refill）、`:560`/`:570`（move_to）、`:591`（move_to_location）；并配**非 clear 路径**的集成用例（`sow` 遇 `ui_modal`（`PlantSkill.cs:262`）不封格；`water` 遇 `world_fading` 不增配额）。

## 5. 复现命令

```powershell
$repo = "D:\Deepseek Harness Workspace\星露谷游戏自动化"
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
cd $repo; $env:PYTHONUTF8="1"; $env:PYTHONPATH="$repo\brain"
& $py -m py_compile (Get-ChildItem brain\agentfarm\*.py, tests\*.py | % FullName)
& $py -m unittest discover -s tests              # Ran 195 tests / OK
cd mod\AgentFarm.Bridge
dotnet build .\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental   # 0 警 0 错
cd $repo
& $py scratch\_review_cmp_use_tool.py            # HEAD vs 工作树 的函数级逐行 diff（条款①证据）
```

（注：pwsh 会把 `unittest` 的 stderr 汇总显示成 `[exit code: 1]`，**是噪声**；判据是 stdout 的 `Ran N tests` + `OK`。）
