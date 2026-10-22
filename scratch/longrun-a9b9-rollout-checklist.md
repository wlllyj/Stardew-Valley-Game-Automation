# A9/B9 长跑起跑逐条清单（版本 **0.7.49**）

> 执行人：machine-runner（真机独占，主工作目录 `D:\OpenCode Workspace\星露谷游戏自动化`，不建 worktree）。
> 用途：**等 lead GO 后**逐条打勾执行。A9/B9 都**必须先等到**「0.7.49 已冻结 + 冻结 dll 哈希」的 GO。
> ⚠ 版本号一律 **0.7.49**（0.7.48 冻结已作废，见 lead 待命通知）。日志前缀一律 `-0749`。
> 环境：所有 Python 命令带 `PYTHONUTF8=1`；`python` = DSH 运行时
> `C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`；`brain/` CLI 需 `PYTHONPATH=<repo>\brain`。
> 真机铁律：游戏不允许无人值守挂着；长跑必须脱离式；禁 `--amend` / `git add -A`。

---

## 0. GO 门禁（未满足则不起跑）

- [ ] lead 已发 GO：**0.7.49 已冻结** + 冻结提交号 + 冻结 dll/manifest 的 **SHA256**
      （当前已知：冻结提交 `51ef0a7`，dll 293888 B / `C9B3BD6C…`，与 0.7.47/0.7.48 逐字节相同）。
