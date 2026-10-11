# 星露谷游戏自动化（Stardew Valley Autonomous Agent）

让 AI **完全自主**地玩《星露谷物语》：自己规划长期目标，自己操作角色干活，全程无需人工介入。

---

## 当前状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| **P1** | **架构设计** | ✅ 已完成 —— [架构 v1.0 已冻结](docs/01-架构设计.md)，8 项决策全部拍板 |
| **P2** | **跑通基本操作**（连得上 / 看得见 / 动得了 / 能走出屋） | 🟡 **进行中** —— 协议与 Python 脑骨架已通；C# 桥 Mod 编写中 |
| P3 | 端到端：农场清障 + 开垦 + 种田，无人介入跑通 | ⬜ 未开始 |
| P4+ | 温室/社区中心/采矿/钓鱼/畜牧/社交等能力扩展 | ⬜ 未开始 |

**最近更新**：2026-10-11 —— 启动 P2；桥接协议定稿；Python 脑骨架 + 假 Mod + 11 个单元测试全过；大模型通路接通并实测开销。详见 [开发日志](docs/00-开发日志.md)。

---

## 设计要点（一句话版）

- **脑体分离**：SMAPI Mod 当"手和眼"（确定性、主线程执行），外部 Python 进程当"脑"（规划、记忆）。LLM 不碰帧。
- **LLM 只出任务意图，不出坐标动作清单**——坐标与动作由技能层按**当下**世界状态计算（旧方案正是死在这里）。
- **闭合反馈环**：每个动作都有前置校验、后置校验、机器可读的失败原因；失败必须回流到决策层与经验库。
- **进度契约**：任务在预算内无状态改善 → 强制改变行为（重试→换路→换目标→上报），禁止空转。
- **只信游戏证据**：任务只有 `VERIFIED`（游戏状态差分证实）与 `needs_review` 两种终态，后者不许冒充完成。
- 详见 [架构设计](docs/01-架构设计.md)。

---

## 快速上手

```bat
rem 医生检查：能不能连上 Mod、看到什么、版本对不对（需要游戏已启动并加载存档）
tools\agentfarm.cmd doctor

rem 打印一行世界摘要
tools\agentfarm.cmd observe

rem 让角色走到指定格（真实移动）
tools\agentfarm.cmd move 64 15

rem 每 2 秒打印一次世界摘要（真机测试时的"眼睛"）
tools\agentfarm.cmd watch

rem 无人值守体检：世界在推进吗／失焦暂停关着吗／有没有挡路弹窗
rem 退出码就是结论：0=ok  1=warn  2=stop（stop 会写 logs\stops\ 事故报告）
tools\agentfarm.cmd triage

rem 跨地点移动（按游戏真值的 warp 图 + 建筑门做 BFS；--tile 可省）
tools\agentfarm.cmd goto Farm

rem 从标题界面读档 / 让游戏自己退出（换 Mod dll 必须重启游戏，这两条配对使用）
tools\agentfarm.cmd load
tools\agentfarm.cmd shutdown --force-after 30

rem 无人值守部署闭环：备份存档 → 自己关游戏 → 换 dll → 自己开 → 自己读档 → 自检
python tools\deploy-mod.py

rem 落点契约验收（回执 ok 是否真的停在目标格；退出码 0=通过 1=破裂 3=版本不对）
python tools\verify-landing.py --rounds 10

rem 检查大模型通路（不会打印密钥）
tools\agentfarm.cmd llm-check

rem 跑单元测试（不需要游戏）
python -m unittest discover -s tests -v
```

**没有游戏也能开发**：先起一个假 Mod，再用 `AGENTFARM_BRIDGE_JSON` 把脑指过去。

```bat
python tools\fake_bridge.py --port 17899 --out brain\run\fake-bridge.json
set AGENTFARM_BRIDGE_JSON=%CD%\brain\run\fake-bridge.json
tools\agentfarm.cmd doctor
```

---

## 文档导航

| 文档 | 内容 |
|---|---|
| [00 · 开发日志](docs/00-开发日志.md) | **持续追加**的开发过程记录（最新在最上），含规则与模板 |
| [01 · 架构设计](docs/01-架构设计.md) | 分层架构、七层契约、地点拓扑、veto 原因码、验收标准、风险登记 |
| [02 · 环境实测快照](docs/02-环境实测快照.md) | 游戏/SMAPI/.NET/Python 版本、Mod 清单、遗留进程处置 |
| [03 · 桥接协议](docs/03-桥接协议.md) | **Mod ↔ 脑的唯一契约**：传输、服务发现、health/observe/exec、状态码 |
| [04 · 配置与密钥](docs/04-配置与密钥.md) | 密钥约定、环境变量、模型选型、实测开销、环境陷阱 |
| [knowledge/](docs/knowledge/INDEX.md) | 旧项目已验证的 API 知识（带可信度标注）、设计模式、失败教训 |
| [_legacy-audit](docs/_legacy-audit.md) | 旧 `stardew-auto-farm` 全量盘点（协议/执行层/根因/可复用资产） |
| [_external-research](docs/_external-research.md) | 外部同类项目与学术调研（stardew-together / StarDojo / SPIKE 等） |

---

## 本机事实基线（关键几条）

- 游戏 **Stardew Valley 1.6.15** + **SMAPI 4.5.2**，位于 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`
- **Git 2.55.0** 已安装，仓库已初始化（分支 `main`）
- .NET SDK 6.0.136 / 6.0.428；DSH 自带 Python 3.12（裸 `python` 是 Microsoft Store 占位符，**不要直接用**）
- **慢脑**：DeepSeek `deepseek-flash`（推理模型）。实测一次真实规划 **41.4 秒 / 7123 token**
- 旧方案的守护进程已停止、6 个旧 `AutoFarm*` mod 已移出 `Mods\`（归档于 `Mods.disabled-旧AutoFarm-20261011\`）

---

## 目录结构

```
星露谷游戏自动化/
├─ README.md
├─ docs/                 文档与知识资产（00~04 + knowledge/ + 两份调研）
├─ mod/                  体：C# / SMAPI Mod（感知 + 动作原语 + 本地 RPC）
│  └─ AgentFarm.Bridge/
├─ brain/                脑：Python
│  ├─ agentfarm/         bridge.py（桥客户端） / llm.py（大模型） / __main__.py（CLI）
│  ├─ data/              静态知识（crops.json 等）
│  └─ run/               运行态（不进版本库）
├─ tools/                诊断与运维（agentfarm.cmd / fake_bridge.py / analyze_log.py / parse_save.py / il-probe）
├─ tests/                单元测试（不需要游戏）
└─ secrets/              密钥（**不进版本库**）
```
