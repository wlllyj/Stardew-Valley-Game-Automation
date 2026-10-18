# 0.7.40 发布记录（2026-10-18）

> 本批 = **全脑侧修复批次**（Mod 无代码变更，dll 与 0.7.39 字节相同）；
> 目的 = 修掉 0.7.39 七步真机冒烟抓出的两个真缺陷，为 **A″/B″ 长跑**扫清最后障碍。

## §1 卡片与状态

| 卡 | 内容 | 状态 | 提交 |
|---|---|---|---|
| task-233 | 非片区意图（ship/sell/sleep/review/recover_stamina/wait_for_save）失败不许裸用 `no_target`，证据不可用 ⇒ `unknown_evidence` + `unknown_why`；ship 失败带自有证据包 | ✅ 已交付并亲核（全量 1156 OK、m233a/b 各杀 1） | `cb1fb05` |
| task-232 | 空格压力通道：`slot_relief` 在 `free_slots <= SLOT_RESERVE` 时按三档已知表卖叠腾格；`NEVER_SELL` + 表外 fail-closed；每 qid 留 K=10；只走 `worker.sell()` + 钱/背包行数双差分 | ✅ 已交付并亲核（全量 1168 OK、m232a/b/c 合计杀 7） | `6a7f100` |
| task-232 增量 | 建造预留表 `SLOT_RELIEF_RESERVES = {"(O)378": 25, "(O)390": 30, "(O)382": 5}`；reserve>0 时**永不整叠卖空**（宁可腾不出格子） | ✅ 已交付并亲核（全量 1171 OK、m232d 杀 3） | `a4cd307` |
| task-234 | 0.7.40 delta 独立对抗验收（A/B/C/D 四段 + 七条作弊通道 + 变异两列） | 进行中（deputy-lead） | — |
| task-113 | A″/B″ 复跑（**同起点协议**，见 §5） | blocked_by task-234 | — |

## §2 冻结与装机（Lead 执行）

