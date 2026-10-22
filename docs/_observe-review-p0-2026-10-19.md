# 独立验收：P0 批（0f72f3c→bbb6a89）· D1 / buy / verify-zone-retention（observer · 2026-10-19）

> 卡面：T15（Lead 指定 observer 为本批 P0 的**独立验收人**；deputy-lead 因利益冲突仅作二审）。
> 写范围：仅本文件（`docs/_observe-*.md`）+ `scratch/`。**未改生产代码、未动任务板、未碰游戏、未 deploy**。
> 方法：只读代码 + `git show` + 用**真实函数**跑最小观测（`scratch/observe_t15_d1_minobs.py`）。
> 基线：`git rev-parse HEAD` = `80de585`（含 P0 批 `0f72f3c..bbb6a89`）。路径约定：`brain/agentfarm/*.py`、`mod/AgentFarm.Bridge/*.cs`、`tools/*.py`、`logs/*.jsonl`。

## 0. 三个判决（先给结论）

| 项 | 判决 | 一句话 |
|---|---|---|
| A · D1 | **D1 成立** | `ZONE_BLOCKER_KINDS` 缺 `"clump"`；Mod 对 ResourceClump 只发 `kind="clump"` ⇒ 大障碍永不计数；最小观测实测：区内 1 桩+1 草报 `blockers=1`（应为 2） |
| B · buy 分支 | **真实购买** | 链路 `longrun.py:9043`→`_preconditions`→`worker.buy`→Mod `BuySkill`→反射 `ShopMenu.tryToPurchaseItem`；Mod 侧按**钱/背包差分**判成败（`BuySkill.cs:246-265`）。保留两点见 §B.4 |
| C · verify-zone-retention | **需修后用** | fail-closed 与"无硬编码坐标"成立；但**继承 D1 ⇒ 假 PASS**：区内只剩树桩时报 `0/0 PASS (retained clear)` 且 `exit=0`（实测） |

---

## A. D1（阻断级缺陷）—— 判定：**D1 成立**

### A.1 Mod 契约：tile `kind` 的完整取值集合
`mod/AgentFarm.Bridge/Contracts.cs:588-593`（`TileView.Kind` 的 XML 文档，逐字）：
```
/// `weed`（杂草）/ `twig`（树枝）/ `stone`（可敲石头）/ `object`（其它放置物，如机器、箱子、掉落物）/
/// `tree`（树）/ `fruitTree`（果树）/ `clump`（资源堆）/ `grass`（草）/ `dirt`（耕地）/
/// `bush`（灌木）/ `unknown`。
[JsonPropertyName("kind")] public string Kind { get; set; }
```
⇒ **`clump` 在取指集合内**。`Contracts.cs:598` 明写：**只有 `kind=="clump"` 才填 `clump*` 元数据**。

### A.2 子类型在 `clumpKind`，`KindOf` 永不返回 `"clump"`
`mod/AgentFarm.Bridge/ClumpMeta.cs:38` 文档 + `:39-73` 实现 —— `KindOf(int?)` 返回值集合 = `stump`(600) / `log`(602) / `boulder`(672) / `rockPile`(148,622) / `greenRain`(≥752) / `unknown`。**不含 `"clump"`**。

### A.3 Mod 侧"ResourceClump ⇒ kind=clump"的**唯一**落点
`mod/AgentFarm.Bridge/WorldSnapshot.cs:807`：
```
else if (tf is StardewValley.TerrainFeatures.ResourceClump clump) { t.Kind = "clump"; FillClumpMeta(t, clump); }
```
（`FillClumpMeta` 在 `WorldSnapshot.cs:453`，`:460 t.ClumpKind = ClumpMeta.KindOf(index)`。）
⇒ 观测里大障碍的 `kind` **只可能是 `"clump"`**，`stump/log/boulder/...` **只出现在 `clumpKind`**。

### A.4 `fields.py` 的判定点（`ZONE_BLOCKER_KINDS` / `BLOCKER_KINDS`）
- `brain/agentfarm/fields.py:56` `BLOCKER_KINDS = frozenset({"weed","stone","twig","tree","bush"})`
- `brain/agentfarm/fields.py:60` `ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {"stump","log","boulder","rockPile","greenRain"})` —— **不含 `"clump"`**
- 判定点（全部用 `tv.get("kind") in …`，比的是 tile `kind` 而非 `clumpKind`）：
  - `fields.py:321`（`zones_from_observe`，`Zone.blockers`）
  - `fields.py:363`（`zone_blockers_total`）
  - `fields.py:506`（`plot_in_zone`，`b_in` 障碍桶）
