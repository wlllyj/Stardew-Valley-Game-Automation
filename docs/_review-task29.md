# task-29 独立验收（deputy-lead / 承 task-35 之后）

判定：**PASS**（两条诚实化路径与处三处退出码语义全部成立，我自己跑命令、自己的桩、不复用作者用例助手）

对象：提交 **`4b3addf`**（唯一一次改动的全部内容）
`README.md` +3 · `brain/agentfarm/__main__.py` +27/−5 · `tests/test_main_pid_gate.py` +41/−1（`git show --stat 4b3addf`）

---

## §1 读数（我亲跑）

| 项 | 读数 |
| --- | --- |
| `py_compile brain/agentfarm/__main__.py` | **exit 0** |
| `unittest tests.test_main_pid_gate -v` | **Ran 13 tests / OK**（与 Lead 读数一致） |
| 全量 `unittest discover -s tests` | **Ran 294 / FAILED (failures=1)** ⇒ 失败是 `test_longrun.TestOneDay.test_no_buy_flag`，**与 task-29 无关**，属 dev-coder 正在落的 NIT-1 修复的连带效应（详见 §5 警告） |
| 我的独立探针 | `scratch\_t29_probe.py`（最小自写桩，monkeypatch `pid_alive`，**不 import 作者的 `_Recorder`**）⇒ **9/9 ALL-PASS**（§2） |
| 范围 | `4b3addf` 只碰上述 3 个文件；`brain/agentfarm/longrun.py`、`tests/test_longrun.py`、`mod/`、`tools/` 在该提交里**未被触碰** |

---

## §2 条款①：`kill()` 返回 `False` / 抛异常两条路径真的 `return 1`、异常不穿出 —— 成立

代码路径 `brain/agentfarm/__main__.py:564-579`：

```
564  if pid is None:                       → 报"缺 pid，无法强杀" → return 1
569  try:    killed = bool(kill(int(pid)))
571  except Exception as exc:              → 报"强杀抛异常：<类型>: <消息>" → killed = False
574  if not killed:                       → 报"强杀未成功，进程可能仍在运行（pid=…）：请人工确认" → return 0? 不：return 1
578  out("强杀成功") → return 0
```

我的探针实测（每例都**故意不 try/except**，异常穿出即脚本崩 = FAIL）：

| 例 | 输入 | rc | 日志/副作用 | 期望 |
| --- | --- | --- | --- | --- |
| A | `pid_alive=False` | **0** | `游戏进程（pid 24444）已退出`；**未调用 kill** | ✅ |
| B | `pid=None`、桥不应答 | **1** | `无法判定…缺 pid，无法强杀…请手动确认`；未调用 kill | ✅ |
| C | `pid=None`、**桥仍在应答** | **1** | `桥仍在应答 ⇒ 进程显然还活着，继续等待` → 等满后仍 `return 1` | ✅ 不因桥活着就报成功 |
| D | `kill` 返回 `False` | **1** | `强杀未成功，进程可能仍在运行（pid=24444）：请人工确认`；`killed=[24444]` | ✅ **核心** |
| E | `kill` 抛 `OSError` | **1** | `强杀抛异常：OSError: taskkill 不在 PATH` + `未成功…`；**无 traceback 穿出** | ✅ **核心** |
| F | `kill` 返回 `True` | **0** | `强杀成功（pid 24444）`；`killed=[24444]` | ✅ |
| G | `kill` 返回 `1`（非 bool 真值） | **0** | `强杀成功` | ✅ `bool()` 语义一致 |
| H | `pid="abc"`（非法） | **1** | `int()` 的 `ValueError` 被同一个 except 兜住 → `未成功`；未真调用 kill | ✅ 安全方向（见 NIT-2） |
| I | `seconds=0` + pid 有值 | **0** | 不进等待循环，直接走强杀兜底 | ✅（CLI 只在 `--force-after>0` 时才进来） |

**没有一条 `return 0` 是无证据的**：全文只有两处 `return 0` —— `:552-554`（要求 `pid_alive is False`，即判死）与 `:578`（要求 `kill` 返回真）。`None`（不知道）在任何分支都不会被当成"已退出"。

`_taskkill`（`:499-503`）本身也守约：非 Windows ⇒ `False`；Windows ⇒ `os.system('taskkill /PID n /F') == 0` ⇒ 失败必然 `False` ⇒ 上面 `:574` 必然 `return 1`。

