# task-81 独立验收：task-78（`bound_basis` 上界基数 + `encircled` 判据文案诚实化）

- **对象**：`595db16`（task-78，dev-coder 交付；父 `0004bd2` / `5bd669f`）
- **验收者**：deputy-lead（只读 `brain/`/`mod/`/`tools/`/`tests/`，只写本文件 + `scratch/`）
- **判定**：**PASS-WITH-NITS**（卡面 7 条全过；NIT-1 在**工具侧**、非本卡引入）

## §1 基线（我亲跑）

| 项 | 读数 |
| --- | --- |
| `git show --stat 595db16` | `brain/agentfarm/farmwork.py` +52 / `longrun.py` +113 / `tests/test_farmwork.py` +32 / `tests/test_longrun.py` +191 = **4 files, +346/−42** |
| 范围检查 | `git show --name-only 595db16` 对 `manifest\|bridge\.py\|^logs/\|00-开发日志` **零命中** ✅ |
| SHA256（前 16，与自报逐字一致） | `farmwork.py 404896339FADB1E0`(137282 B)、`longrun.py A10CA88E0628CE68`(223103 B)、`test_farmwork.py 2880E5C592621D87`(102739 B)、`test_longrun.py 7D88B2EAB076B523`(224323 B) |
| `py_compile -W error::SyntaxWarning`（brain/agentfarm + tests 全量） | **exit 0** |
| `unittest tests.test_farmwork tests.test_longrun` | **Ran 225 / OK**（与自报一致） |
| `unittest discover -s tests` | **Ran 523 / OK**（与自报一致） |
| 工作树 | HEAD = `595db16`；` M mod/AgentFarm.Bridge/manifest.json`（Lead 的 0.7.26 bump，非本卡）；`?? scratch/_t72_tool_fix.py`、`?? scratch/_t81_{probe,b,adv}.py` |
| 未跑 | `dotnet build`（本卡未碰 `mod/`，无新增 Mod 代码；dev-coder 报 0 警 0 错） |

## §2 A 段：逐条打勾

1. **越界** ✅ —— 见 §1 范围检查（4 个文件之外零改动）。
2. **亲跑读数** ✅ —— 225 OK / 523 OK / `py_compile` 0，全部由我自己执行（不引用自报）。
3. **字段与公式对账** ✅
   - 阶段级：`brain/agentfarm/longrun.py:2223` `"bound_basis": sum(1 for s in all_steps if s.attempted and not s.encircled)`；`:2225` `encircled_tried`；`:2229` `engaged`（注释写明只作证据）。
   - 日级：`:3084 attempted_steps = Σ stages[].attempted`、`:3085 bound_basis_steps = Σ stages[].bound_basis`、`:3087 rep.bound_basis`、`:3088 unreachable_bound = max(5, int(0.2 * bound_basis_steps))`；refused 侧同基数 `:3112`；`unmet_leftover` `:3127`。
   - 三个出口都写：`unreachable_summary` `:3139`、`refused_summary` `:3131`、`encircled_summary` `:3161`（后者另有 `tried_open_steps` `:3162`）；`day_end.bound_basis` 见 §3 实测（真值 25）。
   - **`attempted` 语义一字未动**：阶段级 `:2200` 与日级 `:3084` 都仍是"发起过的步数"，只换分母。
   - 逐格 `encircled` journal 带 `kinds`/`tried_open`：`main/agentfarm/farmwork.py:1097-1103`（`r.tried_open = len(cleared)`、`r.encircled_kinds`、reason 照观测写）⇒ 日级 `longrun.py:2244-2253` 的 `encircled_stage`。
   - ⚠️ NIT-2：`day_end` **没有** `attempted` 字段（`:3084-3088` 只写 `bound_basis`/计数）⇒ 工具的 `attempted_total` 回退 Σ stages（不影响判定）。
4. **两个假世界（跑真代码）** ✅ —— 见 §3（A 段诚实化 + B 段整天记账）。
5. **回归** ✅ —— `git diff -U0 595db16^ 595db16 -- tests/`：**删除行只有 1 行**，且是旧的不实断言 `self.assertIn("树/桩/大石", r.reason)`（task-78 正是要删它）；**没有任何 `def test_` 删除/改名**，其余断言零放宽。
6. **对抗反例 ≥2** ✅ —— ADV-1/2/3 全被工具拦住（见 §3.3）。
7. **判定格式** ✅ —— 本文件 + 短 hash 回报。

## §3 B 段：对抗实验（全部是我自己写的探针，可指向别的树变红）

### 3.1 A 段 —— 判据文案诚实化（`scratch/_t81_probe.py`）

| 场景 | task-78 之前（快照 `scratch/_t77_snap`） | `595db16` |
| --- | --- | --- |
| 四邻 `weed` 且 `standable=false`（`clear((62,10))`） | `code='encircled'`，reason 写「四邻被不可清障物占住（**树/桩/大石一类**…）」、`as_dict` 无 `tried_open`、0 次 `use_tool` ⇒ **红** | reason 写「…；四邻实际 kind=`['weed','weed','weed','weed']`；已试开路 0 次（上限 4）」，`r.tried_open=0`、0 次挥动 ⇒ **通过** |
| 对照：把 `(61,10)` 改成可站可清 | —— | `code='ok'`（`已清掉（kind weed → 未知；第1次请求→未知）`） |

