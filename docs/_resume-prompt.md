继续星露谷自动化项目（**目标不变**）。工作目录：`D:\Deepseek Harness Workspace\星露谷游戏自动化`（先 `pwd` 确认）。

**目标（原样，不要改）**：按 `docs\_p3-kickoff.md` 推进 P3 —— 让「脑」端到端自主完成"清理农场障碍 → 开垦 → 播种 → 浇水"，并**连续 3 个游戏日无人工介入**。已完成的顺序项：①把 watchdog 接进运行循环 ②`observe?detail=full` 增加逐格清单 `tiles[]`（快照升 `agentfarm-world/6`）③`use_tool` ④`select_item`/`plant` —— 都已真机验收；⑤的确定性部分 3x3 试点已过（8/9 格"清障→锄→种→浇"全链路差分通过，1 格跳过＝草）。剩余：⑤ 5x5 与边界决策层、⑥ 扩到目标区域跑满 3 个游戏日。

先读（按顺序）：`docs\_handoff.md`（交接总纲：状态表、已验收事实与数字、开发循环、踩坑清单、"新会话恢复 5 步"）→ `docs\00-开发日志.md` 最新条目（001–024，权威过程记录）→ `docs\03-桥接协议.md` §6/§8 与 `docs\_p3-kickoff.md`。

接着干：
1. `python -m unittest discover -s tests`（应 **45 OK**）；
2. `python tools\deploy-mod.py --no-quit`（游戏现在是**关闭**的：自动拉起 + 自动读档；Mod 0.7.18 已装机）；
3. `python tools\run-plot.py --size 5 --seed 472`（P3 ⑤ 确定性部分；跑完把结果与踩坑写进 `docs\00-开发日志.md` 新条目，倒序置顶）。

纪律（照做）：
- 改 Mod → `dotnet build` 必须 0 错 0 警 → 再用 `tools\deploy-mod.py` 装机+重启+读档；
- **验收一律用 `observe?detail=full` 的 `tiles[]` 差分**：回执只是声明，绝不拿回执当证据；
- 改文件用编辑工具或"先写 .py 再执行"（PowerShell 直接读写 UTF-8 会毁中文）；
- 探针优先：先用 `tools\api-probe`（编译期存在性：CS0117=不存在、CS1503=签名不同）与 `tools\il-probe`（IL 反汇编，支持 `Type|Method`、`FIND|子串` 搜"谁调用了 X"）把游戏 API 钉死，再写实现。

**接 LLM 之前必须先告诉我**（用户 m01184 的明确要求）：`brain\agentfarm\llm.py` 的慢脑只用于**边界决策**（换任务类型 / 异常恢复 / 跨日复盘），坐标与动作序列仍由技能层按当下世界状态计算。
