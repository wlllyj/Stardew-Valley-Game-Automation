# task-9 · 长跑看护守护 `tools/run-guardian.py` —— 离线夹具自测证据

> **§0 结论先行**：交付 `tools/run-guardian.py`（脱离式可起跑的长跑看护守护）。判据 = ①`logs/<tag>.pid` 脑进程实测存活 ②`logs/<tag>.jsonl` 是否出现 `finish` 或超过 `--stall-seconds` 秒无新行 ③`bridge.json` 是否存在/新鲜/health 可达。
> **脑死 且（`finish` 已写 或 账本超时无新行）⇒ 自动执行 `tools/stop-game.py` 优雅退出并复核进程 0 / bridge.json / 17890；脑活但桥失联 ⇒ 只告警不退出。**
> 离线夹具自测 **30/30 PASS**（两态 + 超时分支 + PID 缺失安全闸 + `--dry-run` 不调用 stop + `--detach` 脱离式）；**未做真机演练**（按 Lead 指令：A9 起跑前空档再放行）。真机全程未被触碰（自测前后 `StardewModdingAPI.exe` 进程数 = 0、真 `bridge.json` 不存在）。

- 执行：teammate `machine-runner`｜卡：task-9｜被测：`tools/run-guardian.py`（新增，0.7.44 批次工具，不改生产代码）
- 夹具：`scratch\_t9_guardian_selftest.py`（自测器）、`scratch\_g_fake_stop.py`（假 stop 脚本）
- 自测原文：`logs\t9-guardian-selftest.txt`（97 行 / 7795 B / UTF-8）；夹具与各用例日志：`scratch\_gtest\<case>\`
- 自测时间：`2026-10-18T17:37:29` 至 `17:37:42`（约 13s）

---

## §1 脚本职责与判据（`tools/run-guardian.py`）

### 1.1 判据表

| 观测 | 判定 | 动作 |
|---|---|---|
| `logs/<tag>.pid` 存在、解析成功、进程**实测已死** | `brain_dead=True` | 进入触发判定 |
| 同上，且账本出现 `event=finish` | `trigger=True` | **执行 `tools/stop-game.py`（优雅退出）** |
| 同上，且账本 `mtime` 超过 `--stall-seconds`（默认 180s）无新行 | `trigger=True` | 同上（覆盖「脑被 kill、日志无 finish」形态） |
| 同上，但账本仍在更新且无 finish | `trigger=False` | 继续观察（避免打断收尾写账本），日志写「继续观察」 |
| `logs/<tag>.pid` 缺失 / 解析失败 / 存活探测失败 | `trigger=False` | **安全闸**：无法证明脑死就不动手，只告警 |
| 脑**活** + 桥失联（`bridge.json` 缺失 / mtime > `--bridge-stale-seconds` / health 不可达） | `trigger=False` | **只告警，不退出**（脑还在跑，游戏必须开着） |
| 脑活 + 桥在 | 正常 | 心跳日志（默认 300s 一次状态变化外的保活行） |

- 触发后：跑 `python -u <stop-script> --wait <stop-wait-seconds>`（默认 `tools/stop-game.py --wait 45`，**只用优雅退出，绝不 taskkill**）→ 打印 rc → 复核 `tasklist` 里 `StardewModdingAPI.exe` 进程数、`bridge.json` 是否存在、`netstat` 里 17890 是否 LISTENING → 写 `logs/<tag>-guardian.log`。
- 退出码：`0`=已收尾/无需动作（含 `--once`/`--dry-run`）；`2`=已执行 stop 但游戏仍在跑（需要人工介入）；`3`=参数/环境错误。
- 每拍状态快照覆盖写 `logs/<tag>-guardian-state.json`（含 `brain_alive/journal/finish/stalled/bridge/trigger/stop/verify` 全字段，便于事后复核）。

### 1.2 安全闸（写死在实现里）

1. `--tag` **必填**，无默认值；pid/journal/log/state 全部由 tag 派生 ⇒ 不会误作用于别的 run。
2. 触发必要条件含「PID 文件存在 + 进程实测已死」；**PID 文件缺失一律不触发**（自测 D 用例）。
3. `--dry-run`：命中判据**只打印命令**，**不执行 stop、不退出游戏**（自测 E 用例证明假 stop 收据不存在）。
4. stop 只调用显式 `--stop-script`（真机默认 `tools/stop-game.py`）；日志打印完整命令与 rc。
5. 看护自身可 `--detach` 脱离式起跑（`DETACHED_PROCESS`），返回后继续看护，与 agent 回合边界无关；guardian 自身 pid 写 `logs/<tag>-guardian.pid`，console 写 `logs/<tag>-guardian.console.log`。

### 1.3 与本事故（条目 084）的对应

| A8 事故环节 | 本脚本覆盖 |
|---|---|
| 会话 15:08 死 → 看护子代理 15:09 一起失败 | 看护是**独立 detached 进程**，不随会话/子代理死 |
| 脑 15:20:38 自己收尾（写了 `finish`）→ 无人 stop-game，游戏跑到 17:03 | 脑死 + `finish` ⇒ 立即 stop（自测 A） |
| 若脑被 kill、没来得及写 `finish` | 账本超时无新行 ⇒ stop（自测 B2） |
| 脑还活着但桥掉线（假死/游戏挂） | 只告警，不越权退出（自测 C） |

---

## §2 自测设计（全部离线，不碰真游戏）

- 夹具（`scratch\_gtest\<case>\`）：假 `brain.pid`（死 pid = `999999` / 活 pid = 自测进程 `os.getpid()`）、假账本 `.jsonl`（含/不含 `finish`）、假 `bridge.json`（或指向不存在路径）、**假 stop 脚本** `scratch\_g_fake_stop.py`（写收据到 `$GUARDIAN_FAKE_RECEIPT`，不发桥请求、不 taskkill）。
- 断言口径：**「触发了 stop」= 假 stop 收据文件出现且 argv 含 `--wait`；「没触发」= 收据不存在**；另断言 guardian 日志含各判据原文。
- 真机未触碰的硬断言：自测开始/结束都检查 `StardewModdingAPI.exe` 进程数 = 0、真 `%APPDATA%\StardewValley\AgentFarm\bridge.json` 不存在（自测前后均成立）。

| 用例 | 形态 | 期望 | 结果 |
|---|---|---|---|
| A | 脑死（999999）+ 账本含 `finish` | 触发 stop | **PASS**（6/6 断言） |
| B1 | 脑死 + 无 `finish` + 账本新鲜（0.1s） | 不触发，写「继续观察」 | **PASS**（3/3） |
| B2 | 同 B1，把账本 mtime 回拨 600s（> 180s 阈值） | 触发 stop（超时分支） | **PASS**（3/3） |
| C | 脑活（自测进程 pid）+ `finish` 已写 + 桥缺失 | 只告警，不调用 stop | **PASS**（4/4） |
| D | `brain.pid` 缺失 + `finish` 已写 | 安全闸：不触发 | **PASS**（3/3） |
| E | A 的夹具 + `--dry-run` | 打印命令，不调用 stop | **PASS**（4/4） |
| F | `--detach --once`（子进程自行评估后退出） | guardian pid/console 生成、无残留进程 | **PASS**（5/5） |
| 收尾 | 真机未被触碰 | 游戏进程 0、真 bridge.json 未创建 | **PASS**（2/2） |

**总读数：`# RESULT: 30/30 PASS`（`logs\t9-guardian-selftest.txt:97`），自测器 rc=0。**

