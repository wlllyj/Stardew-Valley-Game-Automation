# 0.7.27 发布计划（Lead 独占执行）

> 上一版：0.7.26（task-67 当季种子 + task-68 枯死作物开路 + task-73 stuck 日翻篇）已装机并跑完 run7。
> 本版目标：把 **P3 ⑥ 的最后一条腿（播种）** 接上，并修掉用户 2026-10-14 反馈里最刺眼的一条（死苗还在浇水）。

---

## §1 本版内容（逐卡验收通过后才入版）

| 卡 | 内容 | 作者 | 写盘范围 | 状态 |
|---|---|---|---|---|
| **task-55** | 经济闭环（二）：卖**盈余材料**换种子钱（每 id 保留 K=10、三条件门闸 `money < 5×seed_price` 且 `seeds_total==0` 且 `farm.emptyDirt>0`、`Money +=` 零写入） | dev-coder | `brain/agentfarm/{farmwork,longrun}.py` + `tests/` | **已交付 `6948bb4`**（Lead 代码级 PASS；桶漂移红归 task-91，标 completed 已授权） |
| **task-84** | 死苗不浇水：Mod 把 dry 拆「活苗/死苗」+ `water()` 排除死苗 + `clear_dead` 提到 `water_area` 之前 + `given_up` 格当天剔出「还有活」 | dev-coder | `mod/AgentFarm.Bridge/{FarmScan,Contracts}.cs` + `brain/agentfarm/{farmwork,longrun}.py` + `tests/` | in_progress（0.7.27 最后一张 Mod 卡） |
| **task-83** | 田块规整：固定当家田块 + `next_plant_tiles()` 行优先连续填空 + 同日不跨 zone | dev-coder | `brain/agentfarm/` + `tests/` | pending（**赶不上就挪 0.7.28**） |

⚠️ **Mod 有无改动决定是否 bump**：task-84 动 `mod/` ⇒ 必须 bump 到 0.7.27；若 task-84 掉卡（只剩 brain-only 卡），**不要 bump**，直接以 0.7.26 起 run8（此时本文件改名为「run8 执行记录」，本版号作废）。

## §2 冻结与装机九步（Lead 独占；踩过的坑写在括号里）

```powershell
# 0) 确认树干净（未跟踪的 scratch/*.py 也算脏 ⇒ 先 git add -A）
git add -A; git status --short

# 1) note 文件：首串必须是 v0.7.27，否则 _bump-mod-version.py 只告警不改版本
#    （tools/_note-0727.txt，列出 task-55/84/83 的内容）
python tools\_bump-mod-version.py 0.7.27 --note-file tools\_note-0727.txt
#    ⚠️ 该脚本最后一句 print 在 cp1252 下会抛 UnicodeEncodeError（版本已写盘）
#    ⇒ 必须用 json.load 读 manifest.json 核对 Version，不能只看退出码

# 2) 同步脑侧期望版本
#    brain/agentfarm/bridge.py:39  MOD_VERSION_EXPECTED = "0.7.27"

# 3) 编译（必须 0 警 0 错）
dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental

# 3b) 【Lead 独占】工具侧对齐本版新字段/事件（task-84 的 dead_crops/dry_dead/gave_up_tiles + task-55 的 sell 家族）
#     tools\verify-run3.py + tests\test_verify_run3.py：新字段缺失 ⇒ 只记 info（缺失≠通过）、
#     活苗 dry 口径对齐、不新增硬闸门；跑 `python -m unittest tests.test_verify_run3` 全绿。
#     ⚠️ 纪律（task-86 教训）：**任何口径变更都必须过一轮独立对抗验收**才能拿去判真机账本。

# 4) 提交冻结
git add -A; git commit -m "release: 0.7.27 (task-55 economy + task-84 dead-crop watering + task-83 layout)"

# 5) 六项发布检查（manifest==brain / 版本==期望 / dll 不比源码旧 / py_compile / 全量单测 / 树干净）
python tools\check-release.py --expect 0.7.27

# 6) 装机（会重启游戏并读档）
python tools\deploy-mod.py --no-quit

# 7) 走进农场（preflight 的「已读档+户外」两项要求人在 Farm）
python -m agentfarm goto Farm --no-focus        # 需要 PYTHONPATH=<repo>\brain

# 8) 起跑前自检 + 权威基线
python tools\preflight.py --expect 0.7.27 --save-baseline logs\run8-baseline.json

# 9) 交 task-89（machine-runner）用起跑器发 run8（先 --dry-run 看四要素）
python tools\start-detached-longrun.py --journal logs\longrun-3day-llm-run8.jsonl --expect-version 0.7.27
```