---

## §3 条款②：退出码语义三处措辞一致 —— 成立（逐处抄录）

- **`__main__.py` docstring `:537-540`**：`0 = 已确认退出（pid_alive 判死，或强杀成功）；1 = 等满仍未能确认退出，或无法强杀，请人工确认 —— 缺 pid、强杀返回假、强杀抛异常、桥既不响应又无法按 pid 判定，全部归这里。`
- **CLI `shutdown` 子命令 help `:806-808`**：`退出码：0=已确认退出（pid 判死或强杀成功） 1=等满仍未能确认退出/无法强杀，请人工确认`
- **CLI `--force-after` help `:810-812`**：`0=已确认退出（pid 判死或强杀成功）；1=等满仍未能确认退出，或缺 pid/强杀失败，请人工确认`
- **`README.md:54-56`**：`0 = 已确认退出（pid 判死，或超时后强杀成功）；1 = 等满仍未能确认退出，或无法强杀（缺 pid / 强杀返回失败 / 强杀抛异常），请人工确认`

三处同义、无自相矛盾：`0` 都要求"已确认"（判死 **或** 强杀成功）；`1` 都覆盖"缺 pid / 强杀失败 / 强杀抛异常 / 等满仍不确定"。docstring 那句"桥既不响应又无法按 pid 判定"与实际代码一致（`:555-562` 只是记录并继续等，`:564-567` 才 `return 1`；桥不应答但 pid 可用 ⇒ 走强杀，成功仍是 0，符合语义）。

`pid_alive` 自身的契约也一致（`brain/agentfarm/bridge.py:149-177`）：`None`=不知道、Windows 用 `OpenProcess+WaitForSingleObject`（绝不用 `os.kill(pid,0)`）、非法 pid 由上游 `_parse_pid`（`bridge.py:321-327`）归一成 `None` 并留 note ⇒ `await_game_exit` 实际只会收到 `int` 或 `None`。

---

## §4 条款③：范围检查 —— 成立

- `git show --stat 4b3addf` 只有 3 个文件（上表）；**task-19 的 `brain/agentfarm/longrun.py` / `tests/test_longrun.py` 在 `4b3addf` 里未被触碰**（我在 task-19 验收快照里算的 `331dedede388` / `f27b12950f11` 直到该提交后复算仍不变）。
- 现在这两个文件确实变了（`6dcb11225ce6` / `06547cd95c34`，18:04:41/18:04:45）—— 那是 **dev-coder 正在落 NIT-1 修复**（我已核：工作树里 `if not win:` 分支把结论钉成 `False`，并加了注释引用 `docs\_review-task19.md`），属 Lead 已批准的在制，不是 task-29 范围外改动。
- `tools/preflight.py`（18:04:46）也是 Lead 侧在制，与 task-29 无关。

---

## §5 NIT 清单 / 当前工作树警告

- **⚠ 警告（给 Lead 的 delta 复核用，非 task-29 缺陷）**：NIT-1 修复落地后全量是 **294 tests / 1 failure = `tests/test_longrun.py:791 test_no_buy_flag`**。
  - 现象：`FakeWorld(weeds=0, seeds=0, money=100)` + `allow_buy=False` ⇒ 地上一格都没有 ⇒ 户外窗口 0 格 ⇒ 新守卫生效 ⇒ `checks.watered_outdoor=False` ⇒ 那天 `→ needs_review`、`run()` 返回 1，而该用例断言 `code == 0`。
  - 判断：这是**修复的正确连带效应**，不是回归 —— 生产里跑 run3 时农场上必然有 objects/terrainFeatures（草/石/耕地），窗口非空；但这条既有用例的假世界是退化的（零格农场）。
  - 需要决策：要么把它改成生产可信的假世界（给一格耕地/草），要么显式改期望并注明"零格农场不算达标"。**这是语义决定，请 Lead 拍板后由 dev-coder 落地**（我未改任何测试）。`verify-run3.py:390-402` 明确支持"无活可做的 0 步日可被判 VERIFIED"（有 `no_work` 证据时只记 info）⇒ 口径上两种选择都能自洽，但必须选一个并留痕。
