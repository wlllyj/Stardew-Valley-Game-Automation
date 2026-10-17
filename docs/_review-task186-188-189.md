# task-190 独立对抗验收：task-186 / task-188 / task-189（0.7.36 冻结门）

- 验收人：deputy-lead（独立对抗验收，只看代码 + 自跑输出）
- 验收对象：`c67b85f`（task-186，brain 收获四路证据）、`e612464`（task-188，Mod `use_tool` 的 `acted/actedEvidence`）、`7f9c719`（task-189，brain loot 逐 qid 记账）；对账侧 `3ccc29b`（Lead，`tools/verify-run3.py` 净额口径）
- 开工时 HEAD：`3f3a5c0`（0.7.36 发布计划 docs）
- 判定：**PASS-WITH-NITS ⇒ 0.7.36 可以据此冻结**（无必修项；NIT 见 §5）
- 复跑入口：`scratch\_t190_probe.py`（对抗探针，`T190_ROOT` 切树、`T190_FORCE=1` 让 pre 树照跑）、`scratch\_t190_mutate.py`（自建变异矩阵 + C6c 映射复核）

---

## §1 A 段：范围与读数

### 1.1 改动范围（`git show --stat`）

| 提交 | 文件 | 规模 | 写盘范围核对 |
| --- | --- | --- | --- |
| `c67b85f` task-186 | `brain/agentfarm/farmwork.py` 64、`brain/agentfarm/longrun.py` 11、`docs/_review-task181-182.md` 15、`tests/test_farmwork.py` 115 | 4 文件 +193/−12 | brain + tests + docs，无越界 |
| `e612464` task-188 | `mod/AgentFarm.Bridge.Tests/Program.cs` 40、`mod/AgentFarm.Bridge/ClumpRules.cs` 32、`mod/AgentFarm.Bridge/Skills.cs` 158、`mod/AgentFarm.Bridge/UseToolSkill.cs` 72、`tests/test_longrun.py` 93 | 5 文件 +386/−9 | 只命中 `mod/AgentFarm.Bridge{,.Tests}/`（卡面声明范围）|
| `7f9c719` task-189 | `brain/agentfarm/farmwork.py` 37、`tests/test_farmwork.py` 148 | 2 文件 +181/−4 | brain + tests，无越界 |

越界扫描（三提交 `--name-only` 过滤 `^mod/|^tools/|manifest.json|bridge.py|^logs/|00-开发日志`）：**0 命中** ⇒ dev-coder 未 bump、未装 Mod、未动日志。

### 1.2 SHA256 前 16（工作树 = HEAD 内容）

| 文件 | SHA256 前 16 |
| --- | --- |
| `brain/agentfarm/farmwork.py` | `FA6BD05CCAB9DF25` |
| `brain/agentfarm/longrun.py` | `1F539DA6B4DEF848` |
| `tests/test_farmwork.py` | `7C503EC1AEB4CF9A` |
| `mod/AgentFarm.Bridge/UseToolSkill.cs` | `0163D54BDE2ED462` |
| `mod/AgentFarm.Bridge/Skills.cs` | `548E233BFC44BA27` |
| `mod/AgentFarm.Bridge.Tests/Program.cs` | `F2F280F292876F53` |

### 1.3 亲跑读数（原文留档 `scratch\_t190_targeted.txt`、`scratch\_t190_full.txt`）

- `py_compile -W error::SyntaxWarning`（farmwork/longrun/planner）⇒ **exit 0**
- 定向 `tests.test_farmwork tests.test_longrun tests.test_planner` ⇒ **Ran 554 tests / OK**
- 全量 `discover -s tests` ⇒ **Ran 959 tests / OK**
- `dotnet build mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --no-incremental` ⇒ **0 警告 0 错误**
- `dotnet run --project mod\AgentFarm.Bridge.Tests\AgentFarm.Bridge.Tests.csproj -c Release` ⇒ **`OK 26 断言全部通过`**，exit 0

---

## §2 B 段：FAIL → PASS 对照（三棵冻结 pre 树 vs post 树）

三棵 `git archive` 冻结树（`scratch/_t190_pre186` = `c67b85f^`、`scratch/_t190_pre188` = `e612464^`、`scratch/_t190_pre189` = `7f9c719^`），配 `T190_FORCE=1` 让"缺特性 ⇒ SKIP"的门闸失效、通道照跑，从而拿到**修复前必红**的原文。

