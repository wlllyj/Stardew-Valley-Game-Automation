# 卡片草稿 A2 — 种子门闸与腾格回路重排（更深层的"整晚死锁"）

> 状态：草案（未落库）。仅分析 + 提案，不改代码、不改开发日志。
> 作者：analyst-b3（log-analyst）。关联任务：task-240b（catch-22 修复）。

## 0. 背景：task-240b 修掉了什么

task-240b（commit `e23d989` `fix(longrun): task-240b 腾格成功后同轮试买种子（catch-22）`）
修的是"腾格→买种"的 **catch-22**：腾出格子后要到下一个决策轮才去试买，中间的快照刷新
把"腾格成功"吞掉，导致当天始终买不进种子。修复点见 `brain/agentfarm/longrun.py`：

- `_preconditions_apply` 在 `free_slots < 1` 分支里，腾出一叠后**立即重取快照并就地重试 buy**
  （`longrun.py:7491-7504`：`_snap_or(obs)` → 重算 `free_slots` → 落到 `7555+` 的买种逻辑），
  不再等下一轮。这正是"腾格成功后同轮试买种子"。

## 1. 残留的更深层死锁：整晚无可卖叠

catch-22 修的是"腾得出但没在同轮买"；但还有一种**腾不出**的情形，task-240b 没碰、也解决不了：

**整晚无可卖叠（full bag of protected materials, no sellable surplus）**

触发链路（`longrun.py:7486-7525`）：

1. `plantable == 0`（当季没有可种种子）⇒ 必须买种（`7473` 早退不成立）。
2. `free_slots < 1`（背包满）⇒ 进腾格分支。
3. 腾格只有两条路：
   - `_sell_surplus_for_slot`（`7489`）—— 凑钱买种，卖超 K 的盈余材料；
   - `_sell_surplus_for_space` → `_ship_one_stack_for_space`（`7496` / `6515`）。
4. **关键死锁**：`_ship_one_stack_for_space`（`6515-6556`）的候选白名单
   - 跳过 `_PROTECTED = {"330","378","380","382","384","386","388","390"}`（建材/矿石/锭/煤/土/木/石，`6519`）；
   - 跳过种子名（`6531`）、`SLOT_RELIEF_NEVER_SELL_IDS`（`6533`）；
   - 若背包**全是受保护材料 + 受保护种子**，则 `cands` 为空 ⇒ `return False`（`6542-6543`）。
5. 两条腾格路都返回 False ⇒ `7505` 仍 `free_slots < 1` ⇒ 记 `slot_relief{pressure,reached=False}`
   并 `return changed`（`7525`）—— **今天不买**。

此时 `plantable==0`（种不了）、腾不出格（买不进）、全是受保护物（卖不掉）三路全断。
bot 当天对"买种"彻底放弃，只留一句 `"买种子前背包满且腾不出格子 ⇒ 今天不买"`，
**静默放弃而非显式判定为不可恢复**——这正是 A9-0749 账本里"farm 还有大量耕地空着却动不了"
的同源疑凶之一（与 Z3 的 unknown 格互相叠加）。

## 2. 提案：种子门闸 vs `slot_relief` 重排

核心原则：**种子买种尝试应当"一旦有可卖盈余可腾格就立刻触发"，而不是被"背包必须先有空格"
这道前置闸门挡住。**

具体重排建议：

### 2.1 把"买种"挂到 `slot_relief` 的成功腾格上（事件驱动，而非起点闸门）
- 现状：`_preconditions_apply` 是**起点闸门**——只在函数顶部判断 `free_slots<1`，
  腾一格后就地重试一次（`7491-7504`）。但 `_slot_relief`（`6558`）在农场主循环里会反复腾格
  （每天最多 `SLOT_RELIEF_MAX=6` 轮、`SLOT_RELIEF_MAX_STACKS_TOTAL=10` 叠，`6586-6587`），
  这些**后续腾出的空格并没有回灌到买种**。
- 提案：当 `_slot_relief` 在某轮**真的腾出了一格来自可卖盈余的空格**（`_ship_one_stack_for_space`
  成功，`6551-6555`），直接 `continue` 后重新调用 `_preconditions_apply`（或至少触发一次买种尝试），
  而不是等下一个"整点"门闸。即：买种由"腾出可卖盈余"驱动，而非由"背包是否已满"门槛驱动。

### 2.2 区分"腾不出（有盈余没卖）"与"腾不出（全是受保护物）"
- 现状：`_ship_one_stack_for_space` 在无候选时只 `return False`，调用方无法区分
  "本可卖但今天卖满上限" vs "根本没有可卖叠"。
- 提案：让 `_ship_one_stack_for_space` / `_slot_relief` 在 `cands` 为空（全是受保护材料+受保护种子）
  时返回明确信号（如 `no_sellable_surplus=True`）。`_preconditions_apply` 据此：
  - 记一个**显式、跨天可见**的 `inventory_blocked`（reason=`all_protected`，而非笼统的 `buy_full`），
    让账本一眼看出"今天不是没试，是根本无解"，而不是静默 `今天不买`；
  - 触发诊断（见 A4 的 `refused_tiles` 思路可复用）：把"满包受保护物"作为当日收尾理由写进简报，
    提醒需要次日结算/人工清包，而不是每天重撞同一堵墙。

### 2.3 验收判据（草案）
- 单测：构造 `inventory` 全为 `_PROTECTED` + 受保护种子、`plantable==0`、`free_slots==0` 的 obs，
  断言 `_preconditions_apply` 返回 `changed=False` 且 `rep` 含 `all_protected` / `inventory_blocked`
  显式标记（而非仅 `notes` 一句话），且当天 `buy` 事件数为 0（没有白撞 `no_inventory_space`）。
- 单测：构造 `_slot_relief` 后续轮次腾出一格可卖盈余的 obs，断言随后 `_preconditions_apply`
  被触发一次买种尝试（`buy` 事件 +1 或 `seed_dead_today` 被诚实置位）。
- 行为账本对照：A9-0749 春季跑中 `seed_gate{seeds:0,money:14}` 反复出现、`buy` 0 条的天，
  修复后应在账本出现 `inventory_blocked{reason=all_protected}` 而非消失的因果。

## 3. 引用锚点
- `brain/agentfarm/longrun.py:7451` — `_preconditions_apply`（种子门闸入口）
- `brain/agentfarm/longrun.py:7486-7525` — `free_slots<1` 腾格分支 + 放弃买种
- `brain/agentfarm/longrun.py:6558` — `_slot_relief`（腾格回路）
- `brain/agentfarm/longrun.py:6515-6556` — `_ship_one_stack_for_space`（候选白名单 / `cands` 为空）
- `brain/agentfarm/longrun.py:6519` — `_PROTECTED` 受保护材料集合