1. `tools/_note-0740.txt`（首串 `v0.7.40`）→ `tools/_bump-mod-version.py 0.7.40 --note-file …` ⇒ `manifest.json` Version `0.7.39 → 0.7.40`、Description 头部插入本批说明。
2. `brain/agentfarm/bridge.py:39` `MOD_VERSION_EXPECTED = "0.7.40"`（注释列出本批两条 + `--- 历史 ---` 保留 v0.7.39 全文）。
3. `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警告 0 错误**；dll **281088 B**（与 0.7.39 字节相同）、manifest **64311 B**。
4. C# 自检 `dotnet run --project .\mod\AgentFarm.Bridge.Tests\… -c Release` ⇒ `OK 85 断言全部通过`。
5. 冻结提交 **`6f9b797`**（`0.7.40 冻结: 非片区意图证据(task-233) + 空格压力通道/建造预留(task-232)`）。
6. `tools\check-release.py --expect 0.7.40` ⇒ **六项全绿**（`Ran 1171 tests`、工作树干净）。
7. `tools\deploy-mod.py --no-quit` ⇒ `0.7.39 → 0.7.40`，桥 `modVersion=0.7.40 port=17890`，自动读档 `Wahaha_450799035` → FarmHouse (9,9)。
8. `python -m agentfarm goto Farm`（需 `PYTHONPATH=<repo>\brain`）⇒ ok，`hop1 [3,12]→[64,15]` 7645ms。
9. `tools\preflight.py --expect 0.7.40 --save-baseline logs\run10h-baseline.json` ⇒ ✅
   基线：**第 1 年 秋 26 日 06:10 sunny / Farm(64,15) / 体力 270/270 / 钱 1977g / 农场[草 523 石 106 枝 73 树 780 耕地 79 作物 34] / crops 34 / unwateredCrops 2 / dryCrops 34 / waterLeft 6 / tillableCount 141 / tileCount 400 truncated / 无模态 / worldAdvancing true**。

## §3 0.7.40 五文件指纹（A″/B″ 只比这五个 + argv）

```
longrun.py   B432CC5439B6D2FCA6E99E938AF688A66D96520281D3EA066C988277C0C6231E  (547868 B)
farmwork.py  B7B4545414DC47E7D5392550E179B8113C645CAE1111950A3F4E678E3F6C76B3  (222811 B)
bridge.py    84281FEE6F125AF4FC901B1602D6402CD98F749C4B745DC071E3F84AA2D71B30  (64904 B)
dll          FF05225C6846D80C6CCF4E8B16A15F399FACCBED572705DF886486A8E419BD08  (281088 B)
manifest.json 57280F1D33AF2D5DEBCB7369A44E030B1B35CA26CC0A9D978434BE274AA35869  (64311 B)
```

## §4 判据（本批验收口径）

- **A 段（task-233）**：ship 无 plot 证据 ⇒ `unknown_evidence` + `unknown_why`，`reasons` 里无裸 `no_target`；片区任务取消**仍** `no_target` + `evidence.stage_tiles_empty is True`；旧账本 ⇒【无法判定】不判红；analyzer 的 `missed:intent_no_target_evidence:*` 消失。
- **B 段（task-232）**：满包+熟作物+有盈余 ⇒ 先腾格再收；满包+无盈余 ⇒ 如实 `inventory_blocked` 且 `failed_steps==0`；`NEVER_SELL`/表外一件不卖；建造预留不被整叠卖空；有界 ≤3 轮 ≤5 叠；**双差分不符 ⇒ 不许判成功**。
- **C 段（真机冒烟 A2 版）**：步 4 日报告不再全 `inventory_blocked`（`slot_relief.freed>0`、`sold[]` 可核）；步 7 analyzer 红里无 `missed:intent_no_target_evidence:ship`；步 3 用 A2 判据（树格有界连续 `use_tool` ≤3 次、`tree→stump`/消失即 PASS，`tool_ineffective` 不作失败证据）。
- **D 段**：七条作弊通道逐条实测不过。

## §5 A″/B″ 起跑（task-113 rev17，同起点协议）

1. 七步冒烟跑完、优雅退游戏后，备份存档目录四件（`Wahaha_450799035` / `SaveGameInfo` / `Wahaha_450799035_old` / `SaveGameInfo_old`）→ `logs/ab-backup/A6-start/`，逐件 size/mtime/SHA256 写进证据 §1。
2. A″ 跑 5 天 → 优雅退游戏 → 冻结 SMAPI + 存档四条 + 六串。
3. **恢复同一起点**（四件拷回，逐件 SHA256 必须与备份完全一致；不一致 ⇒ 停下报 Lead）。
4. B″ 跑 5 天（`logs/longrun-runB6-0740-lessons.json` = A″ lessons **字节拷贝**，记两侧 SHA256）。
5. 两臂 baseline 的 `day/timeOfDay/money/farm counts/stamina` 逐字段应完全相同；唯一允许差异 = 教训库。
6. 起跑：`tools/start-detached-longrun.py --days 5 --size 5 --max-minutes 240 --max-days 12 --journal logs/longrun-run{A6,B6}-0740.jsonl --expect-version 0.7.40`；每日 ≥2 份独立观测。
7. 判据：尾部连续 5 日 `verified=true`（`verify-run3 --days 5` rc=0 + `strict_verdict` 窗口零问题）+ 独立观测 + 六串 ≥5/5 + L0–L2 成立；L5 措辞按 §7.1 第 5 条门禁。

## §6 已知限制

- 本批**不解决**：熔炉建造/铜斧升级链（task-227）、床上读档坑（task-229）、compare-runs 口径（已于 task-217 修）、195/196/193/197 backlog。
- 真机冒烟 A2 版之前步 3 的红是**判据过严**（非缺陷），旧口径已作废（`docs/_smoke-0739.md` 有记录）。
- `slot_relief` 卖叠是"策略自身动作"，不进 `intent_coverage`（避免污染 LLM 意图对账）。