| 通道 | pre186 | pre188 | pre189 | post（HEAD） |
| --- | --- | --- | --- | --- |
| C1a/C1b 缺格假绿 | **FAIL** | ok | ok | ok |
| C2b/C2c 白名单只凭背包差分 | **FAIL** | ok | ok | ok |
| C3 F5 措辞（缺字段/-1） | **FAIL ×4** | ok | ok | ok |
| C4d/e/f R2 loot 记账 | **FAIL ×3** | ok | **FAIL ×3** | ok |
| C5c–C5h task-188 通道 | **FAIL ×5** | **FAIL ×5** | **FAIL ×5** | ok |
| C7c F4 已注明有意口径 | **FAIL** | ok | ok | ok |
| 汇总 | `PASS=18 FAIL=17` | `PASS=30 FAIL=5` | `PASS=27 FAIL=8` | **`PASS=35 FAIL=0`**（SKIP=1，见 §4） |

修复前原文（节选）：

```
pre186 C1a  FAIL  收获成功（判据：该格 crop 已消失；该格 ready true→None）；受影响格：[[60, 29]]；
                  ⚠ 背包没有新增物品（收货可能丢了，不能出货）        ← 格已不在观测里却被当成功
pre186 C2c  FAIL  after={…'loot': {'(O)128': 1}, 'harvested': {'(O)128': 1}, 'affected_tiles': [[60, 29]]}
pre186 C3   FAIL  …；farm.readyCrops 没下降                             ← 字段缺失却写"没下降"
pre189 C4d  FAIL  loot={} waits=None                                    ← 没有真走等待轮
pre188 C5e  FAIL  出现 0 次                                              ← use_tool 未接共享 wrapper
```

post 树汇总：`PASS=35 FAIL=0 SKIP=1`（留档 `scratch\_t190_post_v4.txt`）。

---

## §3 C 段：七条作弊通道逐条实测

### 3.1 C1（F1 假绿）—— PASS

- 构造：动作后把该格从**观测**里抹掉（世界真相不变：crop 仍在），回执 `ok=true`。
- 实测：`C1a` ⇒ `ok=False code=failed`；`C1b` 文案含「不在…窗口」；`C1c` 白名单为空。
- 正对照 `C1d`：格在窗口内 + crop 真消失 ⇒ 仍 `ok=True`（**没有修成假阴**）。
- pre186 原文：`ok=True …收获成功（判据：该格 crop 已消失…）` ⇒ 洞真实存在、已被堵住。

### 3.2 C2（F3 白名单污染）—— PASS（保留 NIT-1）

- `C2b`：世界**完全没变**（作物还在）、只有背包进了 `(O)128` ⇒ 白名单必须为空。post `ok`；pre186 `harvested={'(O)128': 7}` FAIL。
- `C2c`：只有背包差分、没有格子级证据 ⇒ 不计白名单（`whitelist_bound` 语义）。pre186 FAIL、post ok。
- `C2d`：工具行不进 `sellable_slots`（红线未放宽）。
- **NIT-1（Lead 已裁定，非阻塞）**：真实收成时同一次动作里顺手入包的**无关 qid 仍进白名单**（实测 `harvested={'(O)128': 1}`，`affected=[[60,29]]`）。收紧另立 **task-193（0.7.37）**：按本格作物产物 id 归因，取不到 ⇒ `whitelist_source="unavailable"` 且本批不进白名单。

### 3.3 C3（F5 措辞）—— PASS

- `readyCrops` 缺失 / `-1`：失败文案必须写「无法判定」，不许写「没下降」。post 4 条断言全绿；pre186 4 条全红（原文见 §2）。

### 3.4 C4（R2 loot 记账）—— PASS

- `C4a`：一次动作影响多格、并入既有叠（`(O)262 +4` / `(O)178 +2`）⇒ 两笔都进 `gained`。
- `C4b/C4c`：不许再写「背包没有新增物品」；理由写明逐 qid 差分。
- `C4d`：**延迟入包**（第 3 张观测才看得到）⇒ 有界多等（`loot_waits ≥ 1`）后仍记到 `+4`。pre189 FAIL（`loot={} waits=None`）。
- `C4e/C4f`：确有丢失时如实告警（「对不上」），pre189 FAIL（写成「没有新增物品」）。

### 3.5 C5（R1 Mod `use_tool` 回执 `acted/actedEvidence`）—— PASS（三源复核）

