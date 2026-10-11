# -*- coding: utf-8 -*-
"""无人值守**运行循环**（监督者）：把 `watchdog` 从"手动跑一次"变成"一直在看着"。

【为什么需要它（旧账，条目 00888）】
`brain\\agentfarm\\watchdog.py` 早就写好了（10 类发现、20 个单测），但一直只有
`agentfarm triage` 手动跑一次 —— 也就是"人得想起来去看"。无人值守长跑（P3：连续 3 个游戏日）
这么干必然重演旧项目的失败模式：**空转了 40 分钟没人发现**。
本模块就是那个"一直在看"的循环。

【它做什么 / 不做什么（刻意分开，便于各自单测）】
* `watchdog.assess()` 负责**判断**（纯函数、不碰网络）；
* 本模块负责**取数 + 时钟 + 停机动作 + 落盘报告**：
    每 `interval` 秒取一次 `health` + `observe` → `assess()` → 按判定处理：
      - `ok`   ：继续（打印心跳，让人回来看日志知道它活着）
      - `warn` ：继续（warn 不拦路：弹窗之类可恢复的情况本来就该自动化自己处理）
      - `stop` ：**写 `logs/stops/stop-*.json` 事故报告**（带上当时的 health/observe 原文）
                 → 按 `--on-stop` 决定是否 `quit_game` 收工 → 退出码 2
* **不做**：不自己重试到天亮、不自己改世界状态。规划层（P3 的任务队列）以后挂在
  `on_sample` 钩子上，与本模块的监督职责分开 —— 这样"监督逻辑"不会被业务逻辑污染。

【桥连不上也算 stop】
`assess()` 是纯函数，拿不到"连不上"这件事；但游戏进程死掉/端口没了是**必须停机**的情况
（继续等下去只是浪费时间）。所以本模块在取数失败时自己合成一条
`bridge_unreachable`（STOP 级）发现，与其它发现一起进报告。

用法：
    set PYTHONPATH=D:\\...\\星露谷游戏自动化\\brain
    python -m agentfarm run                      # 每 15 秒体检一次，默认跑 60 分钟
    python -m agentfarm run --minutes 180 --on-stop quit
    python -m agentfarm run --max-samples 5      # 只采样 5 次（自检/测试用）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .bridge import BridgeClient, BridgeError, MOD_VERSION_EXPECTED
from .watchdog import (
    LEVEL_STOP,
    LEVEL_WARN,
    Finding,
    assess,
    format_findings,
    verdict,
    write_stop_report,
)

DEFAULT_INTERVAL_SECONDS = 15.0
DEFAULT_MINUTES = 60.0

# 停机动作
ON_STOP_REPORT = "report"   # 只落报告（默认：让"人/外层脚本"决定下一步）
ON_STOP_QUIT = "quit"       # 落报告 + 让游戏自己退出（quit_game）
ON_STOP_NOTHING = "nothing"


@dataclass
class Sample:
    """一次采样（取数结果与判定）。测试与 `on_sample` 钩子都用它。"""

    at: float
    health: dict[str, Any] | None
    observe: dict[str, Any] | None
    findings: list[Finding]
    verdict: str
    error: str | None = None      # 取数失败时的摘要（BridgeError.status: reason）


class SupervisedRunner:
    """监督循环。所有外部依赖都可注入，便于离线单测。"""

    def __init__(
        self,
        client_factory: Callable[[], BridgeClient] = BridgeClient,
        *,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        duration_seconds: float | None = DEFAULT_MINUTES * 60.0,
        max_samples: int | None = None,
        on_stop: str = ON_STOP_REPORT,
        report_dir: Path | None = None,
        mod_version_expected: str | None = MOD_VERSION_EXPECTED,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        log: Callable[[str], None] = print,
        on_sample: Callable[[Sample], None] | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.interval = float(interval)
        self.duration_seconds = duration_seconds
        self.max_samples = max_samples
        self.on_stop = on_stop
        self.report_dir = report_dir
        self.mod_version_expected = mod_version_expected
        self._sleep = sleep
        self._now = now
        self.log = log
        self.on_sample = on_sample

    # ---------- 取一次样 ----------
    def sample_once(self, client: BridgeClient | None = None) -> Sample:
        """取 health + observe，跑 `assess()`；连不上桥时合成 `bridge_unreachable`(STOP)。"""
        health: dict[str, Any] | None = None
        observe: dict[str, Any] | None = None
        error: str | None = None

        try:
            c = client or self.client_factory()
            # ⚠️ 每次都用**新建**的 client：token 每次启动游戏都会变，必须重读 bridge.json。
            health = c.health(timeout=5.0)
            try:
                observe = c.observe("summary", timeout=5.0)
            except BridgeError as exc:
                # 能探活但取不到快照（例如刚开始读档）：不算探活失败，交给 assess 判。
                error = f"observe 失败：{exc.status}: {exc}"
        except BridgeError as exc:
            error = f"health 失败：{exc.status}: {exc}"
        except Exception as exc:  # noqa: BLE001 - 任何异常都不许把无人值守循环带崩
            error = f"{type(exc).__name__}: {exc}"

        findings = assess(
            health, observe,
            mod_version_expected=self.mod_version_expected,
        )
        if error is not None:
            # 连不上/取不到 = 必须停机：继续等只是浪费时间（游戏可能已经死了）。
            findings.append(Finding(
                "bridge_unreachable", LEVEL_STOP,
                "与 Mod 的通信断了（游戏可能已退出/崩溃）。请人工或外层脚本重启游戏后重新读档",
                error,
            ))

        return Sample(at=self._now(), health=health, observe=observe,
                      findings=findings, verdict=verdict(findings), error=error)

    # ---------- 主循环 ----------
    def run(self) -> int:
        """返回退出码：0 = 跑满时长正常结束；2 = 因 stop 级发现停机。"""
        started = self._now()
        n = 0
        self.log(f"监督循环启动：间隔 {self.interval:g}s"
                 + (f"，时长 {self.duration_seconds / 60:.0f} 分钟" if self.duration_seconds else "")
                 + (f"，最多 {self.max_samples} 次采样" if self.max_samples else "")
                 + f"，停机动作 on_stop={self.on_stop}")

        while True:
            n += 1
            s = self.sample_once()
            if self.on_sample is not None:
                try:
                    self.on_sample(s)
                except Exception as exc:  # noqa: BLE001 - 钩子不许带崩监督
                    self.log(f"[WARN] on_sample 钩子抛异常（已忽略）：{type(exc).__name__}: {exc}")

            el = self._now() - started
            line = (f"[{n}] t+{el:6.0f}s verdict={s.verdict}"
                    f" clock={(s.observe or {}).get('clock', {}).get('timeOfDay')}"
                    f" loc={((s.observe or {}).get('player') or {}).get('location')}")
            self.log(line)
            if s.verdict != "ok":
                self.log(format_findings(s.findings))

            if s.verdict == LEVEL_STOP:
                path = write_stop_report(
                    s.findings, health=s.health, observe=s.observe,
                    directory=self.report_dir,
                    note=f"无人值守监督循环第 {n} 次采样判定为 stop（间隔 {self.interval:g}s）",
                )
                self.log(f"🔴 已停机并落事故报告：{path}")
                self._handle_on_stop()
                return 2

            if self.max_samples is not None and n >= self.max_samples:
                self.log(f"已跑满 {n} 次采样，正常结束")
                return 0
            if self.duration_seconds is not None and el >= self.duration_seconds:
                self.log(f"已跑满 {el / 60:.1f} 分钟（{n} 次采样），正常结束")
                return 0

            self._sleep(self.interval)

    # ---------- 停机动作 ----------
    def _handle_on_stop(self) -> None:
        if self.on_stop == ON_STOP_QUIT:
            try:
                res = self.client_factory().quit_game()
                self.log(f"已请求游戏退出（quit_game）：{res.get('status')} — {res.get('reason')}")
            except Exception as exc:  # noqa: BLE001
                self.log(f"[WARN] quit_game 失败（{type(exc).__name__}: {exc}）；游戏保持原样，请看事故报告")
        elif self.on_stop == ON_STOP_NOTHING:
            self.log("按 on_stop=nothing：不动游戏，只留事故报告")
        else:
            self.log("按 on_stop=report：不动游戏，只留事故报告（外层脚本可据此决定是否 deploy-mod.py）")


def load_last_stop_report(directory: Path | None = None) -> dict[str, Any] | None:
    """读最近一次事故报告（`agentfarm run --last-stop` 用；没有则 None）。"""
    d = directory or (Path(__file__).resolve().parents[2] / "logs" / "stops")
    if not d.exists():
        return None
    files = sorted(d.glob("stop-*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