---

## §3 两态自测原文（rc / 日志）

### 3.1 脑死 ⇒ 触发（用例 A：正常退出但 `finish` 已写入）

guardian 调用假 stop 的 rc 与判据原文（`logs\t9-guardian-selftest.txt:14-21`）：

```
2026-10-18T17:37:31 [stop] 判据成立：判据成立：脑死 且 finish 已出现
2026-10-18T17:37:31 [stop] 命令：…python.exe -u …\scratch\_g_fake_stop.py --wait 1.0
2026-10-18T17:37:31 [stop]   [fake-stop] called argv=['--wait', '1.0'] … rc=0
2026-10-18T17:37:31 [stop] rc=0
2026-10-18T17:37:31 [verify] 进程数=0 pids=[]
2026-10-18T17:37:31 [verify] bridge.json=…\scratch\_gtest\A-dead-finish\bridge.json exists=True
2026-10-18T17:37:31 [verify] 17890 LISTENING=False
2026-10-18T17:37:31 [exit] code=0 ✅ 游戏已退出（进程 0）
```

- 假 stop 收据原文（`scratch\_gtest\A-dead-finish\stop-receipt.json`）：`{"at": "...", "argv": ["…_g_fake_stop.py", "--wait", "1.0"], "cwd": "<repo>", "rc": 0, "note": "fixture only：不请求桥、不 taskkill、不碰存档"}`。
- 断言：`A 判据成立 ⇒ 假 stop 被调用（receipt 存在）`、`A 假 stop 收到 --wait 参数`、`A 日志含 时间/判据/finish/stop rc/进程 0`、`A 日志含 bridge.json / 17890 复核` 全 PASS。

