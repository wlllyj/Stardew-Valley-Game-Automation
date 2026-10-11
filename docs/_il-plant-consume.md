# IL 取证 · 「播种不扣种子」的机制与修法（Mod 0.7.19）

> 写在 2026-10-11 晚。起因：**用户**在 P3 ⑤ 的 5x5 试点里发现异常 ——
> `tools\run-plot.py --size 5 --seed 472` 报 20 格 `planted=True`、`observe` 里 20 个 `crop` 都在，
> 但背包里那包防风草种子（item `472`）**从头到尾是 10 个**。
> 这条笔记把「为什么」和「怎么修的」钉死，供以后复用（同类问题：**绕过游戏入口就会漏掉游戏在那条链里做的账**）。

## 1. 真机现象（先记事实）

```
[1/25] ✅ (64, 18) ... planted=True watered=True 体力=270
...
[20/25] ✅ (68, 21) ... planted=True watered=True 体力=192
完成 20 / 处理 25 格；跳过 5；没做成 0；终态：VERIFIED
```
随后 `observe?detail=full`：
```
farm: hoeDirt=20 crops=20 unwatered=20       ← 作物真的种下了（不是假成功）
player.inventory: slot 5 = 472 "Parsnip Seeds" x 10   ← 种了 20 格，还是 10 个
```
⇒ 结论：**作物是真的，扣种子是假的**。这比"播种失败"更危险：账目失真会污染后面所有
"种子够不够 / 产量多少 / 3 个游戏日要备多少种子"的判断。

## 2. IL 取证（工具：`tools\il-probe`）

命令（游戏目录 `D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley`）：
```
dotnet run -c Release -- "<游戏目录>" "StardewValley.Object|placementAction" "FIND|consumeObject" "FIND|reduceActiveItemByOne"
dotnet run -c Release -- "<游戏目录>" "StardewValley.Game1|pressActionButton"
```
> ⚠️ 落盘时 PowerShell 的 `>` 写的是 **UTF-16LE**，`read`/`grep` 会当二进制。
> 用 `tools\_tmp_conv.py <src> <dst>` 转成 UTF-8 再看（脚本已留在仓库）。

### 2.1 `Object.placementAction` 不扣物品

* `FIND|consumeObject` → **命中 0 个调用方法**（整个程序集里没有任何方法调它）。
* `FIND|reduceActiveItemByOne` → 命中 25 个调用方法，**没有一个是 `placementAction`**
  （清单里是 `Game1.pressActionButton`、`GameLocation.checkAction`、`Utility.tryToPlaceItem`、
  `Farmer.eatHeldObject`、`FarmAnimal.pet` … 这些）。
* 直接 dump `StardewValley.Object.placementAction(GameLocation, Int32, Int32, Farmer)`（IL 916 行起）
  —— 整段里没有任何对 `Stack` / 物品数量的写操作。

⇒ **`placementAction` 只负责"把东西放到世界上"，不负责"从背包里扣掉"。**

### 2.2 真正扣物品的是 `Game1.pressActionButton`

`StardewValley.Game1.pressActionButton(KeyboardState, MouseState, GamePadState)` 的关键片段：

| IL 偏移 | 代码 | 含义 |
|---|---|---|
| `IL_0620` | `callvirt Boolean performUseAction(GameLocation)` | 手持物"对地点使用"（吃东西/机具投料那条） |
| `IL_0625` | `brfalse.s -> IL_064E` | 不成立就跳到"放置"那条路 |
| `IL_062C` | `callvirt Void reduceActiveItemByOne()` | ✅ **`performUseAction` 成功就扣一个** |
| `IL_0658` | `callvirt Int32 get_Stack()` → `stloc.s 10` | 走放置路线前，**记下手里的堆叠**（局部变量 10） |
| `IL_0752`–`IL_0763` | `get_ActiveObject().get_Stack()` / `ldloc.s 10` / `blt.s -> IL_0776` | 放置后**只有当前 Stack 小于记下来的值**才认为"消耗成功" |

⇒ 游戏自己的口径是一句话：**放置链成功 = 世界变了 且 背包少了**。
我们把路径③写成"绕过鼠标直调 `placementAction`"（为了躲开 `wasMouseVisibleThisFrame` 把使用键带到鼠标格的问题，
见 `PlantSkill.cs` 里路径②的注释），于是**正好丢掉了后半句**。

## 3. 修法（Mod 0.7.19）

`mod\AgentFarm.Bridge\PlantSkill.cs`：

1. `TryPlacementAction(out string detail, out bool consumed)`：放置前记 `obj.Stack`，放置后比大小，
   把"链内有没有扣"作为诊断与判据一起返回；
2. `EnforceItemConsumed(bool consumed)`：**只在"该格已经出现 crop"且"链内没扣"**时，
   调游戏自己的 `Game1.player.reduceActiveItemByOne()` 补扣一次
   —— 这不是"乱写游戏状态"，而是把绕过鼠标时丢掉的那一步补回来，参数与前置条件都与
   `pressActionButton` 一致（架构 §8 豁免清单已登记）；
3. `Begin()`：种子堆叠 ≤ 0 时**显式** `precondition_failed`（以前被"永不减少"掩盖，永不可达）；
4. 回执新增：`种子堆叠 n→m`、补扣说明、`UsingTool=`、走过的路径 —— 让回执自己就能说明这次扣没扣。

### 真机验收（判据 = 观测差分，不信回执）

`tools\verify-plant-consume.py`（新脚本，可重复跑）：
```
Mod 0.7.19  ...
播种前：item 472 堆叠 = 10
目标格 (64, 18)  站好位：玩家 (64, 17)
锄地回执：status=ok 511ms
锄地差分 ✅ kind=dirt plantable=True
播种回执：status=ok 4030ms
  已把「Parsnip Seeds」种进 (64,18)（按了 3 次使用键，UsingTool=False）；
  种子堆叠 10→9（补扣 472：Stack 10→9（游戏入口 reduceActiveItemByOne））；
  路径：②leftClick(64,18) 返回 False；③placementAction 返回 True（用物品 472，ActiveObject=472，像素 4096,1152）（Stack 10→10，链内没扣）

播种后：item 472 堆叠 = 9（前 10，差 -1）
        (64, 18) tiles[] = {"tile":[64,18],"kind":"dirt","tool":"can","feature":"HoeDirt",
                            "standable":true,"actionable":true,"crop":"24","ripe":false,
                            "dead":false,"watered":false,"plantable":false}
✅ 作物出现：crop=24
✅ 种子扣减：10 → 9（期望 9）
结论：VERIFIED
```
> 回执里那句 `③placementAction ...（Stack 10→10，链内没扣）` 就是 IL 结论的**真机复现**：
> 同一个事实，两条独立证据（IL + 运行时）对上了。

## 4. 可复用的教训

1. **绕过游戏入口 = 要自己补上那条链里的所有账**。我们绕开鼠标是为了拿回"作用在哪一格"的控制权，
   代价就是游戏在 `pressActionButton` 里做的记账也得自己补 —— 而且必须**用游戏自己的结算方法**补。
2. **"成功"的判据要包含副作用**。本次把"作物出现"当成成功就漏了"背包减少"；
   判据升级为两条同时成立（`crop` 出现 **且** 堆叠恰好 -1）。
3. **探针优先级再次验证**：`FIND|` 全程序集搜"谁调用了 X"能在几分钟内回答
   "这一步到底谁负责"，比猜十次都快。
4. **一次落盘转码的坑**：PowerShell `>` 重定向产出 UTF-16LE，别拿它当文本源（见 §2 的提示）。