- **NIT-1（task-29 自身，不阻塞）**：`__main__.py:806-812` 两个 help 文本很长（子命令列表里会被截断显示）；纯 cosmetic。
- **NIT-2（task-29 自身，不阻塞）**：`await_game_exit` 只把 `pid is None` 认定为"缺 pid"（`:564`）；非法类型（如 `"abc"`）要等到 `int(pid)` 的 `ValueError` 才失败，且会先打印一句"等了 Ns 进程仍在（pid abc）"（措辞误导）。方向安全（rc=1），且上游已归一（`bridge.py:321-327`）⇒ 实际不可达。若要更整洁，可在入口处 `pid = _parse_pid(pid)` 或把 `:564` 改成 `if not isinstance(pid, int) or pid <= 0`。
- **INFO**：`test_main_pid_gate.py` 新增的 3 条用例断言有效（`rc==1` + `未成功` + OSError 类型名出现 + `declared_exit` 不被置真），不是空断言；我另用自己的桩复现了同样结论（§2 表），故不依赖作者用例自证。

---

## §6 结论

**PASS。** ①`kill()` 返回假 / 抛异常两条路径都 `return 1` 且日志含"未成功"、异常被兜住不穿出（`:569-577`，探针 D/E 实测）；②退出码语义在 docstring / CLI help（两处）/ README 四处措辞同义、无矛盾；③`4b3addf` 范围干净，未触碰 task-19 的两个文件。

唯一需要 Lead 决策的是 §5 的工作树警告：NIT-1 修复让既有用例 `test_no_buy_flag`（零格农场的"无活可做"日）不再达标 ⇒ 全量当前 **294 / 1 failure**，delta 复核的"294 OK"目标需要先处理这条用例（改假世界或改期望，二选一）。

---

## §7 NIT-1 delta 复核（Lead 派，2026-10-13 18:07）= **DELTA-PASS**

对象（两个文件的最终 SHA256，与 Lead 给的**逐字一致**）：
`brain/agentfarm/longrun.py` = `6DCB11225CE615C167334BC820B9EEA4E10A7F89C3B72EEED186E3077C3078C0`（121125 B / 18:04:41）
`tests/test_longrun.py` = `83A506D91448FDDF5061FE52BE8439627302DDF8D903DD7087F3E9DCB84CEEA2`（106936 B / 18:05:52）

四项：

1. **空窗口钉成 False 且不影响非空窗口**：`longrun.py:595-600` 空窗口先 `return False, info`，`:601 return len(dry_t) == 0` 只对非空窗口生效。
2. **新用例真的在验东西、且可证伪**：`tests/test_longrun.py:1967-1982 test_empty_outdoor_window_is_false_never_true` —— `assertFalse(ok)` + `scope=="window"` + `(tiles,crops,dry)==(0,0,0)` + `assertIn("没有任何户外窗口观测格", note)`；输入刻意用 `_with_crop(watered=True)`（作物已浇好，杜绝"没有干格就算过"的蒙法）且 `farm.complete=False` 逼走窗口分支。**旧代码必失败**：我 task-35 的探针 A3 就是同一输入打旧代码、旧代码返回 `ok=True`（NIT-1 的发现过程）。
3. **diff 只有这三处**：把 17:57（NIT-1 之前）存的 `scratch\_task19_wip.diff`（395 行）与 `scratch\_delta_now.diff`（429 行）做行级 `Compare-Object` ⇒ 新增仅 ①的 5 行（替换旧 1 行）+ 新用例 ~16 行 + `test_no_buy_flag` 的 6 行，其余只是 `index`/`@@` 行号偏移；无夹带。`git diff --stat` = longrun **+147**（原 +143）、test_longrun **+174**（原 +151）。
4. **`test_no_buy_flag` 只补假观测、断言未放宽**：`:797-798` 加 `w.farm={"loaded":True,"complete":True,"crops":0,"dryCrops":0,"unwateredCrops":0,"hoeDirt":0}`（含 4 行理由注释），`:801-803` 原样保留 `assertEqual(code, 0, run.logs)` / `w.buys == []` / `w.crops == {}`。

读数：两个目标用例 `-v` ⇒ **Ran 2 / OK**；全量 `unittest discover -s tests` ⇒ **Ran 294 tests / OK**（exit 0）。§5 的警告由此关闭。