### 3.2 脑死 + 无 `finish` ⇒ 按超时阈值触发（用例 B）

- B1（账本 0.1s 前刚更新）**不触发**：`logs\t9-guardian-selftest.txt:24-25` `PASS B1 未超时 ⇒ 不触发（receipt 不存在）`、`PASS B1 日志写明「继续观察」`。
- B2（同一夹具，账本 mtime 回拨 600s）**触发**（`:27-38`）：

```
2026-10-18T17:37:36 [stop] 判据成立：判据成立：脑死 且 账本已 600.1s 无新行
2026-10-18T17:37:36 [stop] rc=0
2026-10-18T17:37:36 [verify] 进程数=0 pids=[]
2026-10-18T17:37:36 [verify] 17890 LISTENING=False
2026-10-18T17:37:36 [exit] code=0 ✅ 游戏已退出（进程 0）
```

⇒ 「脑进程被 kill / 消失但日志无 `finish`」这一形态由**超时阈值**覆盖（默认 180s，可用 `--stall-seconds` 调）。

### 3.3 脑活 ⇒ 不触发（用例 C：脑活 + `finish` 已写 + 桥失联）

`logs\t9-guardian-selftest.txt:40-50`：

```
2026-10-18T17:37:36 [state] brain pid=3200 alive=True · journal lines=2 last=finish@100.0 age=0.1s finish=True stalled=False · bridge exists=False … lost=True · trigger=False
2026-10-18T17:37:36 [state]   脑活但桥失联 ⇒ 只告警，不退出（游戏必须开着）
2026-10-18T17:37:36 [exit] code=0（--once：只评估一拍，未触发）
```

- 断言全 PASS：`C 不触发（receipt 不存在）`、`C 日志含「脑活但桥失联 ⇒ 只告警」`、`C 日志无 stop 调用`、`C rc=0`。
- **注意**：C 的 `finish=True` 是刻意构造的「脑还没死但 finish 已写」竞态；按判据不触发（触发必须以脑死为前提）——不会在脑还活着时抢停游戏。

### 3.4 安全闸（用例 D：PID 文件缺失）与 `--dry-run`（用例 E）

- D（`:52-61`）：`PASS D 不触发（receipt 不存在）`、`PASS D 日志含「PID 文件缺失」安全闸`。
- E（`:63-76`）：`--dry-run` 命中判据时日志原文：
  ```
  [stop] 判据成立：判据成立：脑死 且 finish 已出现
  [stop] 命令：… -u …\scratch\_g_fake_stop.py --wait 1.0
  [stop] --dry-run：只打印不执行（不退出游戏）
  [exit] code=0（--dry-run 只演练，未退出游戏）
  ```
  `PASS E 不触发 stop（receipt 不存在）` ⇒ **演练不会误退游戏**。

### 3.5 脱离式起跑（用例 F）

`logs\t9-guardian-selftest.txt:78-92`：`PASS F 起跑 rc=0`、`PASS F 打印「已脱离式起跑」`、`PASS F guardian pid 文件已写`、`PASS F console 出现 start/exit`、`PASS F --once 子进程已自行退出（无残留看护进程）`。产物：`logs\t9-F-detach-guardian.pid`、`logs\t9-F-detach-guardian.console.log`（后者含 `[i] guardian start …` 与 `[exit] code=0`）。

---

## §4 用法（A9/B9 起跑命令怎么带它）

**一行（A9；B9 把 tag 换成 `longrun-runB9-0744`）**：

```
PYTHONUTF8=1 python tools\run-guardian.py --tag longrun-runA9-0744 --detach
```

