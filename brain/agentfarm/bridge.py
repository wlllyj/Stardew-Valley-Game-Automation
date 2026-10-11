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

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---- 契约常量（改这里必须同步 docs/03-桥接协议.md 并升版本号） ----
SCHEMA_BRIDGE = "agentfarm-bridge/1"
SCHEMA_WORLD = "agentfarm-world/2"   # v2：新增 isOutdoorFarm / activeMenuText / dialogueResponses /
                                     #      dialogueIsQuestion / onScreenMenus / windowActive / canMove /
                                     #      hasController；删除 dialogsOnScreen。见 docs/03-桥接协议.md
MOD_VERSION_EXPECTED = "0.1.0"

# 已知基线：环境实测快照 docs/02-环境实测快照.md
BASELINE_GAME_VERSION = "1.6.15"
BASELINE_SMAPI_VERSION = "4.5.2"

# 覆盖 bridge.json 位置的环境变量（测试与多实例调试用）
ENV_BRIDGE_JSON = "AGENTFARM_BRIDGE_JSON"


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
        return self._request(
            "POST",
            "/v1/exec",
            body,
            timeout=http_timeout if http_timeout is not None else (timeout_ms / 1000.0 + 3.0),
        )

    # 便捷封装：里程碑 A 的两个技能
    def noop(self) -> dict[str, Any]:
        return self.exec_skill("noop", timeout_ms=1000)

    def move_to(self, x: int, y: int, *, timeout_ms: int = 8000, based_on_seq: int | None = None) -> dict[str, Any]:
        return self.exec_skill(
            "move_to", {"tile": [int(x), int(y)]}, timeout_ms=timeout_ms, based_on_seq=based_on_seq
        )