| 断言 | 读数 |
| --- | --- |
| `C5a` C# 自检工程真跑**编译产物**且 exit 0 | ok |
| `C5b` 输出「断言全部通过」且 `FAIL ` 行为 0 | ok |
| `C5c` 纯函数 `ClumpRules.ActedEvidence` 存在（五类证据按序） | ok |
| `C5d` `acted` 由证据派生（不是 `err == null` 旧口径） | ok |
| `C5e` `interact` 与 `use_tool` 走**同一个 wrapper**（`WithActedEvidence(` ≥ 2 次） | ok |
| `C5f` 证据不可得 ⇒ `acted=false`（fail-closed） | ok |
| `C5g` 无证据 ⇒ 降级 `status=no_action`（Lead 已批准的 fail-closed） | ok |
| `C5h` R4 渲染路径不再写死 `（空）` | ok |
| `C5i` 回执 `acted=true` 但世界没动 ⇒ 脑侧 `failed`（世界证据优先） | ok |
| `C5j` 回执 `acted=false` 但世界真变 ⇒ 脑侧仍 `ok`（线索不当判据） | ok |

三源 = ①脑侧 `farmwork.harvest` 的四路证据；②Mod 回执 `acted/actedEvidence`；③世界观测差分。`C5i/C5j` 证明**判据落在世界证据上**，回执只作线索 —— 与卡面"fail-closed"要求同向。

### 3.6 C6（GAP 类 + 作者映射实测复核）—— PASS（含 GAP 观察项）

- `C6a/C6b`：存在**真跑 `dotnet run` 的行为回归**（`TestTask182ClumpRulesBehaviour`），不是只 grep 源码 ⇒ 比 task-178 的 GAP 有实质进步。
- `C6c`（作者自报映射实测复核，见 §4.2）：
  - `m188c/m188d/m188e` ⇒ 契约各杀 **1**，**符合**自报；
  - `m188a` 实测杀 **6**（自报 7）、`m188b` 实测杀 **7**（自报 8）⇒ **数字不符**（方向一致：两种变异都被杀）。
- **GAP-1（非阻塞）**：作者的 R4 契约是**纯文本断言**（`assertIn("该格原本是 {this.OriginalText()}")` + 三个 marker 串）。实测 `m188e2`（把 `OriginalText()` 的兜底改成 `return "（空）";`）⇒ **0 杀**：契约只钉模板串，不覆盖兜底值。行为层不受影响（`acted/actedEvidence` 有真行为断言），属"文本契约的残余盲区"，建议后续把 R4 改成行为断言。

### 3.7 C7（板面/文档一致性）—— PASS

- `C7a`：`checks` 键集仍是这 10 个（`slept_by_us/no_blocking_modal/no_hard_failures/unreachable_within_bound/refused_within_bound/no_unmet_stages/crops_watered/watered_outdoor/day_justified/zero_action_evidenced`），**未被悄悄加宽**。
- `C7b`：`_leftover` 仍不按认输格逐格扣减（task-168 红线未破）。
- `C7c`：F4（仅 `readySource` 变化即算成功）已在 `docs/_review-task181-182.md` 注明**有意口径**。

---

## §4 变异矩阵（自建，`scratch\_t190_mutate.py`）

### 4.1 我的通道变异（brain，探针抓）

| 变异 | 实测 | 结果 |
| --- | --- | --- |
| `control` | `PASS=35 FAIL=0`；C# 杀 0；契约杀 0 | ✅ 基线干净 |
| `m190a_f1_tile_seen_always`（`tile_seen = True`） | 红 `C1a`/`C1b` | ✅ 杀 |
| `m190b_f3_whitelist_unbound`（`if gained and tile_level_evidence:` → `if gained:`） | 红 `C2b` | ✅ 杀 |
| `m190c_f5_wording`（改成"没下降"） | 红 `C3`×2 | ✅ 杀 |
| `m190d_r2_no_wait`（等待循环 → `while False:`） | 红 `C4d` | ✅ 杀 |
| `m190e_r2_wording`（丢失分支关掉） | 红 `C4e`/`C4f` | ✅ 杀 |

（v1 里 `m190b`/`m190d` 未被杀，是我探针缺样例 —— 补 `C2b`、把 `C4d` 改成"第 3 张观测才入包"后 v2 全杀；`control` 的 v1 假红是变异树没拷 `docs/` 所致，v2 已拷。）

### 4.2 C6c：作者自报「变异 ⇒ 用例」映射实测复核

