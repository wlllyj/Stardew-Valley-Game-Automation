# _review-task38-ab —— 两项只读审计（lead 卡 m00494：A=buy 分支真实性 / B=verify-zone-retention 语义）

- 角色：deputy-lead（对抗验收方）。**本卡全程只读**：只 `grep`/`read`/`git show`/跑只读工具；未改任何生产代码、未 deploy、未碰游戏、未动任务板。
- 环境：Windows / `PYTHONUTF8=1`；`grep`/`sed` 用 `C:\Program Files\Git\usr\bin\*`；只读。
- 立场：不信作者自述、不信回执；结论一律给 `文件:行号` + 调用链。
- 被审对象：`bbb6a89`（P0 批第 5 个提交）的 `buy` 分支；`tools/verify-zone-retention.py`（P0-3）。

## ★ 单独发现（lead 漏、本卡捞回）：D1 不止在离线校验器，**运行时选区同漏**

> lead 原始卡面只把 D1 定位在 `tools/verify-zone-retention.py`（离线校验器）。本卡核到：**同一个 `ZONE_BLOCKER_KINDS` 也被运行时 `plot_in_zone` 用来给格分类**，所以缺口同时落在**运行时选区/账实口径**上——不只是"事后校验器骗人"，而是"选哪块地干活"当场就算错。详见 §B(d)。



## 0. 利益冲突声明（lead §2 强制）

`bbb6a89`（以及同批 `0f72f3c/3a22b97/5434acd/e34e5cc`）的 author=committer 在本仓一律是 `Stardew Automation <stardew@localhost>` —— **全仓所有 agent 共用同一身份**，无法据提交者判定作者；我此前已实测并向 lead 报告"证据指向 deputy-lead"。**因此本批可能存在本人当年的作品，本人不得作为本批（含 `bbb6a89` 的 buy 分支）的唯一验收人。**
本文档只做**事实核验**（读代码 → 给 `文件:行号` 与调用链 → 三种结论之一），不代替 observer 的独立验收。若本文结论与 observer 冲突，以双方**同向**为准。

---

## A. `bbb6a89` 的 `buy` 分支真实性

弃权点先说清楚：`bbb6a89` 的 `git show` 只含 `brain/agentfarm/longrun.py` + `brain/agentfarm/planner.py`（无测试），改动即"给 planner 的 `buy` 意图加一条 `_execute` 分派"。

### A(a) `_preconditions` 里到底哪条路径会买种子？

分派入口：`brain/agentfarm/longrun.py:9042-9054`
```
9042: if task == "buy":
9043:     changed = self._preconditions(obs, rep)
9044:     if changed: obs = self._snap()
9049:     self._record_intent(..., note="buy 由 _preconditions 流程执行（游戏入口 ShopMenu.tryToPurchaseItem）")
9053:     acted = changed or acted
```
即 `buy` 意图**整条复用** `_preconditions`。真正的买种路径在
`_preconditions`（`longrun.py:7379`）→ `_preconditions_apply`（`longrun.py:7402`）里，共三处发 `_buy_seed`：

| 路径 | 行号 | source | 说明 |
|---|---|---|---|
| ① 手上有货架清单直接挑 | `longrun.py:7512` | `"shelf"` | `pick_seed_offer` 选当季最便宜 |
| ② 无清单 → 用配置 `buy_item` 探一次 | `longrun.py:7538` | `"probe"` | 旧 Mod 无清单字段时的唯一办法 |
| ③ 探测带回清单 → 换 id 再挑一次 | `longrun.py:7548` | `"shelf"` | 仍不成 ⇒ `_seed_dead`（`7551`） |

买之前的门闸（不买的分支）：`7424-7425`（当季可种种子 >0 直接不买）、`7437-7476`（背包满 → 先腾格；腾不出 ⇒ 记 `slot_relief trigger="none"/demand_basis="buy_full"`(7461) 后**不买**）、`7482-7484`（`allow_buy=false`）、`7485-7491`（当天已撞 `no_inventory_space`）、`7492-7495`（当天请求数达上限 `MAX_BUY_TRIES_PER_DAY`）、`7496+`（`seed_dead_today`）。

**答**：会买种子的路径 = `7512` / `7538` / `7548` 三处 `_buy_seed`；三者都经 `_buy_seed`（`longrun.py:7554`）→ `self.worker.buy(...)`（`7587`）。

### A(b) 是否走游戏入口 `ShopMenu.tryToPurchaseItem`？（调用链）