- 起跑顺序：**先 `tools\start-detached-longrun.py`（长跑 pid 文件落盘）→ 再起看护**；看护也可先起（PID 文件缺失时走安全闸、只告警，pid 文件出现后自动接管）。
- 一行起跑示例（A9，0.7.44 冻结装机后由 Lead 放行）：

```
PYTHONUTF8=1 python tools\start-detached-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs/longrun-runA9-0744.jsonl --expect-version 0.7.44 ; PYTHONUTF8=1 python tools\run-guardian.py --tag longrun-runA9-0744 --detach
```

- 看护产物：`logs\longrun-runA9-0744-guardian.log`（逐条时间/判据/stop rc/进程 0/bridge.json/17890）、`logs\longrun-runA9-0744-guardian-state.json`、`logs\longrun-runA9-0744-guardian.pid`、`logs\longrun-runA9-0744-guardian.console.log`。
- 起跑后要做的只读复核（写进 A9 证据）：`Get-Process` 里有 guardian pid、guardian.log 有 `[i] guardian start` 与首条 `[state]`；跑完看到 `[exit] code=0 ✅` 即看护已完成收尾。
- 参数默认值（真机用默认即可）：`--stall-seconds 180`、`--interval 10`、`--bridge-stale-seconds 120`、`--stop-script tools\stop-game.py --stop-wait-seconds 45`；health 探测默认开（`--no-health-check` 可关）。

---

## §5 已知限制（未演练 / 边界）

1. **真机演练未做**（Lead 指令：A9 起跑前空档放行）。本次证据全部来自离线夹具；A9 起跑时是**首次真机使用**，起跑后需核对 guardian.log 的心跳与（收尾时）`[verify]` 三行。
2. 看护自身也是**单点**：guardian 进程死掉则无人收尾。缓解：`logs\<tag>-guardian.pid` + 心跳日志（默认 300s 一条）人工复核；A9 起跑后我会把「guardian 活着」列入每日只读巡检。
3. 触发条件是**脑死**；「脑活但游戏挂死/桥失联」按纪律只告警不退出（不越权），需要人工判断（本卡刻意如此）。
4. 只识别 `StardewModdingAPI.exe`（与 `tools/stop-game.py` 同口径）；若游戏以其它进程名/包装器启动，识别不到（当前装机不存在该形态）。
5. `--stall-seconds` 是「脑被 kill、日志无 finish」形态的兜底：默认 180s ⇒ 脑死后最多再看护 3 分钟才退游戏（可调小，但太小可能打断收尾写账本）。
6. `--detach` 的 guardian pid 文件只写进程号、不写 sidecar；如需四要素审计，结合 `logs\<tag>.version.json` 与 guardian.pid 时刻人工对齐。
7. 自测的「触发」证据来自**假 stop 脚本收据**（不碰真游戏，符合 Lead 的「离线两态」要求）；真 stop-game 的 rc/进程 0/bridge/17890 复核路径与假脚本同一段代码，但**真机读数要等 A9 实跑才有**。

---

## §6 提交物与自检

| 路径 | 说明 |
|---|---|
| `tools\run-guardian.py` | 看护守护（新增；不改生产代码） |
| `scratch\_t9_guardian_selftest.py` | 离线夹具自测器（30 项断言） |
| `scratch\_g_fake_stop.py` | 假 stop 脚本（夹具专用；不发请求/不 taskkill） |
| `docs\_run-guardian-evidence.md` | 本文件 |

- `PYTHONUTF8=1 python -W error::SyntaxWarning -m py_compile tools\run-guardian.py scratch\_t9_guardian_selftest.py scratch\_g_fake_stop.py` ⇒ **rc=0**（2026-10-18 17:37 实测）。
- 自测：`PYTHONUTF8=1 python scratch\_t9_guardian_selftest.py` ⇒ **30/30 PASS，rc=0**；完整原文 `logs\t9-guardian-selftest.txt`（UTF-8）。
- 未入库（`.gitignore` 的 `logs/` 与 `scratch/*` 规则）：`logs\t9-guardian-selftest.txt`、`logs\t9-F-detach-guardian.*`、`scratch\_gtest\` 夹具产物；它们留在盘上供 Lead 复核，本文件引用其行号原文。
- 提交：按路径 `git add`（禁 amend / 禁 `git add -A`）；提交后 `git show --stat HEAD` 自检。