- [ ] **GO 后第一步**：`python tools\deploy-mod.py` 装 0.7.49 → 判据：bridge `modVersion=0.7.49`、dll 哈希 == 冻结哈希。
- [ ] 记录 `git rev-parse HEAD`（主目录冻结提交）与冻结 dll 哈希，写入 A9 证据头。
- [ ] 现场干净三连：进程 `0` / `bridge.json` 不存在 / `17890` 无 LISTENING（下方 §1 复核）。
- [ ] 确认恢复目标存档存在：`logs\ab-backup\A9-start\`（四件 + `manifest.json`）。
- [ ] 确认 \`git\` 工作树状态已记（冻结提交锚定，A9/B9 provenance）。

## 1. 现场复位（只读核对，起跑前）

- [ ] `Get-Process -Name StardewModdingAPI,Stardew -ErrorAction SilentlyContinue` ⇒ 无输出（进程 0）。
- [ ] `Test-Path "$env:APPDATA\StardewValley\AgentFarm\bridge.json"` ⇒ `False`。
- [ ] `netstat -ano | Select-String ":17890"` ⇒ 无 LISTENING。

---

## 2. 【GO 后第一步】1 日 smoke-0749（验证 0.7.49 新口径在真机真的生效）

> ⚠ 顺序：本 smoke 通过 + lead 复核后，才进 §3 A9 臂。smoke 用 1 日短跑，跑完即优雅收尾、报回 lead。

- [ ] **S1** `python tools\deploy-mod.py` 装 0.7.49 ⇒ bridge `modVersion=0.7.49`。
- [ ] **S2** `python scratch\arm-start-helper.py restore --arm A9` ⇒ `VERDICT: RESTORED`。
- [ ] **S3** `python scratch\arm-start-helper.py verify --arm A9` ⇒ `VERDICT: SAME`。
- [ ] **S4** `tools\start-game.cmd` → `PYTHONPATH=brain python -m agentfarm load --save Wahaha_450799035` → `PYTHONPATH=brain python -m agentfarm goto Farm`。
- [ ] **S5** `PYTHONPATH=brain python tools\preflight.py --expect 0.7.49 --save-baseline logs\runA9-baseline.json` ⇒ `✅ 可以起跑`
      （**必须在 restore 之后重写**；restore 前那份是冬28档，作废）。
- [ ] **S6** smoke 跑（参数 lead 已批准）：`python tools\start-detached-longrun.py --days 1 --size 5 --max-minutes 60 --max-days 2 --journal logs\longrun-smoke-0749.jsonl`
      - 判据：账本出现 `finish`；新口径字段/事件在真机出现（按 task-38 快修口径核对，如 `slot_relief` 补全 task-237 字段）。
- [ ] **S7** 收尾三件（§3.4 的 C1–C5，前缀改 `smoke-0749`）+ `python tools\stop-game.py --wait 45` 优雅退 + 三连核对。
- [ ] **S7b 版本复证（lead 加）**：收尾时**再跑一次** `PYTHONPATH=brain python tools\preflight.py --expect 0.7.49`，
      并把 `health` 的 `modVersion` **原文**抄进报告（证游戏里挂的确实是 0.7.49，不是旧 dll）。

### 2.1 smoke 判据（lead 已写死闸口）

**硬闸口（任一不过 ⇒ 停下报 lead，不许进 A9）**
- [ ] 进程 `0`
- [ ] `bridge.json` 已删
- [ ] `17890` 无 LISTENING
- [ ] 存档四件 size+mtime+SHA256 退前退后**逐字节比对**（⚠ 注意 `*_old` 与主档会互换，比对的是**四件整体**）
- [ ] SMAPI 原文里 `modVersion` = **0.7.49**

**口径闸口（只报数、不判生死，交 lead 与判据）**
- [ ] ① `zone_blockers_total` 在 smoke 账本里的形态（有没有出现 **clump 计入后 ≠0** 的区）
- [ ] ② `day_end` 里 `buy`/`upgrade_tool` 意图的 `executed_steps` / `reasons`（D2 修完应当是**有动作才 1、无动作 0 + `unknown_evidence`**）
- [ ] ③ `ended_by` 原文

**明确不要做**：不为「让 smoke 好看」改任何代码/参数/判据 —— smoke 就是 0.7.49 在真机的第一次真实读数，越丑越有用。

- [ ] **S8** 报回 lead；等 lead 确认后再进 §3 A9 臂。

---

## 3. A9 臂（journal = `logs\longrun-runA9-0749.jsonl`）

### 3.1 恢复起点（写存档动作 —— 只有 GO 后才能做）

- [ ] **R1** 恢复：`python scratch\arm-start-helper.py restore --arm A9`
  - 判据：`rc=0` 且末行 `VERDICT: RESTORED`（四件逐字节 == 备份）。游戏必须处于停止态。
- [ ] **R2** 同起点核对：`python scratch\arm-start-helper.py verify --arm A9`
  - 判据：`VERDICT: SAME`（四件全 `OK`，`Wahaha_450799035` 3,141,826 B / `053CAA71…4AF7`）。

### 3.2 起游戏生效

- [ ] **G1** `tools\start-game.cmd`（启 SMAPI 与游戏；**不走 Steam**，免云存档覆盖测试档）。
- [ ] **G2** 读档：`PYTHONPATH=brain python -m agentfarm load --save Wahaha_450799035`
  - 判据：打印 `已进入存档 Wahaha_450799035：地点 … 格 …`；`health` 里 `hasSaveLoaded=true`。
- [ ] **G3** 落地：`PYTHONPATH=brain python -m agentfarm goto Farm`
  - 判据：打印已在 `Farm`，落点 `[64,15]` 一带（非床）。

### 3.3 基线 + 守护 + 脱离式起跑

- [ ] **P1** 基线：`PYTHONPATH=brain python tools\preflight.py --expect 0.7.49 --save-baseline logs\runA9-baseline.json`
  - 判据：`✅ 可以起跑`（`rc=0`）；基线 `day=26 winter` / `location=Farm` / HasSaveLoaded。
- [ ] **L0 零教训基线核对（关键）**：`logs\longrun-runA9-0749-lessons.json` 起跑前**必须不存在**
      （教训库路径由 journal 派生，见 `brain/agentfarm/longrun.py:1573-1583`；存在 ⇒ 会污染「零教训基线」⇒ **停，别起跑**）。
- [ ] **P2** 守护（**原样**起，不改一行）：`python tools\run-guardian.py --tag longrun-runA9-0749 --detach`
  - 判据：`logs\longrun-runA9-0749-guardian.pid` 落盘；`…-guardian.log` 出现心跳行。
- [ ] **L1** 脱离式长跑：`python tools\start-detached-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs\longrun-runA9-0749.jsonl`
  - 判据：脑 PID 落 `logs\longrun-runA9-0749.pid`，进程独立于会话（回合边界不掉）；journal 出现 `start` 行。
  - 记 argv：A9/B9 **只差 `--journal`**（其余 `--days 5 --size 5 --max-minutes 240 --max-days 12` 相同）。
- [ ] **L1b sidecar 核对**：`logs\longrun-runA9-0749.version.json` 里 **`boundary_llm=true`**（LLM 默认开）；并核五文件哈希 == 冻结。
- [ ] **L2** 每日 ≥2 份独立观测：`PYTHONPATH=brain python -m agentfarm observe full`（存 `scratch\`）。

### 3.4 A9 收尾三件（证据完整性，与钱无关）

- [ ] **C1 冻结 SMAPI 窗口**：脑停后，把 `%APPDATA%\StardewValley\ErrorLogs\SMAPI-latest.txt`
      复制 → `logs\runA9-0749-smapi-window.txt`，记 **行数 / size / mtime**。
      - 若被强制昏睡收尾：照实记该天 `ended_by`（如 `forced_sleep`），交判据/analyzer 判是否 VERIFIED。
- [ ] **C2 存档四件「退前」**：记 `Wahaha_450799035` / `SaveGameInfo` / `…_old` / `SaveGameInfo_old`
      的 **size / mtime / SHA256**（脑停后、退游戏前快照）。
- [ ] **C3 优雅退**：`python tools\stop-game.py --wait 45`（守护可能已自动执行）⇒ `rc=0`。
- [ ] **C4 存档四件「退后」**：同 C2 四项再记一遍 ⇒ 与 C3 前**逐字节比对**（跨日是否真落盘）。
- [ ] **C5 退后三连**：进程 `0` / `bridge.json` 已删 / `17890` 无 LISTENING。
- [ ] **C6 热身三天单列**：winter26 / winter27 / winter28 逐日单列冬26(满包无活) 与 winter27(resume 耗竭) 两 FAIL 形态读数
      （`inventory_blocked` 四门槛 / `resume_exhausted` / `stuck:`）。

---

## 4. B9 臂（journal = `logs\longrun-runB9-0749.jsonl`）

> 与 A9 **同起点**、同参数（argv **只差 `--journal`**）；唯一差异 = 起跑前注入 A9 的 lessons（对照臂）。

- [ ] **B-R1** 恢复同起点：`python scratch\arm-start-helper.py restore --arm A9` ⇒ `VERDICT: RESTORED`。
- [ ] **B-R2** 核对：`python scratch\arm-start-helper.py verify --arm A9` ⇒ `VERDICT: SAME`。
- [ ] **B-G1** `tools\start-game.cmd`。
- [ ] **B-G2** `PYTHONPATH=brain python -m agentfarm load --save Wahaha_450799035`。
- [ ] **B-G3** `PYTHONPATH=brain python -m agentfarm goto Farm`。
- [ ] **B-P1** `PYTHONPATH=brain python tools\preflight.py --expect 0.7.49 --save-baseline logs\runB9-baseline.json` ⇒ `✅ 可以起跑`。
- [ ] **B-LS lessons 注入（关键）**：把 A9 的教训库**字节拷贝**：
      `logs\longrun-runA9-0749-lessons.json` → `logs\longrun-runB9-0749-lessons.json`
      - 判据：**记两侧 size + SHA256，必须完全相同**（拷贝无损）。写入本清单下方「附表」或 A9/B9 证据头。
- [ ] **B-P2** 守护：`python tools\run-guardian.py --tag longrun-runB9-0749 --detach`。
- [ ] **B-L1** `python tools\start-detached-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs\longrun-runB9-0749.jsonl`。
- [ ] **B-L2** 每日 ≥2 份独立观测。
- [ ] **B-L1b sidecar 核对**：`logs\longrun-runB9-0749.version.json` 里 `boundary_llm=true`。
- [ ] **B 收尾三件**：同 §3.4 的 C1–C5（前缀改 `runB9-0749`）。

---

## 5. 判决 / 对照（跑完两臂后）

- [ ] `PYTHONPATH=brain python tools\verify-run3.py --days 5 --journal logs\longrun-runA9-0749.jsonl --smapi`
- [ ] `PYTHONPATH=brain python tools\verify-run3.py --days 5 --journal logs\longrun-runB9-0749.jsonl --smapi`
- [ ] `PYTHONPATH=brain python tools\analyze-longrun.py --journal logs\longrun-runA9-0749.jsonl --window 5`（同 B9）
- [ ] `PYTHONPATH=brain python tools\compare-runs.py --run-a logs\longrun-runA9-0749.jsonl --run-b logs\longrun-runB9-0749.jsonl`
      ⇒ 看 L0–L5：L0 需 `run A lessons ≥1 条且 ≥1 条 count>=1`，否则对照作废。
- [ ] 三检查器：`tools\verify-run3.py` + `tools\analyze-longrun.py` + `scratch\run9-lead-check.py`（独立复核器）。
- [ ] 双列读：`already` / `attempted_ok` 与 `ok` 分别列（不混算）。

---

## 附表：lessons 拷贝无损记录（B9 起跑前填）

| 侧 | 路径 | size | SHA256 |
|---|---|---|---|
| A9 源 | `logs\longrun-runA9-0749-lessons.json` | | |
| B9 目标 | `logs\longrun-runB9-0749-lessons.json` | | |

- [ ] 两侧 size 相同、SHA256 相同。

## 附表：A9/B9 起点四件（restore 后填）

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `Wahaha_450799035` | | | |
| `SaveGameInfo` | | | |
| `Wahaha_450799035_old` | | | |
| `SaveGameInfo_old` | | | |
