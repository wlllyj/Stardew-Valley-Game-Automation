# -*- coding: utf-8 -*-
"""无人值守体检（watchdog）：把"静默停摆"变成"大声失败"。

## 这个模块存在的理由（全部来自真机事故，不是设想）

1. **接口报 ok、画面正常、实际永久停摆**（`docs/00-开发日志.md` 条目 013）。
   走到床边引出 `Go to sleep for the night?` → `dismiss_modal` 报 ok →
   之后 `isModal=false`、`canMove=false`、世界时钟 45 秒不动，角色谁也指挥不动。
   当时脑**完全没有察觉**：它看到的是"弹窗已关闭、一切正常"。
2. **失焦冻结**曾让"角色不动"被误判成"寻路失败"（条目 015 的三条撤回之一）。
   现在根因已由 Mod v0.5.0 消除，但**脑仍必须能自己发现它回来了**
   （`health.game.pauseWhenOutOfFocus` 翻回 `true` 就是铁证）。
3. **诊断信息一旦撒谎，比没有诊断更糟**：doctor 曾因为读错字段位置
   （`windowActive` 只在 `/v1/health` 里，observe 里根本没有）而永远打印
   "窗口在前台"。所以本模块**只依据显式读到的事实**下结论，拿不到就说拿不到。

## 判据怎么来的

每条判据都对应一个**可复现的观察**，写在 `Finding.evidence` 里，便于事后复盘。
"停"（`stop`）只留给**脑自己修不了**的情况——那些情况继续跑只会污染账本；
能靠一个技能修好的（例如弹窗要 `dismiss_modal`）只报 `warn`。

## 用法

    from agentfarm.watchdog import assess, verdict, require_healthy, write_stop_report

    findings = assess(health, observe)          # 纯函数，离线可测
    print(verdict(findings))                    # "ok" / "warn" / "stop"
    require_healthy(health, observe)            # stop 时抛 UnattendedStop

`assess()` **不发任何请求**：调用方自己取 `health()`/`observe()`，
这样它既能在生产循环里用，也能在单元测试里用字典直接喂。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# 时钟停滞多久算"世界没在推进"。真机基线：正常时停滞在 0.4~7s 之间往复
# （v0.5.0 失焦验收：16 次采样最长 6.9s；前台 45s 跑 8 格时最长 7.3s），
# 所以 40s 已经远超正常抖动，而 013 事故里是 45s+ 一直不动。
DEFAULT_STALL_SECONDS = 40.0

# 013 事故的"半卡死"特征比世界停滞更严格：它同时伴随 canMove=false。
HALF_DEADLOCK_STALL_SECONDS = 20.0

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_STOP = "stop"

_ORDER = {LEVEL_OK: 0, LEVEL_WARN: 1, LEVEL_STOP: 2}


@dataclass(frozen=True)
class Finding:
    """一条体检结论。`code` 是机器可读原因码（与架构 §5.4 的 veto 原因码同风格）。"""

    code: str
    level: str
    message: str
    evidence: str = ""


class UnattendedStop(RuntimeError):
    """无人值守必须停下来的情况。携带全部 findings 供上层写事故报告。"""

    def __init__(self, findings: Iterable[Finding]) -> None:
        self.findings = [f for f in findings if f.level == LEVEL_STOP]
        detail = "；".join(f"{f.code}: {f.message}" for f in self.findings) or "（无细节）"
        super().__init__(f"无人值守安全检查未通过，已停止：{detail}")


def _dig(d: Any, *path: str) -> Any:
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def assess(
    health: dict[str, Any] | None,
    observe: dict[str, Any] | None,
    *,
    mod_version_expected: str | None = None,
    stall_seconds: float = DEFAULT_STALL_SECONDS,
) -> list[Finding]:
    """对一次 `health` + `observe` 采样做体检，返回 findings（可能为空）。

    刻意**不抛异常**、也不访问网络：把判断与取数分开，才能离线单测。
    """
    health = health or {}
    observe = observe or {}
    out: list[Finding] = []

    # ---------- 1. 根本没进游戏 ----------
    has_save = observe.get("hasSaveLoaded")
    if has_save is False:
        out.append(Finding(
            "no_save_loaded", LEVEL_STOP,
            "没有加载存档，任何技能都无从谈起（请先在游戏里读档）",
            "observe.hasSaveLoaded=false",
        ))
    if _dig(health, "runtime", "onTitleScreen") is True:
        out.append(Finding(
            "title_screen", LEVEL_STOP,
            "游戏停在标题界面",
            "health.runtime.onTitleScreen=true",
        ))

    # ---------- 2. 失焦暂停有没有被改回来（v0.5.0 的命门） ----------
    oof = _dig(health, "game", "pauseWhenOutOfFocus")
    if oof is True:
        out.append(Finding(
            "oof_pause_regression", LEVEL_STOP,
            "「失焦自动暂停」又是 true 了：窗口一旦不在前台，世界时钟与角色更新都会被整段跳过"
            "（IL 证据 Game1._update IL_0444–IL_0480）。Mod ≥0.5.0 应该每帧扳回，"
            "看到这条说明扳回失败或 Mod 版本过低",
            "health.game.pauseWhenOutOfFocus=true"
            + (f"，oofFixCount={_dig(health, 'game', 'oofFixCount')}"),
        ))
    elif oof is None:
        out.append(Finding(
            "oof_field_missing", LEVEL_WARN,
            "health 里没有 pauseWhenOutOfFocus（Mod <0.5.0）：无法判断失焦时世界是否还在推进",
            "health.game.pauseWhenOutOfFocus 缺失",
        ))

    # ---------- 3. 版本/协议对不上 ----------
    if mod_version_expected is not None:
        got = health.get("modVersion")
        if got is not None and got != mod_version_expected:
            out.append(Finding(
                "mod_version_mismatch", LEVEL_WARN,
                f"游戏里跑的 Mod 版本 {got} ≠ 脑期望的 {mod_version_expected}："
                "可能是『脑已升级、游戏里还是旧 dll』——新参数会被**静默忽略**"
                "（真机实测 v0.5.0 上 allow_bed=true 与不带该参数返回逐字相同的结果）",
                f"health.modVersion={got}",
            ))

    # ---------- 4. 世界在不在推进 ----------
    advancing = _dig(observe, "liveness", "worldAdvancing")
    stall = _num(_dig(observe, "liveness", "secondsSinceClockMoved"))
    if advancing is False:
        out.append(Finding(
            "world_stalled", LEVEL_STOP,
            "Mod 自报世界没有在推进（worldAdvancing=false）",
            f"liveness.secondsSinceClockMoved={stall}",
        ))
    elif stall is not None and stall > stall_seconds:
        out.append(Finding(
            "clock_stalled", LEVEL_STOP,
            f"世界时钟已经 {stall:.1f}s 没动（阈值 {stall_seconds:.0f}s）："
            "脑自己修不了，继续跑只会让账本腐烂",
            f"liveness.secondsSinceClockMoved={stall:.1f}",
        ))

    # ---------- 5. 013 的半卡死：模态已关、却谁也动不了 ----------
    is_modal = _dig(observe, "ui", "isModal")
    can_move = _dig(observe, "player", "canMove")
    if (
        can_move is False
        and is_modal is False
        and stall is not None
        and stall > HALF_DEADLOCK_STALL_SECONDS
    ):
        out.append(Finding(
            "half_deadlock", LEVEL_STOP,
            "半卡死（条目 013 的原样复现）：**模态已关闭**但角色动不了、世界时钟也不走。"
            "确认过的唯一出路是重启游戏/重新读档——脑不许假装还能继续",
            f"ui.isModal=false，player.canMove=false，"
            f"secondsSinceClockMoved={stall:.1f}",
        ))

    # ---------- 6. 弹窗挡路（能修，所以只 warn） ----------
    if is_modal is True:
        menu = _dig(observe, "ui", "activeMenu")
        is_question = _dig(observe, "ui", "dialogueIsQuestion") is True
        extra = (
            "；这是**提问类**对话框，禁止盲按确认键（条目 013：盲按确认把世界按停在半卡死），"
            "要用 dismiss_modal 的具名回答"
            if is_question else ""
        )
        out.append(Finding(
            "modal_blocking", LEVEL_WARN,
            f"有菜单/对话挡着（{menu!r}），所有技能都会被 ui_modal 拒绝：请用 dismiss_modal 收尾{extra}",
            f"ui.isModal=true，ui.activeMenu={menu!r}",
        ))

    # ---------- 7. 体力 ----------
    stamina = _num(_dig(observe, "player", "stamina"))
    if stamina is not None and stamina <= 0:
        out.append(Finding(
            "stamina_exhausted", LEVEL_WARN,
            "体力为 0：农务类技能会失败（要么吃东西，要么回家睡觉）",
            f"player.stamina={stamina:.0f}",
        ))

    return out


def verdict(findings: Iterable[Finding]) -> str:
    """把 findings 归成一个总判定：`ok` / `warn` / `stop`（stop 优先）。"""
    level = LEVEL_OK
    for f in findings:
        if _ORDER.get(f.level, 0) > _ORDER[level]:
            level = f.level
    return level


def require_healthy(
    health: dict[str, Any] | None,
    observe: dict[str, Any] | None,
    *,
    mod_version_expected: str | None = None,
    stall_seconds: float = DEFAULT_STALL_SECONDS,
) -> list[Finding]:
    """体检；任何 `stop` 级发现都会抛 `UnattendedStop`（并把全部发现带出去）。

    返回 findings（含 warn），供调用方打印——**warn 不拦路**，
    因为自动化本来就该自己处理弹窗之类可恢复的情况。
    """
    findings = assess(
        health, observe,
        mod_version_expected=mod_version_expected,
        stall_seconds=stall_seconds,
    )
    if verdict(findings) == LEVEL_STOP:
        raise UnattendedStop(findings)
    return findings


def format_findings(findings: Iterable[Finding]) -> str:
    """人类可读的多行报告（CLI 用）。空列表也明确说"没发现异常"。"""
    lines: list[str] = []
    icon = {LEVEL_OK: "✅", LEVEL_WARN: "⚠️", LEVEL_STOP: "🔴"}
    for f in findings:
        lines.append(f"{icon.get(f.level, '?')} [{f.level}] {f.code}: {f.message}")
        if f.evidence:
            lines.append(f"      证据：{f.evidence}")
    if not lines:
        lines.append("✅ [ok] 没发现异常")
    return "\n".join(lines)


def write_stop_report(
    findings: Iterable[Finding],
    *,
    health: dict[str, Any] | None = None,
    observe: dict[str, Any] | None = None,
    directory: Path | None = None,
    note: str = "",
) -> Path:
    """把一次停机落成 JSON 事故报告（默认 `logs/stops/stop-<时间戳>.json`）。

    【为什么必须落盘】无人值守的意义是"人不在"，所以停下这件事**不能只打在屏幕上**——
    人回来要能一眼看到"什么时候、因为什么、当时世界长什么样"。
    """
    findings = list(findings)
    directory = directory or (Path(__file__).resolve().parents[2] / "logs" / "stops")
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone()
    path = directory / f"stop-{now.strftime('%Y%m%d-%H%M%S')}.json"
    payload = {
        "at": now.isoformat(timespec="seconds"),
        "note": note,
        "verdict": verdict(findings),
        "findings": [asdict(f) for f in findings],
        "health": health,
        "observe": observe,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