```
planner 产出 buy 意图
  └─ longrun.py:9042  _execute 的 task=="buy" 分支
      └─ longrun.py:7402  _preconditions_apply
          └─ longrun.py:7554  _buy_seed
              └─ longrun.py:7587  self.worker.buy(item, n, shop=self.shop)
                  └─ farmwork.py:3839  FarmWorker.buy()
                      └─ bridge.py:1117  Bridge.buy() → exec_skill("buy", {item,count,shop})
                          └─ mod/AgentFarm.Bridge/BuySkill.cs:169  DoPurchase(ShopMenu menu)
                              ├─ BuySkill.cs:295  TryPurchase(...)
                              │    └─ BuySkill.cs:304  反射 ShopMenu.tryToPurchaseItem(item, null, count, 0, 0)
                              │        ⇒ 游戏内部 IL_013D chargePlayer(游戏自己扣钱)
                              └─ BuySkill.cs:327  SettleHeldItem(...)
                                   └─ BuySkill.cs:335  Game1.player.addItemToInventoryBool(held, false)
```
**答**：是。走游戏入口 `ShopMenu.tryToPurchaseItem`（private，仅反射；`BuySkill.cs:301-306`），钱由游戏自己的 `chargePlayer` 扣（`BuySkill.cs:31` IL 注记），**没有任何一处脑/Mod 自己写 `Money -=`**（`BuySkill.cs:17` 明文纪律；全仓未发现 `Money -=`/`Money +=` 于 buy 链）。

### A(c) 有没有 money 前后差分校验 + 失败可回滚/可记账？

**有差分校验（两层），无回滚，有记账：**

1. **脑侧独立观测差分（真差分，YES）** —— `farmwork.py:3839 buy()`：
   - 调用前：`obs = self.snap()` → `money_before = self.money(obs)` / `have_before = _count_item(...)` → `r.before = {"money":…, "item":…}`。
   - 调用后：再 `obs = self.snap()` → `money_after` / `have_after` → `r.after = {...}`。
   - 判据（`farmwork.py` 内）：**`if have_after > have_before and money_after < money_before: r.ok = True`** —— 这就是"钱少了 **且** 物品多了"的**独立 `observe` 差分**，不看 Mod 回执的 `status`/游戏返回值；不满足落到 `r.code="failed"`（或 `"no_space"`）。
2. **Mod 侧同调用内差分（YES，但非独立 observe）** —— `BuySkill.cs:246-249` `moneyBefore/moneyAfter`、`invBefore/invAfter`、`spent`、`gained`；`BuySkill.cs:257` **`if gained <= 0 ⇒ Fail("purchase_no_effect")`**（fail-closed：抓"宣称成功但背包没变"）。
3. **回滚：没有真正的回滚。** 但有**有界防损**：
   - 购买**前**先自检空格（`BuySkill.cs:219-226`），不够 ⇒ 提前 `no_inventory_space`，**在扣钱之前**拦下；
   - 收货 `SettleHeldItem` 失败 ⇒ 不把 `menu.heldItem` 清空（物品留在商店手上，不丢），并 `Fail("purchase_partial")`（`BuySkill.cs:267-273`，文案明写"钱已按实际支出扣减，需复核"）；
   - 游戏入口 `tryToPurchaseItem` 自身原子（钱够才整体扣）。
4. **记账：有。** `longrun.py:7593-7598` 记 `buy` journal（`ok/code/reason/item/count/price/price_shelf/price_cfg/source/attempt/before/after/receipt/available`）；`7602` 记 `buy_partial`。

**结论（三选一）：`真实购买`。**
理由：走游戏入口 `ShopMenu.tryToPurchaseItem`（钱由游戏 `chargePlayer` 扣、货由游戏 `addItemToInventoryBool` 收），脑侧另有**独立 `observe` 差分**（`have_after>have_before 且 money_after<money_before`）兜底"回执撒谎"。
**未满足项（如实记）**：没有事务性回滚；Mod 侧那层差分是**同调用内**的、不是独立 observe（但脑侧那层是独立的）。

---

## B. `tools/verify-zone-retention.py`（P0-3）语义审计

文件全文 87 行；关键行：
```
50:  zones = zones_from_observe(before, split=args.split)
67:  b = zone_blockers_total(z, before)
68:  a = zone_blockers_total(z, after)
69:  if b is None or a is None:  verdict = "【无法判定】tilesTruncated"; all_ok = False
72:  elif b == 0 and a == 0:     verdict = "PASS (retained clear)"
82:  print("ZONE_BLOCKER_KINDS =", sorted(ZONE_BLOCKER_KINDS))
83:  return 0 if all_ok else 1
```