| 变异（作者站点） | 自报 | 实测 | 结论 |
| --- | --- | --- | --- |
| `m188a` 纯函数恒 `"tile"` | C# 杀 7 | C# 杀 **6** | **不符**（方向一致） |
| `m188b` 纯函数恒 `null` | C# 杀 8 | C# 杀 **7** | **不符**（方向一致） |
| `m188c` wrapper `resp.Acted = true` | 契约杀 1 | 契约杀 **1** | 符合 |
| `m188d` wrapper 不落 `ActedEvidence` | 契约杀 1 | 契约杀 **1** | 符合 |
| `m188e` R4 reason 模板 → `（空）` | 契约杀 1 | 契约杀 **1** | 符合 |
| `m188e2`（我另加的兜底值站点） | — | 契约杀 **0** | GAP-1 观察项（§3.6） |

计数口径：C# 杀条数 = `dotnet run` 输出里 `^FAIL\s` 行数；契约杀条数 = `tests.test_longrun.TestTask188UseToolActed` 的 failure 数。

---

## §5 NIT / INFO 清单（是否阻塞）

| 编号 | 内容 | 阻塞 0.7.36？ |
| --- | --- | --- |
| NIT-1 | 同一次动作里顺手入包的**无关 qid** 仍进 `sell` 白名单（Lead 已裁定，归 task-193 / 0.7.37） | 否 |
| NIT-2 | 作者自报映射 `m188a`(6≠7)、`m188b`(7≠8) 数字不符（两种变异都仍被杀） | 否 |
| GAP-1 | R4 契约是文本断言，`OriginalText()` 兜底值变异 **0 杀**（行为层不受影响） | 否（建议后续行为化） |
| INFO-1 | 脑侧裁决以**世界证据**为准，Mod 回执只作线索（`C5i`/`C5j`） | 否 |
| INFO-2 | `checks` 键集 10 个未变、`_leftover` 语义未变、F4 已注明"有意口径" | 否 |

---

## §6 结论

- task-186 / task-188 / task-189 三条通道的**对抗攻击全部被拦**：新鲜洞（F1 缺格假绿、F3 白名单污染、F5 措辞、R2 loot 记账、R1 回执 fail-closed）在 pre 树上均可复现为红，在 post 树上全部转绿（§2）。
- 自建变异矩阵 **12 case / 0 未达标**（§4.1），作者的映射经实测复核后**两条数字不符、三条符合**，无一条"变异不被杀"（§4.2）。
- 无必修项；NIT-1 已有归口卡（task-193）。
- **0.7.36 可以据此冻结**：本卡是冻结门之一，建议 Lead 按发布计划的九步走（`tools\_note-0736.txt` 首串 → bump → `check-release --expect 0.7.36` → build → deploy-mod → goto Farm → preflight → 装机记录）。

---

