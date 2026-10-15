# task-100 复验：task-99（`6a6da70`）—— C1 真洞收口 + NIT-6 夹具语义

**判定：PASS-WITH-NITS**（无必修项；NIT-1 建议在 0.7.28 顺手做，理由见 §6）

- 验收对象：`6a6da70`「0.7.27 task-99: dryCrops 缺失 ⇒ 未知(≠0) fail-closed + 夹具 None 语义修正(NIT-6)」
- 一句话结论：我 task-97 的 **C1 反例已 FAIL→PASS**（"`no_work` + `watered_outdoor=true` + 工具 VERIFIED"三者同时**不再出现**）；task-96 的四条成果（C6c/C6d/C8b/C8c）全数保留；新修法**没有**引入新的假绿；残留只有"畸形 `dryCrops` 类型"（真实 Mod 不可达）和字段偏乐观这两类 NIT。
- `tools/verify-run3.py` SHA256 = `7356D4CBA1D0A1EE3DFDB5F2723EB39E615C0795C289122863A46730A9A965C3`（与 task-97 验收时**逐字相同**）⇒ 两个任务的工具判决可直接对比。

## §1 范围与读数（全部我亲跑）

| 项 | 实测 |
| --- | --- |
| HEAD / 工作树 | `6a6da70`（其后仅文档提交 `f3e8ec7`）；`git status --short` **干净** |
| `git show --stat 6a6da70` | **恰 2 文件**：`brain/agentfarm/longrun.py` +15/−3、`tests/test_longrun.py` +128/−16（合计 +143/−19） |
| 越界扫描（`manifest`/`bridge.py`/`^logs/`/`00-开发日志`/`^tools/`/`^mod/`） | **零命中** |
| SHA256 | longrun `D1D02D9AE9AB189685A07676681FA61351F44965F892EB1C76D6EFC310D15CE2`、test_longrun `A13875FF6886EA5A28C3F0D18561AED851464DEE44C72A3A5D9ED785CFB99FB9`；`farmwork.py` 8B62190A… / `test_farmwork.py` 04AC1FBD… / `tools/verify-run3.py` 7356D4CB… **均未变** |
| 版本 | `manifest.json:4` = 0.7.27、`brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.27"`（未 bump） |
| `py_compile -W error::SyntaxWarning` | exit 0 |
| `tests.test_longrun tests.test_farmwork` | **Ran 264 tests / OK**（与作者/Lead 一致） |
| 全量 `discover -s tests` | **Ran 594 tests / OK**（与 Lead 一致） |

## §2 作者自报修法逐字复核（对到行）

- `brain/agentfarm/longrun.py:783-791`：`farm = obs.get("farm") or {}`；`:784-785` `complete is not True or loaded is False ⇒ return None`；`:786-787` `dry = farm.get("dryCrops")` / `ripe = farm.get("ripeCrops")`；**`:788-790` `if dry is None: return None`（task-99 ① 就是这一行）**；`:791 return (int(dry), int(ripe or 0))`。
- 与卡面要求逐字一致（旧写法 `if dry is None and ripe is None` 已删除）；docstring `:773-781` 明确写出我 task-97 的 C1 链、可达性依据（`watchdog.py:139-148` 的 `mod_version_mismatch` 仅 `LEVEL_WARN`）与 Lead 明示接受的代价。
- NIT-6 落地：`tests/test_longrun.py:167-169` 把 `farm is None` 映射成 `{}`（"证据不可用"）；`:179-185` 新增 `farm_scan()` 并注明"要世界一致扫描必须显式 `w.farm = w.farm_scan()`"；`:4811-4829` 新增 `test_fixture_none_means_evidence_unavailable` 钉死该语义（含 `obs["farm"] == {}`、`_farm_totals is None`、`sleep_guard` 不放行、显式 `farm_scan()` 后 `(crops,dryCrops)==(1,1)`）。
- 新增用例（`TestTask99DryCropsMissing`，`tests/test_longrun.py:4732-4829`，6 条）**断言都真的在验东西**：`:4755` 缺失⇒`None`／补上⇒`(0,0)`／`dryCrops=3,ripe=2`⇒`(3,2)`；`:4767` C1 反例（不许 `no_work`、`verified=False`、`day_justified=False`、`farm_evidence_unavailable` 每天恰好 1 条且 `on_farm=True`、`_water_evidence` 不许退回窗口自称浇过）；`:4787` `ripe>0` 也不许 `no_work`；`:4799` 正对照（补上 `dryCrops=0` ⇒ 守卫放行 `no_work`）；`:4811` NIT-6。

