# AGENTS.md（仓库硬纪律 —— 所有 agent 会话必读）

> 这份文件是**纪律**，不是建议。违反其中任何一条，评审一律打回。
> 项目背景、架构与历史见 `docs/00-开发日志.md`、`docs/01-架构设计.md`、`docs/_release-*.md`。

## 0. 角色与写范围（Lead 之外）

- **Lead（队长）独占**：`docs/00-开发日志.md`、`logs/`、部署/冻结（`tools/deploy-mod.py`、`_bump-mod-version.py`、`git tag` 类动作）、任务板（`team_task_*`）、与用户对话、最终验收结论。
- **dev-coder**：生产代码（`brain/`、`mod/`、`tests/`）唯一写者；同一时刻只做一张卡（串行）。
- **machine-runner**：真机独占（启游戏 / 起长跑 / 观测 / 优雅退游戏）；只写 `docs/_run*-evidence.md`、`docs/_smoke-*.md`、`logs/`、`scratch/`。
- **log-analyst**：只读代码与账本；只写 `tools/analyze-longrun.py`、`tests/test_analyze_longrun.py`、`docs/_analyze-*.md`、`docs/_il-*.md`、`scratch/`。
- **deputy-lead**：只读生产代码；只写 `docs/_review-*.md`、`scratch/`；不改任务板、不 deploy、不碰游戏。
- **product-observer（旁观者）**：只读生产代码与账本；只写 `docs/_observe-*.md`、`scratch/`；不改任务板、不 deploy、不碰游戏、不改任何判据、不写生产代码。职责＝整体观察与问题发掘（缺口清单：缺口 / 现有证据 / 建议卡面 / 可验证判据）。
- 越界写入 ⇒ 评审直接 FAIL，不看功能对不对。

## 1. Git 纪律（血泪教训：条目 079/080）

- **全仓禁止 `git commit --amend`**。它会改写历史、替换掉别人的提交（已发生一次：把 Lead 的文档提交 `bb40a55` 顶掉）。
- **禁止 `git add -A` / `git add .`**：只按路径加自己的文件。提交前 `git diff --cached --name-only` 逐条核对，提交后 `git show --stat HEAD` 自检。
- 提交信息用 `类型(范围): 一句话`（如 `fix(longrun): 收尾关掉推迟保存的模态`）。
- 工作树里别人的在制改动**不许**顺手提交或回滚。

## 2. 运行环境纪律

- **所有 Python 命令必须带 `PYTHONUTF8=1`**（否则 C# 自检的 UTF-8 输出会被按 cp1252 解码导致假红；本机 `preferred=cp1252`）。
- 跑单测的结论**只看 `Ran N tests / OK`**（`unittest` 往 stderr 写东西会让 pwsh 报 `[exit code: 1]`，不要据此判失败）。
- `python` 必须用 DSH 运行时：`C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`（系统 `python` 是 Windows Store 桩，静默失败）。
- 跑 `brain/` 下的 CLI 需 `PYTHONPATH=<repo>\brain`。
- **PowerShell 直接读写 UTF-8 会毁中文**：写文件用编辑工具或 Python；读文件用 `read` 工具。`Get-Content`/`>` 重定向出的是 UTF-16LE 或乱码。

## 3. 真机（游戏）纪律

- **游戏不允许无人值守挂着**：人不在跑就必须 `tools/stop-game.py` 优雅退出。已发生 3 次 2:00 强制昏睡、每次扣 10% 金币（`-251`/`-226`/`-279`）。
- 长跑必须**脱离式**起跑（`tools/start-detached-longrun.py` / `Start-Process`），不能用会话托管的后台作业（回合边界会被 teardown；已发生 run4 只跑 13 秒）。
- 真机做完必须：冻结 SMAPI 窗口 → 记存档四件 size/mtime/SHA256（退前退后逐字节比对）→ 优雅退出 → 核对进程 0 / `bridge.json` 已删 / 17890 无 LISTENING。
- **跨日 ≠ 落盘**：前一天有出货（`displayedShippedItems`）时游戏先压 `ShippingMenu`，`SaveGameMenu` 被推迟；跑尾声必须关掉它（见 task-236）。

## 4. 验收纪律（最常被违反）

- **判据一律用独立观测差分**：不信回执、不信自述；`observe?detail=full` 的 `tiles[]`/`farm` 计数 + 存档 + SMAPI 原文才是证据。
- **缺失 ≠ 通过**：字段/文件/事件缺失时写【无法判定】，不许当 PASS。
- **变异必须报实测杀数**：作者自报的杀数不算证据，必须能在 `git archive` 冻结树上复跑出来。
- **骨架/探针自己的 bug 与产品 bug 分开判**：探针误判要改判据，不许改结论。
- 沙箱/工具限制不是理由：把"读不到"如实写进结论，不许猜。

## 5. 数值安全（钱与物品）

- **绝不自己写金钱**（`money +=` / `Game1.player.Money = …` 一律禁止）。所有经济动作必须走游戏入口（`ShopMenu.tryToPurchaseItem`、`Farm.shipItem`、`sell` 技能），并用观测差分验证。
- 卖东西必须走白名单 + 建造预留 + 每 qid 保留下限；工具/武器/种子/建材/锭类永不卖。
- 播种/收获/放置等世界写入必须走游戏自己的入口；绕过入口直改世界时**必须补齐游戏的完整语义**（条目 000：播种不扣种子事故）。

## 6. 报告纪律

- 交付必须带：①`git show --stat` ②`py_compile -W error::SyntaxWarning` 读数 ③定向/全量单测原文 ④变异实测杀数 ⑤事件/字段清单（新增项单列）⑥已知限制。
- 不许只写"已完成""已修复"而无数字。结论必须有文件:行号或命令输出为证。