## §3 run8 起跑卡（Lead 建 task-89 派 machine-runner）

- 起跑器（首选）：`python tools\start-detached-longrun.py --journal logs\longrun-3day-llm-run8.jsonl --expect-version 0.7.27`；先 `--dry-run` 看四要素（HEAD / 5 个文件的 SHA256+mtime，含 Mod dll 与 manifest / PID / `git status --short`）。
- 手工 `Start-Process` 仅作备用（托管后台作业会在回合边界被连根收掉，见条目 040/041）。
- 轮询只读三样（PID 存活 / console 尾部 / 账本行数与尾事件），**不用 `job_output` 跑长跑**。
- `eventUp=true` 立刻停手上报，**绝不 dismiss**。
- 交付 `docs/_run8-evidence.md`（§1 起跑与版本四要素 / §2 外部证据 / §3 逐日表 / §4 判据对照（**两侧结论都要写**：旧口径 + 尾部窗口口径）/ §5 归因与遗留）。
- **起止外部快照必须做**（run7 的教训：`scratch/run7-external-snapshots.jsonl` 不存在 ⇒ 窗口内中间 5 次落盘 size 永久不可恢复）：起跑前 `python scratch\run8-snapshot.py --tag start`、结束后立刻 `--tag end`，输出 `scratch/run8-external-snapshots.jsonl`（存档 main + `_old` 的 size/mtime、SMAPI `lines/newday/save` 累计、账本行数与 `finish`、PID 存活、`bridge_info` 对 `--expected-mod-version 0.7.27`）。游戏存档只留两代 ⇒ 别承诺中间值。

## §4 run8 判据

**继承** `docs/_run6-criteria.md`：§1 真空日闸门、三家口径（`no_work` + `final_water.dry>0` ⇒ 红）、三腿覆盖、豁免不得洗白；§2 尾部窗口达标 + 落盘口径（**跨日 ≠ 落盘**；有日终菜单时不判失败也不判通过）。
**禁用**：`day_end.final.location == "Farm"`（`final` 是睡前快照，正常成功的一天会回 FarmHouse）。

**本版新增四条关注项（run8 的核心价值）**：

1. **同日全链**：至少一天里出现 `sell`（策略 = surplus_materials）→ `buy` 成交（当季、最便宜）→ `plant_area`/`sow` 的 `ok > 0` → `water_area` 覆盖到**新播的那几格**。顺序不看死（卖的钱要等下一次 `NewDay` 到账，允许跨日衔接），但**四条腿都要在同一条 run 里各至少成功一次**。
2. **`seed_gate {seeds:0}` 的日子显著减少**：run7 出现 5 次且 `buy` 0 次成交；run8 里若仍有 `seeds:0`，账本必须能说明是「钱没到账」而非「买不起」。
3. **死苗不再被浇水**：`water_area` 的 `tiles` 里**不含** `dead=true` 的作物格；`clear_dead` 的 stage 出现在 `water_area` 之前。
4. **田块规整（task-83 入版时才判）**：同一天播种的格连续成行、不跨 zone（用 `plot`/`plant_area` 的 `tiles` 与 `anchor` 核对）。

## §5 与 run7 对比（基线）

| 指标 | run7（0.7.26） | run8 期望 |
|---|---|---|
| 尾部连续 VERIFIED 天数 | **3**（summer 7/8/9） | ≥3 |
| `finish.code` | 0 | 0 |
| 播种腿 | **已跑通 4 格**（用背包里原有的 `MixedFlowerSeeds`；`sell`/`buy` 事件 0 条、`seed_gate seeds=0`×5） | 播后当日浇水覆盖新苗 + **≥1 次脑自主买种** |
| 死苗处理 | 无（`clear_dead` 0 ok） | `deadCrops` 下降 + 死苗不再被浇 |
| 早期历史问题 | 9 条（summer 3/5 够不着那 1 格干作物、summer 6 `stuck_flush` 翻篇） | 同类问题允许存在，但**窗口外不计 rc**、必须逐条写明 |

## §6 已知遗留（不入本版）