## §3 B 段（核心）：C1 反例 FAIL→PASS

脚本 `scratch/_t100_b.py`（真 `FarmWorker` + 真 `LongRun` + 真 `tools/verify-run3.py` 进程内），输出 `scratch/_t100_b_out.txt`。
世界 = 窗外（400 格观测窗口外）一株**真·没浇的活苗** + `farm` 块 `complete=true, ripeCrops=0, **无 dryCrops**`。

| 例 | 旧（task-96 及以前，我 task-97 实测） | 现在（`6a6da70`） | 工具 |
| --- | --- | --- | --- |
| B/C1（无耕地） | `no_work` + `watered_outdoor=true` + **VERIFIED** | `ended_by=stuck`、`verified=False`、`day_justified=False` | `ok=False / needs_review`（`ended_by=stuck`、`day_end verified=false`） |
| B/C1b（留可耕地） | 同上 | 同上 | 同上 |

- **拦截点（两处，都在 fail-closed 链上）**：`longrun.py:1538`（`work_reasons` 里 `if farm_work is None:`）+ `:1544` `reasons.append(self._farm_evidence_reason(obs))` ⇒ 守卫拿到"人在农场里且 farm 证据不可用…不许判『没有活』"；`longrun.py:1724` + `:1729` `return False, "keep_working", self._farm_evidence_reason(obs)` ⇒ **不放行 `no_work`**，最终以诚实 `stuck:` 收尾（`journal` 每天 1 条 `farm_evidence_unavailable`，`on_farm=True`）。
- 注意：`checks.watered_outdoor` 在这两例里仍是 `true`（窗口里那株活苗确实浇好了），但 `day_justified=False`+`verified=False` ⇒ 账本与工具都是**红的**；卡面要求的"三者同时"已不成立。

## §4 B 段防回归（task-96 成果未被弄回去）

| 例 | 结果 | 工具 |
| --- | --- | --- |
| B/C6c `complete=false` | `stuck` / `verified=False` / `watered_outdoor=false`，`stages=[('clear_dead',1,…)]` | `needs_review`（含 `checks.watered_outdoor=false`） |
| B/C6d `farm=None` | 同上；理由里 `farm.complete=None/loaded=None/dryCrops=None` ⇒ 证明 `None` 现在真的是"没有 farm 块" | `needs_review` |
| B/C8b `complete=false` + 窗外真·没浇活苗 | `stuck` / `False` / `watered_outdoor=false` | `needs_review`（3 problems） |
| B/C8c `farm=None` + 同上 | 同上 | 同上 |

⇒ task-92 那两条 fail-open 原形（C8b/C8c）在 NIT-6 之后**用真语义重建仍然 PASS**。

## §5 C 段：朝新修法进攻

| # | 攻击 | 期望 | 实测 | 判定 |
| --- | --- | --- | --- | --- |
| ① | **正对照**：证据可用且 `dryCrops=2` ⇒ 守卫必须继续干 | 不许 VERIFIED | `stuck`、`watered_outdoor=false`、`scope=farm`、理由"农场口径还有 2 格干作物…先回农场再判" | ✅ 可用证据没被一起关掉 |
| ② | `dryCrops=0`（真有值且为 0）+ 活苗都浇好 | 该正常 VERIFIED | `no_work`、`verified=True`、`scope=farm`、工具 `ok=True / VERIFIED` | ✅ 卡面 C② 满足 |
| ③a | `dryCrops="0"`（字符串数字） | fail-closed？ | **当成 0** ⇒ `no_work` + VERIFIED + 工具 VERIFIED | ⚠️ NIT-1（未做类型校验） |
| ③b | `dryCrops="abc"` | fail-closed？ | **`ValueError: invalid literal for int() with base 10: 'abc'` 直接穿出 `run.run()`** ⇒ 整天崩掉（不是 fail-closed，也不是白过） | ⚠️ NIT-1 |
| ③c | `dryCrops=-1` | fail-closed？ | `_farm_totals=(-1,0)` ⇒ `no_work` 且 `day_justified=True`，但 `_water_evidence` 判 `dry=-1≠0` ⇒ `watered_outdoor=False` ⇒ `verified=False`，工具红（`checks.watered_outdoor=false`） | ✅ 无假绿（但状态自相矛盾 ⇒ NIT-3） |
| ③d | 显式 `dryCrops=None` | fail-closed | `stuck` / `verified=False` | ✅ |
| ④ | Lead 提示①：`dryCrops` 缺失 + `ripeCrops>0` | 有没有形态能骗到 VERIFIED | P4a 熟作物**藏在窗外** ⇒ `stuck`/`False`；P4b 熟作物**窗内可收**（真收到 1 步，`stage harvest ok=1`）后仍 `stuck`/`False` | ✅ **构造不出**该形态，与作者报备一致（`ripe>0` 本身就让守卫继续干） |
| N3 | 窗口 `crops=24` **全是死苗** + farm 证据不可用 + 窗外真·没浇活苗 | 会不会出假绿 | `ended_by=stuck`、`verified=False`、`day_justified=False`；`watered_outdoor=true`（字段） | ✅ 无假绿；字段偏乐观 ⇒ NIT-2 |