## §7 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
# 1) post 树（当前工作树）
$env:T190_ROOT = "$PWD"; $env:PYTHONUTF8 = "1"
& $py -W error::SyntaxWarning scratch\_t190_probe.py            # 期望 PASS=35 FAIL=0 SKIP=1
# 2) pre 树（FAIL→PASS 原文；T190_FORCE 让通道照跑）
$env:T190_FORCE = "1"
$env:T190_ROOT = "$PWD\scratch\_t190_pre186"                    # 期望 PASS=18 FAIL=17
& $py -W error::SyntaxWarning scratch\_t190_probe.py
$env:T190_ROOT = "$PWD\scratch\_t190_pre188"                    # 期望 PASS=30 FAIL=5
& $py -W error::SyntaxWarning scratch\_t190_probe.py
$env:T190_ROOT = "$PWD\scratch\_t190_pre189"                    # 期望 PASS=27 FAIL=8
& $py -W error::SyntaxWarning scratch\_t190_probe.py
# 3) 变异矩阵（含 C6c 映射复核）
& $py scratch\_t190_mutate.py                                    # 期望 12 case / 0 未达标
```

原始读数：`scratch\_t190_post_v4.txt`、`scratch\_t190_pre186_force.txt`、`scratch\_t190_pre188_force.txt`、`scratch\_t190_pre189_force.txt`、`scratch\_t190_mut_v2.txt`、`scratch\_t190_targeted.txt`、`scratch\_t190_full.txt`。

---

## §8 边界

- 只写 `docs\_review-task186-188-189.md` + `scratch/`；未碰 `brain/`、`mod/`、`tools/`、`tests/`、`logs/`、`docs\00-开发日志.md`、任务板；未跑真机、未装机、未 bump。
- 深挖入口：`scratch\_t190_probe.py`（35 条断言 + 1 条发现记录）、`scratch\_t190_mutate.py`（12 条变异，拷贝 `brain+tests+mod+docs`）。

---

## §9 追加 delta 复核（task-192 = `1246cdd`）

卡 task-190 的三条追加项（"释放认输区时同步扣减当天认输记账"落地后复验）。探针 `scratch\_t192_delta.py`（复用 `scratch\_t185_probe.py` 的夹具、`forge()` 与 `tool_run()`；16 条断言，`T185_ROOT` 可切树）。

### 9.1 命令与读数

```powershell
& $py -W error::SyntaxWarning scratch\_t192_delta.py          # HEAD = 1246cdd ⇒ PASS=16 FAIL=0 SKIP=0
$env:T185_ROOT="$PWD\scratch\_t192_pre"                        # 1246cdd^ = 3f3a5c0（488 文件）
& $py -W error::SyntaxWarning scratch\_t192_delta.py          # ⇒ PASS=6 FAIL=6
```

留档：`scratch\_t192_delta_v1.txt`（post）、`scratch\_t192_delta_pre.txt`（pre）。

### 9.2 三条 delta 逐条

| # | 卡面要求 | 实测（HEAD = `1246cdd`） | pre 树（`1246cdd^`） |
|---|---|---|---|
| ① | 释放后不许当天同区再认输；**累计上界不许因释放归零** | D1d 释放后 `shed_ever_tiles` 不归零；D3a 同区再认输被 `already_today` 拦；D3b 累计量抬到 `cap−1`（`cap=68` / workable=200）⇒ 换区认输被 `cap` 拦；D3c 对照清零后同一请求成功 | D1 直接 `AttributeError: 'LongRun' object has no attribute 'shed_ever_tiles'`（累计量机制不存在）；D3b 停在 `already_today`、D3c `allowed=False` ⇒ 上界通道不可达 |
| ② | 净额与工具 `3ccc29b` 一致（`journal 毛 − 释放 = 账本末态`） | D4e 干净释放（6−6=0，账本 0）⇒ 不判「认输量对不上」；D4f 6−2=4 而账本 0 ⇒ problem；D4g 一致 4 ⇒ 与基准同码 | 工具口径已存在 ⇒ D4e/f/g 同样通过；但 pre 树脑侧写的是**毛**（不扣释放）⇒ 真跑时账本与工具净额会不一致（本项修的是脑侧写数口径） |
| ③ | 部分释放 6→2 ⇒ 末态 4 | D2b `scope_released.tiles=2` / `shed_tiles_remaining=4` / `rep.scope_shed_tiles=4`；D2 用真流程（释放时仍持有 2 格）⇒ 末态 = 毛 − 2，快照留 `released_tiles=2` | D2b `末态=6 rel={tiles:2, remaining:None}`（只记释放量、末态不扣）；D2c 快照仍 `tiles:50`、无 `released_tiles` |

### 9.3 结论

三条 delta 全部符合；pre→post 由 6 条通过升至 16 条通过，FAIL→PASS 证据齐。**不影响 §6 的 0.7.36 冻结判定（仍为"可以据此冻结"）。**

### 9.4 冻结后的 hash 口径补注（口径差，非缺陷）

`§1` 的 SHA256 读数取自 `3f3a5c0`（task-192 落地**前**）。task-192（`1246cdd`）改了 `brain/agentfarm/longrun.py` ⇒ 0.7.36 冻结提交 `7ad5f6b` 上该文件 SHA256 前 16 = **`C326DD1E1358EA15`**（本 §9 的探针读数即在此内容上取得）；其余五个文件与 §1 逐字一致（`farmwork.py FA6BD05CCAB9DF25`、`test_farmwork.py 7C503EC1AEB4CF9A`、`UseToolSkill.cs 0163D54BDE2ED462`、`Skills.cs 548E233BFC44BA27`、`Tests/Program.cs F2F280F292876F53`）。装机产物独立复核（只读）：`mod\AgentFarm.Bridge\bin\Release\AgentFarm.Bridge.dll` **202752 B**（SHA256 前 16 `D6699BD057C51CE7`）、`mod\AgentFarm.Bridge\manifest.json` **53261 B** / `"Version": "0.7.36"`、`brain/agentfarm/bridge.py` `MOD_VERSION_EXPECTED = "0.7.36"`（冻结提交 diff 逐行核过：`0.7.35` → `0.7.36`）。