### B(a) `tilesTruncated=True` 时是否 fail-closed？

**是（fail-closed，不当 0、不 PASS）。**
- `brain/agentfarm/fields.py:349-357`：`zone_blockers_total(...)` 内 `if loc.get("tilesTruncated"): return None`。
- 工具 `verify-zone-retention.py:69-71`：`b is None or a is None ⇒ verdict="【无法判定】tilesTruncated"` 且 `all_ok=False` ⇒ 最终 `exit 1`。
- 对照 `fields.py:353` 注释："tilesTruncated 时返回 None：调用方必须标【无法判定】，绝不当 0"。

### B(b) zone bounds 来源是否只用 `fields.zones_from_observe`（不硬编码）？

**是。**
- `verify-zone-retention.py:50` 只用 `zones_from_observe(before, split=args.split)` 推区；同一份 `z` 的 bounds 同时用于 before/after（`:67`/`:68`）。
- `fields.py:270-293`：bounds = `location.tiles[] ∪ location.tillable[]` 的坐标包络再等分（`fields.py:273-274` 注释明写"**不硬编码任何坐标**"）；非户外农场返回 `[]`（`:282-283, 287-288`）。
- 全文件无字面坐标常量。

### B(c) `zone_blockers_total` 是否依赖 `kind ∈ ZONE_BLOCKER_KINDS`？D1（缺 `"clump"` ⇒ 大障碍永不计数 ⇒ 假清空）在此工具是否成立？

**依赖 → 成立。D1 在本工具中**确实**成立。** 证据链（三方对上）：

1. **统计口径依赖 kind 集合**：`fields.py:363` `if tv.get("kind") in ZONE_BLOCKER_KINDS: n += 1`（`zone_blockers_total`）；同一口径也在 `fields.py:321`（`zones_from_observe` 的 `blockers` 计数）。
2. **集合常量缺 `"clump"`**：`fields.py:56` `BLOCKER_KINDS = frozenset({"weed","stone","twig","tree","bush"})`；`fields.py:60` `ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {"stump","log","boulder","rockPile","greenRain"})`
   —— 并进的是 **clumpKind 的值**（stump/log/boulder/rockPile/greenRain），**不含 tile 的 kind 字面 `"clump"`**。
3. **Mod 对 ResourceClump 写的 tile `kind` 恰是字面 `"clump"`**：`mod/AgentFarm.Bridge/WorldSnapshot.cs:807`
   `else if (tf is …ResourceClump clump) { t.Kind = "clump"; FillClumpMeta(t, clump); }`
   （协议文档同据：`mod/AgentFarm.Bridge/Contracts.cs:589-593` 列出 kind 取值含 `clump`（资源堆）；`Contracts.cs:598` "只有 `kind="clump"` 时才填" clump* 元数据；`Contracts.cs:616` clumpKind ∈ stump/log/boulder/rockPile/greenRain/unknown。）

⇒ **任何 ResourceClump 格（树桩/大木头/巨石/石堆/绿雨碎屑）的 `kind=="clump"`，既不在 `BLOCKER_KINDS` 也不在并入的那五个子里 ⇒ 永不计数。** 于是
- `zones_from_observe` 的 `z.blockers`（`fields.py:321`）、`zone_blockers_total`（`fields.py:363`）都会把满是树桩的区读成 `0`；
- `verify-zone-retention.py:72-73` 于是对 `b==0 and a==0` 报 **`PASS (retained clear)`**（`exit 0`）—— 即 lead 说的**假清空**。

### B(d) 【单列】运行时选区同漏：`fields.py:506/:512`

**这是 lead 原卡面漏掉、本卡捞回的一条：D1 的 `ZONE_BLOCKER_KINDS` 缺口不止影响离线校验器 `verify-zone-retention.py`，还影响运行时选区。**

- 同一集合常量 `ZONE_BLOCKER_KINDS` 被**运行时** `brain/agentfarm/fields.py:506` 引用（函数 `plot_in_zone`，定义在 `fields.py:453`）：
  ```
  502: for c in cells:
  503:     tv = tiles.get(c)
  504:     if c in till:                         # tillable = 能锄出耕地的空格，优先按它归类
  505:         t_in.append(c)
  506:     elif tv is not None and tv.get("kind") in ZONE_BLOCKER_KINDS:
  507:         b_in.append(c)
  ...
  512: work = len(b_in) + len(t_in) + len(u_in)
  513: key = (-len(t_in), -work, ay, ax)      # 可锄最多 → 要干的活最多 → 最靠左上
  ```
