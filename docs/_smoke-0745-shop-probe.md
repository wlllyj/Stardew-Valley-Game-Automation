# SeedShop 货架只读探针（0.7.45 真机，task-18 附录）

> 目的：回答 Lead m00822 的问题——**Pierre SeedShop 货架里到底有没有背包升级条目**
> （`Backpack` / `Deluxe Backpack`），以决定 0.7.46 卡 A 走「买背包」还是「Plan B（箱子/木箱）」。
> 只读：不开世界、不买东西、不改存档。全程由 machine-runner 看护，做完立刻优雅退游戏。

## §0 一句话结论

**无此条目。** 经 Mod 现有 `buy` 技能的开店路径，SeedShop 的货架真值 `itemPriceAndStock`
一共 **20 条**（100g–30,000g 全价区间），其中 **没有 `Backpack` / `Deluxe Backpack`**
（也没有任何名字/ID 含 "backpack" 的条目）⇒ 脑的 `buy` 技能**当前买不到背包升级**；
0.7.46 卡 A 要么给 Mod 新增专用技能（背包升级不是货架条目；机制未在本探针核实），
要么按 Plan B 走箱子/木箱。

## §1 背景（为什么需要这条探针）

- 0.7.45 冒烟账本 `logs/longrun-smoke-0745.jsonl` 的 `buy` 事件回执写 `available=20`，
  但同一回执里的**文字清单只列了 12 条**再加「…」——因为 Mod 的 `Listing()` 最多列 12 条
  （`mod/AgentFarm.Bridge/BuySkill.cs:456-469`，`:462-463` `if (names.Count >= 12) { names.Add("…"); break; }`）。
  剩下 8 条未知 ⇒ 无法判定背包条目在不在。
- 结构化清单 `availableItems`（task-67）本来就有完整数据，但账本里只落了条数；
  故直接对桥发一次 `buy` 探针，把 `availableItems` 全量落盘。

## §2 方法

1. `python tools\deploy-mod.py --no-quit` 起游戏（桥自报 `modVersion=0.7.45`、`port=17890`、
   `gameVersion=1.6.15`、`smapiVersion=4.5.2`、`pid=18888`，`startedAt=2026-10-18T12:21:38+00:00`）；
2. 只读脚本 `scratch\_t18_shop_shelf.py`（本提交）用 `agentfarm.bridge.BridgeClient`
   发 `POST /v1/exec`，请求体：
   ```json
   {"skill":"buy","timeout_ms":12000,
    "args":{"shop":"SeedShop","item":"__probe_none__","count":1}}
   ```
   `item` 用**不存在的名字** ⇒ 只会 `item_not_sold`，**不可能真买成**；
3. 把 HTTP 原始响应体、解析后回执、货架三元组（id/name/price）落 `scratch\_t18_shop_shelf.json`
   （`items_count=20`；`backpack_hits=[]`）；
4. 探针后 `dismiss_modal` 关掉可能残留的 `ShopMenu`，再 `stop-game.py --wait 45` 优雅退出。

## §3 读数

### 3.1 桥与请求

| 项 | 值 |
|---|---|
| 桥 | `modVersion=0.7.45` `port=17890` `pid=18888` `gameVersion=1.6.15` `smapiVersion=4.5.2` `startedAt=2026-10-18T12:21:38+00:00` |
| HTTP | `200`，客户端墙钟 `114.9ms`，回执自报 `elapsedMs=73` |
| 回执 | `ok=false`、`status=item_not_sold`、`schema=agentfarm-exec/2`、`worldSeqBefore=4`、`worldSeqAfter=4`、`uiOpened=false`、`worldResumed=true` |
| 玩家 | `FarmHouse`（躺在床里 `isInBed=true`、tile `[9,9]`）、`inventoryCount=12`、钱 **3288**（探针前后一致，未成交） |
| 场景 | winter 28 06:0x（= 0.7.45 冒烟推进后的档；探针未落盘 ⇒ 存档四件未变，见 §5） |

回执 `reason` 原文（文字清单 12 条 + 截断符）：

> 商店「SeedShop」里没有「__probe_none__」。在售清单：Grass Starter(100g)、Grass Starter (Recipe)(1000g)、Sugar(100g)、Wheat Flour(100g)、Rice(200g)、Oil(200g)、Vinegar(200g)、Basic Fertilizer(100g)、Basic Retaining Soil(100g)、Speed-Gro(100g)、Wallpaper(200g)、Flooring(200g)、…

注意这段文字清单**恰好 12 条 + 「…」**，但结构化 `availableItems=20` 条 ⇒ 截断只发生在文字清单，
结构化清单是完整的。

### 3.2 `availableItems` 全表（20 条，原顺序）

| # | id | name | price |
|---|---|---|---|
| 01 | `(O)297` | Grass Starter | 100 |
| 02 | `(O)370` | Basic Retaining Soil | 100 |
| 03 | `(O)368` | Basic Fertilizer | 100 |
| 04 | `(O)465` | Speed-Gro | 100 |
| 05 | `(O)245` | Sugar | 100 |
| 06 | `(O)246` | Wheat Flour | 100 |
| 07 | `(O)423` | Rice | 200 |
| 08 | `(O)247` | Oil | 200 |
| 09 | `(O)419` | Vinegar | 200 |
| 10 | `(WP)67` | Wallpaper | 200 |
| 11 | `(FL)19` | Flooring | 200 |
| 12 | `(O)297` | Grass Starter (Recipe) | 1000 |
| 13 | `(O)629` | Apricot Sapling | 2000 |
| 14 | `(O)628` | Cherry Sapling | 3400 |
| 15 | `(O)633` | Apple Sapling | 4000 |
| 16 | `(O)630` | Orange Sapling | 4000 |
| 17 | `(O)631` | Peach Sapling | 6000 |
| 18 | `(O)632` | Pomegranate Sapling | 6000 |
| 19 | `(BC)Dehydrator` | Dehydrator (Recipe) | 10000 |
| 20 | `(F)1308` | Catalogue | 30000 |