- 全仓 `grep` 确认：`clumpKind` **在 `brain/` 下零命中** ⇒ 脑侧从不读子类型。

### A.5 P0-1（`0f72f3c`）改了什么
`git show 0f72f3c` 逐字：`- #: kind ∈ BLOCKER_KINDS` → `+ ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {"stump","log","boulder","rockPile","greenRain"})`（并把 `:321`/`:483` 的 `BLOCKER_KINDS` 改成 `ZONE_BLOCKER_KINDS`）。
⇒ 它加的是**只出现在 `clumpKind` 的 5 个串**，而 tile `kind` 永不为这些 ⇒ **在真实观测上是死代码**，D1 未被修复。

### A.6 动态复现（最小观测 + 真实函数）
探针：`scratch/observe_t15_d1_minobs.py`（直接 import `agentfarm.fields`，调 `zones_from_observe` / `zone_blockers_total`）。
最小观测：x/y 各 0..19 ⇒ split=2 → `field_nw/ne/sw/se`；`field_nw` 内放 `{kind:clump,clumpKind:stump}` + `{kind:weed}`；`field_ne` 内放 `{kind:stone}` + `{kind:clump,clumpKind:boulder}`。

命令原文与读数：
```
$ PYTHONUTF8=1 python scratch/observe_t15_d1_minobs.py
ZONE_BLOCKER_KINDS = ['boulder', 'bush', 'greenRain', 'log', 'rockPile', 'stone', 'stump', 'tree', 'twig', 'weed']
BLOCKER_KINDS      = ['bush', 'stone', 'tree', 'twig', 'weed']
'clump' in ZONE_BLOCKER_KINDS = False
'stump' in ZONE_BLOCKER_KINDS = True

zones_from_observe ->
  field_nw   bounds=(0, 0, 9, 9) blockers=1 tillable=10
  field_ne   bounds=(10, 0, 19, 9) blockers=1 tillable=10

zone_blockers_total(zone, obs) ->
  field_nw   -> 1
  field_ne   -> 1

反事实补 'clump' 后 ->
  field_nw   blockers=2 zone_blockers_total=2
  field_ne   blockers=2 zone_blockers_total=2

tilesTruncated=True 时 zone_blockers_total -> [None, None, None, None]
```
判读：`field_nw` 实含 2 个障碍（桩+草）却只报 `1`；补 `"clump"` 后变 `2`。⇒ **大障碍被静默漏计**。
`tilesTruncated=True` ⇒ 全 `None`（fail-closed 生效，见 §C①）。

### A.7 结论
**D1 成立**：`fields.py:60` 的 `ZONE_BLOCKER_KINDS` 缺 `"clump"`，Mod（`WorldSnapshot.cs:807` + `Contracts.cs:588-593`）只发 `kind="clump"` ⇒ `fields.py:321/363/506` 永不命中 ResourceClump。P0-1 加错串（子类型加进了 tile-kind 口径），**未修复 D1**。指定作业区「清空」在"只剩桩/圆木/巨石"时**假成立**。

---

## B. `bbb6a89` 的 `buy` 分支 —— 判定：**真实购买**

### B.1 调用链（逐环 `文件:行号`）
1. `brain/agentfarm/longrun.py:9042-9054`（`bbb6a89` 新增）：`if task == "buy": changed = self._preconditions(obs, rep)`（`:9043`）→ `_record_intent(executed_steps=1 if changed else 0, reasons={} if changed else {"unknown_evidence":1})`（`:9049-9052`）。
2. `longrun.py:7379 _preconditions` → `:7393 if self._preconditions_apply(obs, rep):` → `:7395 fresh = self._snap()`。
3. `longrun.py:7402 _preconditions_apply` → `:7587 st = self.worker.buy(item, n, shop=self.shop)`。
4. `brain/agentfarm/bridge.py:1117 def buy(...)` → `:1138 return self.exec_skill("buy", {"item":…,"count":…,"shop":…})`。
5. Mod：`mod/AgentFarm.Bridge/Skills.cs:442 case "buy": return new BuySkill(req, world, monitor).Step;`（`BuySkill.cs:56 internal sealed class BuySkill`）。
6. **游戏入口**：`mod/AgentFarm.Bridge/BuySkill.cs:300-304` 反射取 `ShopMenu.tryToPurchaseItem`（`BindingFlags.Instance|NonPublic`），`mi.Invoke(menu, new object[] { item, null, count, 0, 0 })`（`:304`）。`held_item=null` 是关键（注释 `:293`：IL_0017 只有 null 才走"直接购买"）。