- ⇒ 一块被 ResourceClump（`kind=="clump"`）占住的格：既不在 `till`（不可锄）⇒ 落到 `:506`；又因 `"clump" ∉ ZONE_BLOCKER_KINDS` ⇒ **不算 blocker** ⇒ 既非 tillable、非 blocker、非 crop、非 unwatered ⇒ 在 `:512` 的 `work` 打分里**完全消失**。选区偏好是"可锄最多 → 活最多 → 左上"，一块塞满 clump 的地会被当成**轻活/空地**而被优先选中。
- **清障执行侧无此漏洞**（别混为一谈）：`longrun._stage_tiles("clear_area")` 用的是 `CLUMP_KINDS`/`CLEARABLE_KINDS`（`longrun.py:197`、`longrun.py:4803`），`farmwork.CLUMP_KINDS`（`farmwork.py:163`）含 `"clump"`。因此**缺口精确定位在 `fields.py` 的 zone/plot 统计与选区口径**（`fields.py:321`、`:363`、`:506`），不在清障执行侧。
- 影响：运行时会误选"看起来空、实际满是树桩/巨石"的区当作业区（与离线假清空同根）。本案 `docs/_review-task38-ab.md` §B(c) 的 D1 结论据此把影响面从"仅离线"上修为"离线校验 + 运行时选区"。

**测试覆盖（决定"这算不算已覆盖"）**：**没有覆盖。**

- `git grep ZONE_BLOCKER_KINDS|zone_blockers_total|zones_from_observe -- tests/`：`zones_from_observe` 只在 `tests/test_fields.py:48/121/143/150/154` 出现；`ZONE_BLOCKER_KINDS`、`zone_blockers_total` 在 `tests/` **零引用**（`zone_blockers_total` 连一个单测都没有）。
- `tests/test_fields.py:166 test_counts_come_from_tillable_and_tiles` 的 kinds 只有 `weed/stone/tree/bush/twig/grass`（`:169-170`），断言 `sum(z.blockers)==5`（`:181`）、且 `:184-187` 只校验 weed/grass/dirt —— **没有一格 kind=="clump"** ⇒ 现有测试抓不到 D1。

---

## 已知限制 / 【无法判定】项

- 本卡**未**跑真机：A 的"真实购买"是**静态调用链 + 双层差分代码**判定，不是真机成交实测；若需"这版 buy 真能成交"的真机证据，属 machine-runner 的活。
- A 的"无回滚"是按**代码语义**判定（游戏入口原子 + 无补偿分支）；`purchase_partial` 的实际发生率未在账本里统计。
- B 的 D1 影响面（`plot_in_zone` 运行时误选）是**静态推理**，未在真机/账本里复现"选中满是 clump 的区"。

## 交给 0.7.49 批次的待跑项（先记，等冻结）

1. **D1 定向单测（dev-coder 新写）**：至少一条"kind=='clump' 的格必须计入 zone blockers"（`zones_from_observe` 与 `zone_blockers_total` 各一条）—— 用它当 D1 修复的"杀点"；本文档给出它现在**不存在**的证据（`tests/` 零引用 + `test_fields.py:166` 无 clump）。
2. **D1 变异**：把 `ZONE_BLOCKER_KINDS` 里的 `"clump"` 去掉（等价于修复前的现状）⇒ 定向单测必须红；再反向（修复后加回）必须绿。
3. **`verify-zone-retention` 端到端**：造一对 before/after 观测（区内含 kind=="clump" 格），确认修复后 `zone_blockers_total` >0 且工具报 FAIL/【无法判定】而非 PASS。
3b. **运行时选区（§B(d) 单列项）**：造一块 `kind=="clump"` 的格，确认修复后 `plot_in_zone`（`fields.py:453`）把它计入 `blockers`（`fields.py:506`/返回的 `blockers` 列表）且 `work` 打分（`fields.py:512`）把它算进"要干的活" —— 未修前它会在打分里消失、被判为轻活区。
4. **A 类回归**：`bbb6a89` 的 buy 分派若在 0.7.49 被重写，需重核"脑侧独立 observe 差分（have_after>have_before 且 money_after<money_before）"仍在（防止重写时退回"只看回执"）。
