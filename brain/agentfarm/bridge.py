"""桥接客户端：与游戏内 Mod 的本地 HTTP 服务通信。

设计约束（见 docs/03-桥接协议.md）：

1. **只用标准库**（urllib / json / pathlib），零第三方依赖。
   脑是整个无人值守系统里最不该"因为装不上包而跑不起来"的部分。
2. **失败必须显式**：所有异常路径都抛 `BridgeError`（带机器可读的 `status`），
   绝不返回"看起来像成功"的空结果。旧方案最大的教训就是失败被静默吞掉
   （见 docs/_legacy-audit.md §3.2）。

协议契约由 docs/03-桥接协议.md 唯一定义；本文件是它的 Python 侧实现。
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---- 契约常量（改这里必须同步 docs/03-桥接协议.md 并升版本号） ----
SCHEMA_BRIDGE = "agentfarm-bridge/1"
SCHEMA_WORLD = "agentfarm-world/6"   # v5：新增 location.doors[]（仅 detail=full）；
                                     #     v4：新增 location.furniture[]（仅 detail=full），
                                     #     修掉 move_to 的家具误判（改问游戏 isPassable）。
                                     # v3：player.isInBed、game.paused / game.shouldTimePass、
                                     #     dismiss_modal 改 answerDialogue + closeDialogue、
                                     #     worldResumed / status=world_stuck。见 docs/03-桥接协议.md
SCHEMA_WORLD_LEGACY = ("agentfarm-world/5", "agentfarm-world/4", "agentfarm-world/3")
# 升级窗口期间的兼容口径：Mod 的 dll 被游戏锁住、必须重启游戏才能换版本，
# 所以"脑已经改了、游戏里还是上一版 Mod"是**正常会发生的中间态**。
# 对上一版 schema：**接受 + 大声警告一次**（新字段不可用），绝不静默吞掉。
SCHEMA_EXEC = "agentfarm-exec/2"     # v2：新增 worldResumed
MOD_VERSION_EXPECTED = "0.7.21"   # v0.7.21：观测里补 player.wateringCan{present,waterLeft,max,
                                 # bottomless,upgradeLevel}（水在 WateringCan 上、不在 inventory）
                                 # 与 location.refillTiles[]（判据=游戏自己的
                                 # CanRefillWateringCanOnTile，扫全图、最多 24）——"连续 3 日浇水"
                                 # 必须能看见"还剩几格水"、"去哪儿补水"；
                                 # v0.7.20：新增 sleep（跨日唯一正路）与 buy（用游戏自己的
                                 # tryToPurchaseItem + addItemToInventoryBool 买种子）；
                                 # v0.7.19：修"播种不扣种子"（placementAction 不扣物品，
                                 # 补调 Farmer.reduceActiveItemByOne；见 manifest 与开发日志条目 024）；
                                 # v0.7.18：先判后动 + tillable[]；
                                 # v0.7.1：interact（调游戏自己的 checkAction）；v0.7.0：quit_game + world/5
                                 # 与“目标=当前所在格直接 ok”。v0.5.0：每帧强制
                                 # pauseWhenOutOfFocus=false（IL 定因：Game1._update
                                 # IL_0444-IL_0480 那道门），health 新增
                                 # game.pauseWhenOutOfFocus / game.oofFixCount 两个证据字段

# 已知基线：环境实测快照 docs/02-环境实测快照.md
BASELINE_GAME_VERSION = "1.6.15"
BASELINE_SMAPI_VERSION = "4.5.2"

# 覆盖 bridge.json 位置的环境变量（测试与多实例调试用）
ENV_BRIDGE_JSON = "AGENTFARM_BRIDGE_JSON"

# 只警告一次的去重集合（同一进程里同一条警告不刷屏）
_warned_once: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned_once:
        _warned_once.add(key)
        print(f"[agentfarm] 警告：{message}", file=sys.stderr)


class BridgeError(Exception):
    """桥接层的一切失败。`status` 与协议 §3 的状态码一一对应。"""

    def __init__(
        self,
        reason: str,
        status: str = "error",
        http_status: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.http_status = http_status
        self.payload = payload or {}

    def __str__(self) -> str:  # pragma: no cover - 仅用于打印
        extra = f" (HTTP {self.http_status})" if self.http_status else ""
        return f"[{self.status}]{extra} {self.reason}"


@dataclass(frozen=True)
class BridgeInfo:
    """`bridge.json` 的内容：Mod 告诉脑"我在哪个端口、口令是什么"。"""

    schema: str
    port: int
    token: str
    pid: int | None
    mod_version: str
    game_version: str
    smapi_version: str
    started_at: str
    path: Path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def default_bridge_json_path() -> Path:
    """`%APPDATA%\\StardewValley\\AgentFarm\\bridge.json`（协议 §2）。"""
    override = os.environ.get(ENV_BRIDGE_JSON)
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        # 非 Windows 或环境异常：退回用户目录，便于在别的机器上做纯 mock 测试
        return Path.home() / ".stardew" / "AgentFarm" / "bridge.json"
    return Path(appdata) / "StardewValley" / "AgentFarm" / "bridge.json"


def pid_alive(pid: int | None) -> bool | None:
    """检查进程是否还活着。返回 None = 无法判断（非 Windows 等）。

    ⚠️ Windows 上**绝不能**用 `os.kill(pid, 0)` 做存在性检查 —— 在 Windows 上
    它不是"发信号 0"，而是会走到 `TerminateProcess`，**真的把目标进程杀掉**。
    这里用 `OpenProcess(SYNCHRONIZE)` + `WaitForSingleObject(0)`：只查询、不触碰。

    【为什么需要它】实测（2026-10-11）游戏正常退出后 `bridge.json` 仍留在磁盘上。
    脑不能假定 Mod 一定守约清理，必须自己判断"这个文件是不是上一局的遗物"。
    """
    if pid is None or os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        return False                      # 打不开 = 进程不存在（或权限不足，保守当死）
    try:
        return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def load_bridge_info(path: Path | None = None) -> BridgeInfo:
    """读取并校验 `bridge.json`。

    文件不存在时给出**可操作**的提示（游戏没开？Mod 没装？），而不是一句 FileNotFoundError。
    """
    p = Path(path) if path is not None else default_bridge_json_path()
    if not p.exists():
        raise BridgeError(
            f"找不到 {p}。请确认：① 游戏已通过 SMAPI 启动；② 已加载存档；"
            f"③ Mod AgentFarm.Bridge 已安装并成功加载。",
            status="bridge_file_missing",
        )
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BridgeError(f"{p} 不是合法 JSON：{exc}", status="bridge_file_invalid") from exc

    schema = str(raw.get("schema", ""))
    if schema != SCHEMA_BRIDGE:
        raise BridgeError(
            f"bridge.json 的 schema 是 {schema!r}，期望 {SCHEMA_BRIDGE!r}。"
            f"两侧协议版本不一致，拒绝继续（协议 §8）。",
            status="schema_mismatch",
        )
    try:
        port = int(raw["port"])
        token = str(raw["token"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BridgeError(f"{p} 缺少 port/token 字段：{exc}", status="bridge_file_invalid") from exc

    return BridgeInfo(
        schema=schema,
        port=port,
        token=token,
        pid=raw.get("pid"),
        mod_version=str(raw.get("modVersion", "")),
        game_version=str(raw.get("gameVersion", "")),
        smapi_version=str(raw.get("smapiVersion", "")),
        started_at=str(raw.get("startedAt", "")),
        path=p,
    )


class BridgeClient:
    """薄 HTTP 客户端。每个方法只做一件事：发请求、解析、把失败变成 BridgeError。"""

    def __init__(self, info: BridgeInfo | None = None, timeout: float = 5.0) -> None:
        self.info = info if info is not None else load_bridge_info()
        self.timeout = timeout

    # ---------- 内部 ----------
    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        auth: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.info.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if auth:
            headers["X-Auth-Token"] = self.info.token

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
                http_status = resp.status
        except urllib.error.HTTPError as exc:
            # 4xx/5xx 也是协议的一部分（401 unauthorized / 404 not_found），要把 body 读出来
            payload = exc.read().decode("utf-8", errors="replace")
            http_status = exc.code
        except urllib.error.URLError as exc:
            raise BridgeError(
                f"连不上 {url}：{exc.reason}。Mod 可能已卸载、端口被占或进程已退出。",
                status="unreachable_bridge",
            ) from exc
        except TimeoutError as exc:
            raise BridgeError(f"请求 {path} 超时（>{timeout or self.timeout}s）", status="timeout") from exc
        except OSError as exc:
            # 实机踩到的坑：游戏进程抖动/退出时，socket 会被**强制重置**，
            # 抛出来的是裸 ConnectionResetError（http.client.RemoteDisconnected 也是它的子类），
            # 不属于 URLError，不捕就会让整个"脑"带 traceback 崩掉。
            raise BridgeError(
                f"与 Mod 的连接中断（{type(exc).__name__}: {exc}）。游戏可能正在退出或已崩溃。",
                status="connection_broken",
            ) from exc
        except http.client.HTTPException as exc:
            # 收到半截响应/非法状态行等：同样属于"对端不可信"，绝不让异常逃逸。
            raise BridgeError(f"与 Mod 的 HTTP 交互异常（{type(exc).__name__}: {exc}）",
                              status="bad_response") from exc

        try:
            result = json.loads(payload) if payload.strip() else {}
        except json.JSONDecodeError as exc:
            raise BridgeError(
                f"{path} 返回的不是 JSON（HTTP {http_status}）：{payload[:200]!r}",
                status="bad_response",
                http_status=http_status,
            ) from exc

        if not isinstance(result, dict):
            raise BridgeError(f"{path} 返回的 JSON 不是对象", status="bad_response", http_status=http_status)

        if not result.get("ok", False):
            raise BridgeError(
                str(result.get("reason") or result.get("status") or "未说明原因"),
                status=str(result.get("status", "error")),
                http_status=http_status,
                payload=result,
            )
        return result

    # ---------- 公开接口（协议 §4/§5/§6） ----------
    def health(self, *, timeout: float | None = None) -> dict[str, Any]:
        """协议 §4。不需要令牌。"""
        return self._request("GET", "/v1/health", auth=False, timeout=timeout)

    def observe(self, detail: str = "summary", *, timeout: float | None = None) -> dict[str, Any]:
        """协议 §5。`detail` 只能是 summary / full。"""
        if detail not in ("summary", "full"):
            raise ValueError(f"detail 只能是 summary 或 full，收到 {detail!r}")
        result = self._request("GET", f"/v1/observe?detail={detail}", timeout=timeout)
        schema = result.get("schema")
        if schema != SCHEMA_WORLD:
            if schema in SCHEMA_WORLD_LEGACY:
                _warn_once(
                    f"world-schema:{schema}",
                    f"Mod 返回旧快照 {schema!r}（期望 {SCHEMA_WORLD!r}）：游戏里装的 Mod 还是升级前的版本"
                    f"（期望 {MOD_VERSION_EXPECTED}），新字段（如 location.doors[] / location.furniture[]）不可用。"
                    f"重启游戏完成升级后本警告消失。",
                )
            else:
                raise BridgeError(
                    f"observe 返回 schema={schema!r}，期望 {SCHEMA_WORLD!r}（协议 §8）",
                    status="schema_mismatch",
                    payload=result,
                )
        return result

    def exec_skill(
        self,
        skill: str,
        args: dict[str, Any] | None = None,
        *,
        timeout_ms: int = 8000,
        based_on_seq: int | None = None,
        http_timeout: float | None = None,
    ) -> dict[str, Any]:
        """协议 §6。

        `http_timeout` 默认比 `timeout_ms` 多留 3 秒，避免"客户端先超时、
        服务端还在跑"造成两边认知不一致（旧协议没有这个区分）。
        """
        body: dict[str, Any] = {"skill": skill, "timeout_ms": int(timeout_ms)}
        if args:
            body["args"] = args
        if based_on_seq is not None:
            body["based_on_seq"] = int(based_on_seq)
        result = self._request(
            "POST",
            "/v1/exec",
            body,
            timeout=http_timeout if http_timeout is not None else (timeout_ms / 1000.0 + 3.0),
        )

        # exec 的 schema 校验采取"**存在才校验**"的宽松口径：
        # 实测 Mod 的部分响应分支（如未实现技能）不带 schema 字段，硬校验会把自己人打自己人
        # （正是旧项目缺陷 D5 的翻版）。字段缺失 = 容忍并继续；字段存在但不符 = 明确报错。
        schema = result.get("schema")
        if schema is not None and schema != SCHEMA_EXEC:
            raise BridgeError(
                f"exec 返回 schema={schema!r}，期望 {SCHEMA_EXEC!r}（协议 §8）",
                status="schema_mismatch",
                payload=result,
            )

        # world_stuck 是 ok=false + status=world_stuck，已在 _request 里转成 BridgeError。
        # 语义提醒：它表示"模态关了但世界没恢复"，脑**必须升级处理（重启游戏）**，
        # 绝不允许当普通失败重试。
        return result

    # 便捷封装：里程碑 A 的技能
    def noop(self) -> dict[str, Any]:
        return self.exec_skill("noop", timeout_ms=1000)

    def dismiss_modal(self, *, timeout_ms: int = 5000) -> dict[str, Any]:
        """关闭当前挡路的模态（dismiss_modal）。

        成功后请**务必检查 `worldResumed`**：它为 False 时说明模态关了但世界没恢复
        （`canMove=false`），此时状态是 `world_stuck`，脑需要重启游戏而不是继续排计划。
        """
        return self.exec_skill("dismiss_modal", timeout_ms=timeout_ms)

    def move_to(
        self,
        x: int,
        y: int,
        *,
        timeout_ms: int = 8000,
        based_on_seq: int | None = None,
        allow_bed: bool = False,
    ) -> dict[str, Any]:
        """走到指定格（move_to）。

        `allow_bed=False`（默认）时，床格会被 Mod 拒绝——无人值守踩到床会触发
        `Go to sleep for the night?` 睡觉流程，是会改写游戏进程的破坏性副作用。
        只有**明确要复现睡觉弹窗来做 `dismiss_modal` 验证**时才传 `allow_bed=True`；
        它只解禁"床"这一项，其它不可踩家具照样拒绝。

        注意：该参数要求 Mod ≥ 0.5.1（协议 §6 `move_to.args.allow_bed`）。
        **低于 0.5.1 的 Mod 会静默忽略未知参数**——真机实测 v0.5.0 上 `allow_bed=True` 与不带
        该参数的请求返回**逐字相同**的 `precondition_failed: 目标格 (9,9) 有家具（床）`。
        所以"脑发了参数、体不认识"是这里最容易踩的坑：脑不能靠"我发了"就当"它生效了"，
        必须以回执（`reason` 里有没有 `allow_bed=true`）为准。
        """
        args: dict[str, Any] = {"tile": [int(x), int(y)]}
        if allow_bed:
            args["allow_bed"] = True
        return self.exec_skill("move_to", args, timeout_ms=timeout_ms, based_on_seq=based_on_seq)

    def move_to_location(
        self,
        location: str,
        *,
        tile: tuple[int, int] | None = None,
        timeout_ms: int = 30000,
        based_on_seq: int | None = None,
        allow_bed: bool = False,
    ) -> dict[str, Any]:
        """跨地点移动（move_to_location，Mod ≥ 0.6.0）。

        `location` 只用来**在游戏真值里查表**（`Game1.locations[i].Name` 与每条 warp 的
        `TargetName`，大小写不敏感）；路线一律由 Mod 侧按 warp 图 BFS 求出，脑**不需要**
        也不应该自己规划跨地点路线（架构 §5.2.1 禁止硬编码地名/坐标）。

        传送是**游戏自己**触发的：Mod 只把玩家走到 warp 源格，等
        `Game1.currentLocation.Name` 真的变了才算一跳成功。因此：
          * 成功回执带 `path`（地点序列）、`hops[]`（每跳的 from/to/arrivedAt/
            sourceTile/landingTile/usedTile/ms/result）、`reachedLocation`；
          * `hops[].result == "mismatch"` = warp 上写的目标与实际落地地点不一致（脑要审计）；
          * 失败回执**也**带 path/hops，用来判断"走到哪一步断的"。

        失败状态码：`precondition_failed`（地点不存在/坐标为负/目标格有阻挡家具）、
        `unreachable_no_route`（warp 图上无路）、`hop_failed`（走到触发格但没传送）、
        `unreachable`、`blocked`、`timeout`、`ui_modal`、`no_save`。
        """
        args: dict[str, Any] = {"location": location}
        if tile is not None:
            args["tile"] = [int(tile[0]), int(tile[1])]
        if allow_bed:
            args["allow_bed"] = True
        return self.exec_skill("move_to_location", args, timeout_ms=timeout_ms, based_on_seq=based_on_seq)

    def load_save(
        self,
        save: str | None = None,
        *,
        force: bool = False,
        timeout_ms: int = 60000,
    ) -> dict[str, Any]:
        """从**标题界面**读档（load_save，Mod ≥ 0.6.0）。

        用途（自主性前提，不是便利功能）：
          * 换 Mod dll 必须重启游戏，重启后游戏停在标题界面；标题界面上唯一的正常入口是
            "点 Continue" —— 那属于**伪造输入**，被硬纪律①禁止；
          * 无人值守长跑必须能从崩溃/重启里自己爬起来。

        实现上调用的是**游戏自己的** `SaveGame.Load(存档名)`（与玩家点 Continue 同一条路），
        不写任何世界状态、不动角色坐标/金钱/时间。成功判据是"世界真的可读了"
        （`Context.IsWorldReady` 且 player/currentLocation 都读得到）。

        `save=None` 时由 Mod 自动挑**最近写过**的存档。
        ⚠️ 已经**在存档里**时默认拒绝（`precondition_failed`）：读档会直接丢掉当天进度
        （游戏只在睡觉时落盘）。确实要丢弃当前进度时传 `force=True`。

        成功回执含 `save`（存档文件夹名）、`reachedLocation`、`tile`。
        """
        args: dict[str, Any] = {}
        if save:
            args["save"] = save
        if force:
            args["force"] = True
        return self.exec_skill("load_save", args, timeout_ms=timeout_ms)

    def interact(self, tile: tuple[int, int] | None = None, *, timeout_ms: int = 5000) -> dict[str, Any]:
        """**用一下面前那一格**（interact，Mod ≥ 0.7.1）。

        实现上是调**游戏自己的动作入口** `GameLocation.checkAction(tile, viewport, player)`
        （api-probe 编译期实证 3 参重载存在）—— 与 `dismiss_modal` 调 `answerDialogue` 而不按确认键
        **同一条纪律**：不合成键鼠事件。

        【为什么进建筑必须用它】真机证据（2026-08-11 晚）：
          * `Farm` / `FarmHouse` 的 `location.doors` **都是空的** ⇒ `isCollidingWithDoors` 无从触发；
          * `GameLocation.checkAction` 的 IL 里遍历 `this.buildings`，调 `getPointForHumanDoor()` /
            `getWarpFromDoor(...)` / **`Building.doAction(Vector2, Farmer)`** ⇒ 进建筑是"动作"路径；
          * `door_push`（把"朝门走一步"喂给寻路器）只能把玩家推到墙前 3 像素，矩形角**永远进不了门格**。

        `tile=None` 时用"玩家当前面朝的那一格"（走到门口朝上时正好是门格）。
        回执里的 `reachedLocation` 是**动作发起时**的地点；门/建筑的传送由游戏自己发起、有淡出期，
        **必须以随后的 observe 为准**。
        """
        args: dict[str, Any] = {}
        if tile is not None:
            args["tile"] = [int(tile[0]), int(tile[1])]
        return self.exec_skill("interact", args, timeout_ms=timeout_ms)

    def use_tool(
        self,
        tile: tuple[int, int] | None = None,
        *,
        tool: str | None = None,
        timeout_ms: int = 12000,
    ) -> dict[str, Any]:
        """**用工具对某一格动手**（use_tool，Mod ≥ 0.7.6）：砍树枝 / 敲石头 / 割草 / 锄地 / 浇水。

        `tool`：`axe` / `pickaxe` / `hoe` / `can` / `scythe` / `auto`（省略＝`auto`）。
        `auto` 由 Mod 按目标格上的东西挑（twig→axe、可破石头→pickaxe、weed|grass→scythe、
        空耕地→hoe、有作物的耕地→can），并在回执的 `reason` 里**报出真实用的那件物品名** ——
        所以脑必须读回执核对"它到底拿了什么工具"，不能假设。

        实现走**游戏自己的入口** `Game1.pressUseToolButton()`（api-probe 实证存在；
        `Farmer.UseTool(...)` / `completeToolUse()` 在 1.6.15 **不存在**），选工具用 `CurrentToolIndex`。
        纪律同 `interact`/`dismiss_modal`：不合成键鼠事件。

        ⚠️ **验收必须用 observe 的 `location.tiles[]` 差分**：回执只是声明，格子上东西没了才是证据。
        失败状态码：`precondition_failed`（没这类工具/有模态）、`tool_ineffective`（挥满 6 次目标格仍在）、
        `timeout`、`no_save`。
        """
        args: dict[str, Any] = {}
        if tile is not None:
            args["tile"] = [int(tile[0]), int(tile[1])]
        if tool:
            args["tool"] = tool
        return self.exec_skill("use_tool", args, timeout_ms=timeout_ms)

    def select_item(self, item: str, *, timeout_ms: int = 5000) -> dict[str, Any]:
        """选中背包里的某件物品（`select_item`，Mod ≥ 0.7.9）。

        `item` 可以是 `ItemId`（例 `472`）、`QualifiedItemId`（`(O)472`）或物品名，大小写不敏感。
        实现是设 `Game1.player.CurrentToolIndex`（等价于玩家滚快捷栏），**并复核** `CurrentItem`
        真的是它 —— 不符时报 `select_failed`，绝不"我设了就当选中了"。
        回执 reason 给出槽位与物品名；拿不到时是 `precondition_failed` + 完整背包清单。
        """
        return self.exec_skill("select_item", {"item": item}, timeout_ms=timeout_ms)

    def plant(self, seed: str, tile: tuple[int, int], *, timeout_ms: int = 15000) -> dict[str, Any]:
        """把种子种进**已经锄好的耕地**（`plant`，Mod ≥ 0.7.9）。

        `seed`：种子 `ItemId`（例 `472` = 防风草种子）；`tile`：目标耕地格。
        前置条件是"该格是 `HoeDirt` 且没有作物"（不满足直接 `precondition_failed`，不瞎试）。
        实现走**游戏自己的使用键入口** `Game1.pressUseToolButton()`（最多 3 次）；
        探针证伪了 `Object.performUseAction` 的"对指定格使用"重载，也刻意不调 `HoeDirt.plant`
        （那是直接写世界状态）。
        ⚠️ **验收必须用 `tiles[]` 差分**：该格要真的出现 `crop`（回执只是声明）。
        """
        return self.exec_skill(
            "plant",
            {"seed": seed, "tile": [int(tile[0]), int(tile[1])]},
            timeout_ms=timeout_ms,
        )

    def sleep(self, *, timeout_ms: int = 180000) -> dict[str, Any]:
        """**睡到第二天**（`sleep`，Mod ≥ 0.7.20）—— 跨日的唯一正路（长跑循环的日终动作）。

        实现走**游戏自己让玩家点"是"的那条路**：`GameLocation.answerDialogueAction("Sleep_Yes", null)`
        → `startSleep()` → `doSleep()` → `Game1.NewDay(0f)`（IL 证据见 `docs\\_il-plant-consume.md`
        同级的 sleep 取证与 `logs\\il-sleep-entry-u8.txt`）。不是合成键鼠、也不是自己写 `Date`。

        ⚠️ **验收必须用 observe 差分**：`clock` 的 `(year, season, day)` 必须真的变大。
        回执 reason 里的"第 N 天"是 `Game1.Date.TotalDays`（春 1 日起 0 基），
        与 `clock.day`（月内日）**差 1**，别拿回执当日期证据。
        睡眠本身是异步协程：Mod 侧跨 tick 等到跨日完成才回执（实测 1.7s），所以 HTTP 要给足时间。
        """
        return self.exec_skill("sleep", timeout_ms=timeout_ms, http_timeout=timeout_ms / 1000.0 + 12.0)

    def buy(
        self,
        item: str,
        count: int = 1,
        *,
        shop: str = "SeedShop",
        timeout_ms: int = 25000,
    ) -> dict[str, Any]:
        """**买种子**（`buy`，Mod ≥ 0.7.20）。

        `item`：`ItemId`（`472`）/ `QualifiedItemId`（`(O)472`）/ 物品名，大小写不敏感；
        `count`：**想买几个**（请求量，不是承诺量）—— Mod 会按"钱够几个 / 库存 / 堆叠上限"夹小，
        最终由游戏自己的 `ShopMenu.tryToPurchaseItem(item, null, count, 0, 0)` 裁决；
        `shop`：`Data/Shops` 里的店铺 id（默认 `SeedShop` = 种子店）。

        ⚠️ 纪律同 `plant`：**回执只是声明**。验收要用 observe 差分看两件事——
        `player.money` 少了多少、`player.inventory[]` 里这件多了几个；
        回执里的"游戏返回值"**不是成败**（IL 证明它只表示"这行该撤了"）。
        失败状态码：`item_not_sold`（附货架清单）/ `cannot_afford` / `no_inventory_space` /
        `shop_unavailable` / `shop_timeout` / `purchase_no_effect` / `purchase_partial`。
        """
        return self.exec_skill(
            "buy",
            {"item": item, "count": int(count), "shop": shop},
            timeout_ms=timeout_ms,
        )

    def quit_game(self, *, timeout_ms: int = 3000) -> dict[str, Any]:
        """让**游戏自己退出**（quit_game，Mod ≥ 0.7.0）。

        用游戏自己的退出标志 `Game1.quit`（api-probe 编译期实证可写）—— 等价于玩家点退出，
        既不伪造键鼠、也不写世界状态，更不是 `Stop-Process` 强杀。

        【为什么需要它】换 Mod dll 必须重启游戏，而重启后停在标题界面。
        "启动 + 自己读档" 已经自主（`load_save`），这一步把另一半补上：
        **发现问题需要关游戏时，脑自己把它关掉**（详见 `tools\\deploy-mod.py`）。

        ⚠️ **回执可能收不到**：置位后游戏会在随后的帧里退出，HTTP 连接可能被重置。
        因此本方法把 `connection_broken` / `bad_response` / `unreachable_bridge` / `timeout`
        一律折成 `{"status": "assumed_quitting"}` —— 那是**预期行为**，不是故障。
        调用方必须再以**进程是否真的消失**为准（`pid_alive(bridge_info.pid)` 或进程名轮询）。
        """
        try:
            return self.exec_skill("quit_game", timeout_ms=timeout_ms, http_timeout=6.0)
        except BridgeError as exc:
            if exc.status in ("connection_broken", "bad_response", "unreachable_bridge", "timeout"):
                return {
                    "ok": True,
                    "status": "assumed_quitting",
                    "reason": f"请求中断（{exc.status}）：游戏很可能已经在退出（以进程是否消失为准）",
                }
            raise