## §6 NIT 表

| # | 现象 | 行号 | 建议 | 必修？ |
| --- | --- | --- | --- | --- |
| NIT-1 | `_farm_totals` 只判 `is None`，不做类型校验：`"0"` 被 `int()` 接受 ⇒ 与"合法 0"不可区分（同 C1 家族）；`"abc"` 抛 `ValueError` 直接**杀掉整天**（不是 fail-closed） | `brain/agentfarm/longrun.py:786-791` | 与同文件 `farmwork.farm_dry_tiles`/`farm_dry_dead_crops` 的 `isinstance` 校验保持一致：`if not isinstance(dry,(int,float)) or isinstance(dry,bool): return None`。真实 Mod（JSON `int`）不可达 ⇒ 不是回归、不阻塞 run8 | 否（建议 0.7.28） |
| NIT-2 | 窗口全死苗时 `watered_outdoor=true`（窗口 `dry_t` 排除了 dead，`crops>0` 又不触发 `crops==0` 闸门）⇒ 字段偏乐观 | `longrun.py:1071`（`dry_t` 过滤 dead）、`:1085-1092`（`if not crops_t` 只堵"0 作物"）、`:1093` | 若要字段级干净：`if crops_t and not [t for t in crops_t if not win[t].get("dead")]: return False, info`（"窗口里没有一株活苗 ⇒ 不是浇水证据"） | 否 |
| NIT-3 | `dryCrops=-1` 时 `no_work` + `day_justified=True` 与 `verified=False` 并存（账本红但状态自相矛盾） | 同上 | 同 NIT-1 的类型校验即可顺带消掉 | 否 |
| NIT-4 | 夹具 `farm_scan()` 的 `crops` 把死苗也算进去（与 docstring"crops 只算活苗"不符），只影响测试夹具 | `tests/test_longrun.py:179-212` | 顺手把 `crops` 改成只算 `not dead`（或改 docstring） | 否（留档） |

## §7 NIT-3（口径结论，给 `docs/_run6-criteria.md`）

**task-99 之后 NIT-3 不再产生假绿，不需要另立卡。** 证据：窗口全死苗 + farm 证据不可用时，守卫在 `longrun.py:1724-1729` fail-closed ⇒ 当天只会以 `stuck:` 收尾、`verified=False`、`day_justified=False`（本轮 N3 实测，`watered_outdoor=true` 无人采信）。它如今只是**字段级偏乐观**（窗口全死苗仍写 `watered_outdoor=true`），而 `tools/verify-run3.py` 的 B4b 闸门只在 `scope=window && crops==0` 时判红、`crops=24` 不触发。
⇒ 建议口径表写：**"窗口 `crops>0` 但全为死苗 ⇒ `watered_outdoor` 仍可能写 true；该字段此时不具证明力（当天必 fail-closed、不产生假绿）。字段级收口见 `_review-task99.md` NIT-2，0.7.28 可选。"**

## §8 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8="1"
& $py -W error::SyntaxWarning "scratch\_t100_b.py" | Out-File -Encoding utf8 "scratch\_t100_b_out.txt"
& $py -m unittest tests.test_longrun tests.test_farmwork      # 264 OK
& $py -m unittest discover -s tests                            # 594 OK
```

## §9 结论

- **PASS-WITH-NITS**：主攻（C1 假 VERIFIED）已 FAIL→PASS 并有 2 处拦截点行号（`longrun.py:1538/1544`、`:1724/1729`）；task-96 成果零回归；正对照（证据可用 / `dryCrops=0`）行为正确；`dryCrops` 缺失 + `ripe>0` 骗不出 VERIFIED；NIT-3 已不产生假绿。
- 残留 4 条 NIT 全是"畸形输入/字段措辞"级，真实 Mod 不可达，**不阻塞** `0.7.27` 放行与 run8。
- 越界检查：本任务只写 `docs/_review-task99.md` + `scratch/_t100_b.py`（+输出 txt），未碰 `brain/`、`mod/`、`tests/`、`tools/`、`logs/`、`docs/00-开发日志.md`。