（表按 Mod 的 `Shelf()` 口径：`itemPriceAndStock` 按价格升序，`rows.Count=20 < 上限 30`
(`BuySkill.cs:432-434`)，**没有截断**。）

### 3.3 为什么可以当「完整货架真值」用

- `Shelf()` 直接枚举游戏 `ShopMenu.itemPriceAndStock`（`BuySkill.cs:425`），**不是** Mod 自建的白名单/过滤；
  即「游戏实际允许在这家店买的全部条目」；
- 20 条 < 30 条上限，且价格从 100g 覆盖到 30,000g，没有价格段的截断迹象；
- 玩家当前背包容量 12（未买过升级）——如果游戏把「下一档背包升级」作为货架条目卖，
  这一份清单里应当出现；**实测没有**。

## §4 结论与判法

- **事实（实测，可复跑）**：`SeedShop` 经 `Utility.TryOpenShopMenu("SeedShop", null, false)`
  打开后，货架 20 条里没有 `Backpack` / `Deluxe Backpack`，也没有任何 id/name 含 "backpack" 的条目
  （`backpack_hits=[]`）⇒ 脑现有 `buy` 技能买不到背包升级。
- **机制（未核实 ⇒ 标【无法判定】）**：背包升级在 SDV 1.6 里到底是不是货架条目（还是商店 UI 的背包按钮/
  专用购买流程）本探针**没有**验证（未点 UI、未看截图）；本探针只证明「经 Mod 这条开店路径拿到的货架里没有」。
  若 0.7.46 卡 A 想做「买背包」，需要 dev-coder 先用带 UI 点击能力的探针把机制坐实，不能拿本文当机制证据。
- **对卡 A 的直接含义**：按「买背包」走需要 **Mod 新增能力**（现在没有）；按 Plan B 走箱子/木箱不需要动经济动作。

## §5 收尾四项（本探针后复核）

| 项 | 读数 |
|---|---|
| 优雅退出 | `python tools\stop-game.py --wait 45` rc=0；日志「✅ 游戏已退出（原 pids=[18888]）」 |
| 进程 | `Stardew Valley`/`StardewModdingAPI` 进程数 **0** |
| `bridge.json` | `%APPDATA%\StardewValley\AgentFarm\bridge.json` **不存在** |
| 17890 | 无 `LISTENING`（`netstat -ano` 无匹配） |

探针**没有写存档**：跑后存档四件与 0.7.45 冒烟收尾时逐字节一致（`Wahaha_450799035` 2026-10-18T19:15:01）：

| 文件 | size | mtime | SHA256 |
|---|---|---|---|
| `Wahaha_450799035` | 2948770 | 19:15:01 | `6DE8419B098EA16972C7DB761F4080127599523A2C1AD8EC5A6176F86861B594` |
| `SaveGameInfo` | 32264 | 19:15:01 | `B5B51971BFF129EDE468D2671731A50B0D0A7964755AE7AB5643AEF07A7310A1` |
| `Wahaha_450799035_old` | 3137234 | 19:04:33 | `1695C1ED3286601FD951837AD0D4363EA45542024E01CD0B4F45B26FD453509D` |
| `SaveGameInfo_old` | 32259 | 19:04:33 | `BCC85C1B47EE63CE043EDE9668EA44E76D67867DD1C5E1CBCB4392D3AAE57DAA` |

A9-start 备份未动、未 restore（仍为 `logs/ab-backup/A9-start/`，MANIFEST `5479354B…988A3D`）。

## §6 产物与复现

| 产物 | size | SHA256 |
|---|---|---|
| `scratch\_t18_shop_shelf.json`（完整回执+货架，含 HTTP 原文，gitignore 未入库） | 26619 | `398C1AC761A8D00009DD3AE1AAF5CB6A55736D3A05C38F1FCD844C52893C56BC` |
| `scratch\_t18_shop_shelf.py`（本提交） | 6240 | `4A63D2BC20123E6F050F1225675C11C8155831C18A22DAD5777B86C3A8311BB7` |

复现：

```powershell
$env:PYTHONUTF8='1'
$py = 'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
& $py tools\deploy-mod.py --no-quit          # 起游戏读档（桥 0.7.45 就绪后返回）
$env:PYTHONPATH = (Get-Location).Path + '\brain'
& $py scratch\_t18_shop_shelf.py             # 只读探针 + 落 JSON + dismiss_modal
& $py tools\stop-game.py --wait 45           # 立刻优雅退
```

## §7 已知限制

1. 只验证了 Mod 现有 `buy` 技能这一条开店路径（`TryOpenShopMenu("SeedShop", null, false)`）；
   物理走进 Pierre 店、点 UI 背包按钮、其他 shop id 均未验证。
2. `uiOpened=false` 是回执字段（探针期间商店菜单确实开过又关过：探针后 `dismiss_modal`
   还额外关掉了一个残留 `ShopMenu`），字段语义以 Mod 代码为准，本探针未深究。
3. 没截图、没看画面；「没有条目」= 货架数据没有，而不是「游戏里绝对买不到背包」——
   机制仍待 UI 侧探针坐实（【无法判定】）。
4. 钱读数 3288 比 0.7.45 冒烟收尾时终态 3264 多 24g：这是读档后游戏结算的隔夜出货入账
   （winter 28 06:0x，晚上卖出的 12 根 wood×2g=24g）；探针未成交、钱数前后一致，且未落盘。
