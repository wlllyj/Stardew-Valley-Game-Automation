"""DeepSeek 大模型客户端（慢脑专用）。

设计约束：

1. **只用标准库**（urllib），与 bridge.py 同样零第三方依赖。
2. **密钥永不进日志、永不进异常消息**。解析顺序：环境变量 `DEEPSEEK_API_KEY`
   > `<仓库>/secrets/deepseek.key`（该目录已在 .gitignore 中）。
3. **`deepseek-flash` 是推理模型**（实测 2026-10-11）：响应里除 `content` 外还有
   `reasoning_content`，用量里单列 `completion_tokens_details.reasoning_tokens`。
   ⚠️ 踩过的坑：`max_tokens` 给小了（比如 8），token 会**全部被思考吃掉**、
   `content` 返回空字符串且 `finish_reason=length`。所以本客户端：
   - 默认给足 `max_tokens`；
   - 把"内容为空但确有推理"识别成明确错误，而不是当成"模型没说话"放过去。
4. **失败必须显式**：抛 `LlmError`，带 `status`（`unauthorized` / `rate_limited` /
   `server_error` / `network` / `truncated` / `bad_response`）。

用法：
    from agentfarm.llm import chat
    r = chat([{"role": "user", "content": "用一句话说明防风草几天成熟"}])
    print(r.content, r.elapsed_ms, r.usage.total_tokens)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"          # 用户选定（2026-10-11）
FALLBACK_MODELS = ("deepseek-flash", "deepseek-v4-pro")  # 实测该端点可用
DEFAULT_MAX_TOKENS = 8192                  # 推理模型要留足：实测一个"农场优先级"问题
                                           # 光思考就吃掉 2048+ token（见 docs/00-开发日志.md 条目 009）
DEFAULT_TIMEOUT = 90.0
MAX_ATTEMPTS = 3

ENV_API_KEY = "DEEPSEEK_API_KEY"
ENV_BASE_URL = "DEEPSEEK_BASE_URL"
ENV_MODEL = "DEEPSEEK_MODEL"
ENV_SECRETS_DIR = "AGENTFARM_SECRETS_DIR"

# brain/agentfarm/llm.py -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]


class LlmError(Exception):
    def __init__(self, reason: str, status: str = "error", http_status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason          # 注意：绝不放密钥
        self.status = status
        self.http_status = http_status

    def __str__(self) -> str:  # pragma: no cover
        extra = f" (HTTP {self.http_status})" if self.http_status else ""
        return f"[{self.status}]{extra} {self.reason}"


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __str__(self) -> str:
        return (f"prompt={self.prompt_tokens} completion={self.completion_tokens}"
                f"(含推理 {self.reasoning_tokens}) 合计={self.total_tokens}")


@dataclass
class LlmResult:
    content: str
    reasoning: str = ""
    model: str = ""
    finish_reason: str = ""
    usage: Usage = field(default_factory=Usage)
    elapsed_ms: int = 0
    attempts: int = 1


# ---------------------------------------------------------------- 配置解析

def secrets_dir() -> Path:
    override = os.environ.get(ENV_SECRETS_DIR)
    return Path(override) if override else REPO_ROOT / "secrets"


def load_api_key(required: bool = True) -> str:
    """环境变量优先，其次 `secrets/deepseek.key`（单行纯文本）。"""
    key = (os.environ.get(ENV_API_KEY) or "").strip()
    if key:
        return key
    path = secrets_dir() / "deepseek.key"
    if path.exists():
        key = path.read_text(encoding="utf-8").strip()
        if key:
            return key
    if required:
        raise LlmError(
            f"没有可用的 DeepSeek 密钥。请设置环境变量 {ENV_API_KEY}，"
            f"或把密钥写入 {path}（该目录不进版本库）。",
            status="no_api_key",
        )
    return ""


def base_url() -> str:
    return (os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")


def default_model() -> str:
    return os.environ.get(ENV_MODEL) or DEFAULT_MODEL


# ---------------------------------------------------------------- 主接口

def _post_json(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body[:400]
    except urllib.error.URLError as exc:
        raise LlmError(f"连不上 {url}：{exc.reason}", status="network") from exc
    except TimeoutError as exc:
        raise LlmError(f"请求超时（>{timeout}s）", status="network") from exc


def list_models(*, api_key: str | None = None, timeout: float = 20.0) -> list[str]:
    """`GET /models`，用于确认模型名是否真的存在（而不是照抄 DSH 的别名）。"""
    key = api_key or load_api_key()
    req = urllib.request.Request(
        f"{base_url()}/models", headers={"Authorization": f"Bearer {key}"}, method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise LlmError("查询模型列表失败（密钥可能无效）", status="unauthorized" if exc.code == 401 else "server_error",
                       http_status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"连不上 {base_url()}：{exc.reason}", status="network") from exc
    return [str(m.get("id")) for m in payload.get("data", []) if isinstance(m, dict)]


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    api_key: str | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> LlmResult:
    """一次对话补全。带有限的指数退避重试（只重试网络错误与 429/5xx）。"""
    key = api_key or load_api_key()
    use_model = model or default_model()
    payload: dict[str, Any] = {
        "model": use_model,
        "messages": messages,
        "max_tokens": int(max_tokens),
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = float(temperature)

    url = f"{base_url()}/chat/completions"
    last_error: LlmError | None = None

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        try:
            status, body = _post_json(url, payload, key, timeout)
        except LlmError as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if status == 200 and isinstance(body, dict):
            return _parse_result(body, use_model, elapsed_ms, attempt)

        detail = ""
        if isinstance(body, dict):
            detail = str((body.get("error") or {}).get("message") or body)[:300]
        else:
            detail = str(body)[:300]

        if status == 401:
            raise LlmError("密钥无效或已失效（HTTP 401）", status="unauthorized", http_status=401)
        if status == 429 or status >= 500:
            last_error = LlmError(
                f"服务端暂时不可用（HTTP {status}）：{detail}",
                status="rate_limited" if status == 429 else "server_error",
                http_status=status,
            )
            if attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 8))
                continue
            raise last_error
        raise LlmError(f"请求失败（HTTP {status}）：{detail}", status="bad_response", http_status=status)

    raise last_error or LlmError("未知失败", status="error")


def _parse_result(body: dict[str, Any], model: str, elapsed_ms: int, attempt: int) -> LlmResult:
    choices = body.get("choices") or []
    if not choices:
        raise LlmError(f"响应里没有 choices：{str(body)[:200]}", status="bad_response")
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "")
    reasoning = str(message.get("reasoning_content") or "")
    finish = str(choices[0].get("finish_reason") or "")

    raw_usage = body.get("usage") or {}
    completion_details = raw_usage.get("completion_tokens_details") or {}
    usage = Usage(
        prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
        completion_tokens=int(raw_usage.get("completion_tokens") or 0),
        reasoning_tokens=int(completion_details.get("reasoning_tokens") or 0),
        cached_tokens=int((raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
    )

    # 推理模型的典型陷阱：token 全花在思考上，content 是空的
    if not content and finish == "length":
        raise LlmError(
            f"回答被 max_tokens 截断且内容为空（推理占用了约 {usage.reasoning_tokens} 个 token）。"
            f"请调大 max_tokens（当前上限 {usage.completion_tokens}）。",
            status="truncated",
        )
    return LlmResult(content=content, reasoning=reasoning, model=model,
                     finish_reason=finish, usage=usage, elapsed_ms=elapsed_ms, attempts=attempt)