> 我原先断言"`as_dict()` 必带 `tried_open`"过严：`farmwork.py:468-469` 是 `if self.tried_open:` 才输出（0 时省略，属性仍在）。B 段实测到 `tried_open=1`（见下），该字段在非零时确实序列化。

### 3.2 B 段 —— 真代码跑一整天（`scratch/_t81_b.py`）

世界（我自己搭）：14×14 杂草海 + 外圈也铺满（保证边缘格子四邻都"观测到"）+ 5 格"北邻留空"；
客户端把**整片海 + 那 5 个北邻**都设成 `move_to ⇒ BridgeError(status="unreachable")`；worker = 真 `FarmWorker`。

实测（`plot_size=N`）：

```
attempted=564  encircled_steps=539  bound_basis=25 (= 564 − 539)
rep.unreachable=20  rep.unreachable_bound=5  unreachable_exempt=5
旧口径 max(5, 0.2*attempted) = 112   新口径 max(5, 0.2*bound_basis) = 5
day_end[bound_basis]=25  day_end[unreachable]=20  day_end[unreachable_bound]=5  day_end[unreachable_exempt]=5
逐格 encircled journal 539 条，样例 tried_open=1、kinds=['weed','weed','weed','weed']
encircled_summary {count:19, attempted:564, bound_basis:25, engaged:11, tried_open_steps:433}
unreachable_summary {count:20, bound:5, attempted:564, bound_basis:25, exempted:5, engaged:11}
unreachable ∩ encircled = ∅
refused_summary 0 条（本世界没有"游戏拒绝"⇒ 该出口未实测，仅与源码 :3131 + 工具白名单对账）
```

**结论**：`encircled` 不再抬高豁免上界（5 而不是 112），且那批真不可达的格子里**界内 5 格仍被豁免**、超界部分不被豁免（fail-closed）；两套集合互不重叠。

### 3.3 对抗反例（`scratch/_t81_adv.py`，喂**仓库** `tools/verify-run3.py`）

| 反例 | 伪造内容 | 结果 |
| --- | --- | --- |
| ADV-1 | 账本 `bound_basis=564`（谎报成 `attempted`，把 encircled 从分母洗掉）+ 上界 112 + checks 全 true | **exit 1**：`不可达豁免上界账本=112 > 自算=5（bound_basis=25 = attempted 564 − encircled 539）⇒ 上界被放宽` |
| ADV-2 | 账本**不写** `bound_basis`，直接用旧口径上界 112 | **exit 1**：同上（工具自算 25/5） |
| ADV-3 | 新口径写对，但用"encircled 很大"解释掉 leftover=539 + `no_unmet_stages=true` | **exit 1**：`no_unmet_stages=True 与自算不一致（…扣掉不可达豁免 0 + 锄不动豁免 0 后剩 539 格…）` |
| ADV-4（取证用） | 账本 `bound_basis=564` 谎报，但上界写成自算值 5 | 点名「上界基数账本 bound_basis > 自算」的行数 = **0**（exit 1 来自别的伪造痕迹）⇒ NIT-1 |

## §4 NIT（每条含行号 + 影响 + 建议）

- **NIT-1（工具侧，非本卡引入；建议修）**：`tools/verify-run3.py:521-524`
  `basis = min(int(_basis), basis_self) if basis_self else int(_basis)` 之后再判 `if basis != basis_self and int(_basis) > basis_self`
  ⇒ 只要 `basis_self > 0`，`min()` 已把 `basis` 钳成 `basis_self`，该 problem **永不触发**（ADV-4 实测点名 0 行）。
  影响：账本谎报 `bound_basis` 被静默钳紧（方向 fail-closed，**不构成洗白通道**），但"账本说谎"没有留痕，事后审计看不到。
  建议：先比较再钳（`if int(_basis) > basis_self: problem(...)`，然后 `basis = min(...)`）。
- **NIT-2**：`day_end` 不含 `attempted`（`longrun.py:3084-3088`；`attempted` 只在 stage `:2220` 与三个 summary `:3131/:3139/:3161`）⇒ 工具回退 Σ stages。判定不受影响，字段面略不一致。
- **NIT-3（观察，非缺陷）**：我的 B 世界里除那 5 格外另有 15 格被判 `unreachable`（外圈/开路一次仍不通）⇒ 密集地形下"被围住"与"走不到"会互相转化，卡面"少量真 unreachable"的格数不固定。
- **NIT-4（记录）**：`encircled_tried` 真实可达 > 0（B 段 433）；task-68 时观测到"0 次"只是那一种布局的产物，不是字段恒零。

## §5 判定

**PASS-WITH-NITS**：卡面 7 条全部满足（越界 ✅、读数 225/523 OK ✅、字段与公式对账 ✅、两个假世界真代码 ✅、回归零改名零放宽 ✅、≥2 对抗反例全被拦 ✅）；`bound_basis` 的口径修正**真的堵住了 encircled 抬高上界**（112 → 5）且 fail-closed（超界不豁免），文案诚实化达标。
唯一建议修的是 **NIT-1**（工具侧既有守卫失效，非本卡引入），修不修都不影响 run7 的判定正确性。