### B.2 是不是"假装下单"？—— 判据在游戏入口之后
`BuySkill.cs:245-249`（判据=观测差分，不看游戏返回值）：
```
int moneyAfter = Game1.player.Money;  int invAfter = CountInInventory(Game1.player, want);
int spent = moneyBefore - moneyAfter; int gained = invAfter - invBefore;
```
`BuySkill.cs:257-265`：`if (gained <= 0) return this.Fail("purchase_no_effect", …)`（"观测上看没有买到东西"）。`Skills.cs:436` 明写 Mod **绝不**自己 `Money -= price`。

### B.3 money 差分与失败记账
- Mod 侧：`BuySkill.cs:246-249` 算 `spent`/`gained`；`purchase_no_effect`（`:259`）/ `purchase_partial`（`:269`）如实失败。
- 脑侧：`longrun.py:7593-7598` `self._journal("buy", ok=st.ok, code=st.code, reason=st.reason, item, count, wanted, price, price_shelf, price_cfg, source, attempt, limit, before=st.before, after=st.after, receipt=st.receipt, available=len(st.available))`；另有 `cannot_afford`（`:7528`）、`buy_partial`（`:7602`）、`buy_no_space`/`buy_no_space_facts`（`:7608-7619`）。
- ⇒ 有 money 差分（Mod 侧）+ 失败记账（两侧都有）。

### B.4 保留点（不改变"真实购买"结论，但须记）
1. **冗余**：`_preconditions` 在 `_run_day` 主循环**每轮**已无条件调用（`longrun.py:9817`），且铁匠升级在同处（`:9824`）。故 `_execute` 的 `buy` 分支（`:9042`）在多数轮次里是**重复调用**（首次已买成功 ⇒ 返回 False）。
2. **常在无操作**：`_preconditions_apply` 在"手上有**当季可种**种子"时**早退返回 False**（`longrun.py:7424-7425`）⇒ 该分支仅在"无当季种子"时才可能真买。
3. 脑侧不另做独立 money 差分，只落 `st.before/after`（真正的差分在 Mod 侧，见 B.2）。

### B.5 结论
**真实购买**：链路经游戏入口 `ShopMenu.tryToPurchaseItem(item,null,count,0,0)`，成败由钱/背包差分裁决，失败有账。不是"假装下单"。（另：`upgrade_tool` 分支用的 `worker.ensure_location` 存在，定义在 `farmwork.py:2332`；`worker.upgrade_tool` 在 `bridge.py:1171` — 仅供旁证，非本卡判决项。）

---

## C. `tools/verify-zone-retention.py` —— 判定：**需修后用**

逐条核实（`tools/verify-zone-retention.py` 全 87 行已读）：

**① `tilesTruncated=True` 是否 fail-closed —— 是。**
`fields.py:356-357`：`if loc.get("tilesTruncated"): return None`；工具 `:69-71`：`if b is None or a is None: verdict = "【无法判定】tilesTruncated"; all_ok = False`。实测读数（命令见附录）：
```
zone        before  after   verdict
field_nw     NA      1       【无法判定】tilesTruncated
…              all -> 【无法判定】…   exit=1
```

**② zone bounds 是否只从观测推出（无硬编码坐标）—— 是。**
工具 `:50 zones = zones_from_observe(before, split=args.split)`；`fields.py:290-293` 由 `location.tiles[] ∪ location.tillable[]` 包络等分，**无任何坐标常量**。