- `task-53`（农场级待清障/待开垦计数）、`task-58/59`（带决策史 + 收工复盘，B/C 件）、`task-14`（逐帧 warp 活锁）、`task-17`（world_stuck 自愈）、`task-20`（工具等级选择）。
- 结构性缺口：仓库**没有 C# 测试工程** ⇒ Mod 内部数值（跳预算、白名单判定）只能靠 build + 真机验收。
- 窗口外的 1 格干作物可能永远 `unreachable`（run7 的 summer 3/5）⇒ task-68 的 `encircled` 只解决"能开路的围住"，解决不了"整簇没有落脚点"。

## §7 冻结与装机执行记录（Lead 独占）

### §7.1 冻结（2026-10-15）
- `tools/_note-0727.txt`（首串 `v0.7.27（经济闭环第一步 + 死苗不再浇水）`，列 task-55/84）→ `python tools/_bump-mod-version.py 0.7.27 --note-file tools/_note-0727.txt` ⇒ `manifest: Version 0.7.26 -> 0.7.27`（**脚本末句 `print` 在 cp1252 下抛 `UnicodeEncodeError` ⇒ 退出码 1 但版本已写盘；核对一律用 `json.load` 读 Version，不看退出码**）。
- `brain/agentfarm/bridge.py:39 MOD_VERSION_EXPECTED = "0.7.27"`（注释列本版两项内容）。
- `dotnet build .\mod\AgentFarm.Bridge\AgentFarm.Bridge.csproj -c Release --nologo --no-incremental` ⇒ **0 警 0 错**；`AgentFarm.Bridge.dll` **172032 B @21:26:06**、`manifest.json` **21468 B @21:26:04**。
- 工作树清干净后提交 **`e23481e`**（`git add -A` 必需：未跟踪的 `scratch/*.py` 会被 `check-release` 算成脏）。
- 工具侧对齐提交 **`fdb87d8`**（`tools/verify-run3.py` 收 task-84 的 5 个 `day_end` 字段 + 新闸门 `no_work` + `dry_dead>0` ⇒ problem；`gave_up_dry` 只记 info；缺 `dry_dead` 的旧账本只记 info；`tests/test_verify_run3.py` 50 OK）。
- **放行条件**：`check-release.py --expect 0.7.27` 必须六项全绿 —— 首次跑时唯一红是 `TestEventMappingDrift`（task-84 的新事件 `dead_crops_summary` 未入 `EVENT_BUCKETS`），作 **task-95** 派 log-analyst；**树不绿不装机**（v0.7.17 教训）。

### §7.2 装机与起跑前预置（待 task-95 交付后执行）
1. `python tools/check-release.py --expect 0.7.27` ⇒ 六项全绿（含 `Ran N tests / OK`、工作树干净）。
2. `python tools/deploy-mod.py --no-quit`（0.7.26 → 0.7.27；记录 dll/manifest 字节数与 `modVersion`）。
3. `python -m agentfarm goto Farm --no-focus`（需 `PYTHONPATH=<repo>\brain`）⇒ 户外农场，否则 `preflight` 的户外判据红。
4. `python tools/preflight.py --expect 0.7.27 --save-baseline logs/run8-baseline.json` ⇒ 四项全绿才算"可以起跑"。
5. **预置（若 `seeds_total==0` 且 `money < seed_price`）**：`scratch/run6-preseed.py` 出货（**每 id 保留 K=10 做不到：Mod `ShipSkill` 只能整叠出货**，见 §7.1 备注）→ `scratch/verify-sleep-brain.py --from-farm` 睡一夜收款 → 复核 `money ≥ 20g`；红线：只走 `sell`/`sleep`/`buy` 三条已验收路径，**绝不 `Money +=`、绝不手改存档**；同夜「有 `ShippingMenu` 时保存被设计推迟」属正常（`docs/_il-newday-save.md`）。
6. 起跑（**脱离式**，见 `docs/00-开发日志.md` 条目 040：DSH 托管后台作业会在回合边界被连根收掉）：`python tools/start-detached-longrun.py --journal logs/longrun-3day-llm-run8.jsonl --expect-version 0.7.27`（先 `--dry-run` 看四要素）；交付 `docs/_run8-evidence.md`（5 节）。
7. 证据纪律：跑完**先别退游戏**；`docs/_runN-evidence.md` §4 必须并列 `tools/verify-run3.py` 的 `verdict` 与 `strict_verdict` 两行（严格口径只呈现、不改 rc），并逐条抄出 `history_problems`。