**③ 会不会因 D1 **假 PASS** —— 会（决定性）。**
实测：构造"区内**只有**一格 `kind=clump,clumpKind=stump`"的 before 与 after（桩始终未清）：
```
$ PYTHONUTF8=1 python tools/verify-zone-retention.py \
    --before scratch/t15_onlyclump_before.json --after scratch/t15_onlyclump_after.json --all
zone        before  after   verdict
field_nw     0       0       PASS (retained clear)
field_ne     0       0       PASS (retained clear)
field_sw     0       0       PASS (retained clear)
field_se     0       0       PASS (retained clear)
ZONE_BLOCKER_KINDS = ['boulder','bush','greenRain','log','rockPile','stone','stump','tree','twig','weed']
exit=0
```
树桩**还在**，却判 `PASS (retained clear)` 且 `exit=0` ⇒ **假 PASS**，根因同 D1。
（对照：区内另有 weed 时 `field_nw 1 1 FAIL, exit=1` —— 说明脚本本身逻辑正确，只是口径漏 clump。）

**④ 退出码语义。**
`:83 return 0 if all_ok else 1` ⇒ **0 = 全部 zone PASS**；**1 = 任一 FAIL 或任一【无法判定】**（两者不区分）；**2 = argparse 用法错误**（如缺 `--before`）；其它未捕获异常 → Python 退出码 1。

**⑤ 附加缺口（不在卡面四项，但影响可作判据）。**
- `zones_from_observe` **只用 `before` 推导**（`:50`），`after` 的 zone 边界不重算 ⇒ 若两日农场范围/形状变了，`after` 仍按 `before` 的旧 bounds 统计；脚本**不校验**两次观测是同一 location/季节。
- 未断言 `after.player/location` 有效；`--zone` 指定的区若不在 `before` ⇒ `:64` 报【无法判定】并 `is_ok=False`（合理）。
- 只比较**恰好两天**；"连续 ≥2 天"需调用方自行链式跑 `(N,N+1),(N+1,N+2)…`。

**C 结论：需修后用。** 机制骨架可用（fail-closed、无硬编码坐标、逻辑对），但**必须**先修 D1（`ZONE_BLOCKER_KINDS` 并入 `"clump"`），否则它是"目标1 ② 连续清空"的**假 PASS 工具**；修后建议补 `after` 边界/同地点断言。

---

## D. 测试覆盖与变异（供 Lead 采信）

- `git grep -n -e zone_blockers_total -e ZONE_BLOCKER_KINDS -e verify-zone-retention -- tests/` ⇒ **零命中**（exit=1，无输出）。
- `tests/test_fields.py`（354 行）仅测 `BLOCKER_KINDS`：`:185-187 assertIn("weed", …)/assertNotIn("grass")/assertNotIn("dirt")`；**无** `ZONE_BLOCKER_KINDS`、**无** `zone_blockers_total`、**无** clump 用例。
⇒ P0-1/P0-2/P0-3 **零单测、零变异**（与 Lead 条目 094 一致，本处为独立复算）。

## E. 已知限制 / 未决

- 本验收为**静态+最小观测**复现，**未**跑真机、**未**跑长跑；"真机动态复现"仍以最小观测为准（已满足 Lead 对 observer 的要求）。
- 提交归属：`git log --format='%an <%ae>'` 全为 `Stardew Automation <stardew@localhost>` ⇒ **谁写的【无法判定】**（与 Lead 条目 094 同）。
- §B 的 `upgrade_tool` 分支仅作旁证；其"真伪/配对"未在本卡判决范围内展开。

## 附录 · 原始命令
```
1) git log --oneline -15 ; git rev-parse HEAD        # 80de585
2) git show 0f72f3c | Out-String                      # P0-1 diff
3) git show bbb6a89 | Out-String                      # P0-5/6/7 diff
4) PYTHONUTF8=1 python scratch/observe_t15_d1_minobs.py
5) PYTHONUTF8=1 python tools/verify-zone-retention.py --before scratch/t15_onlyclump_before.json --after scratch/t15_onlyclump_after.json --all
6) git grep -n -e zone_blockers_total -e ZONE_BLOCKER_KINDS -- tests/
```
（`scratch/t15_before.json` / `t15_after_clump_remains.json` / `t15_after_clean.json` / `t15_before_trunc.json` / `t15_onlyclump_before.json` / `t15_onlyclump_after.json` 为本次构造的观测样本。）
