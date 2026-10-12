"""只读运行器：跑带连字符的脚本并把 stdout 以 UTF-8 落盘（避免 pwsh 重定向写出 UTF-16）。

用法: python scratch\\_reh_run.py <脚本路径> <输出txt> [脚本参数...]
"""
import io
import pathlib
import runpy
import sys

target = sys.argv[1]
out = sys.argv[2]
sys.argv = [target] + sys.argv[3:]

raw = io.BytesIO()
buf = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
old = sys.stdout
sys.stdout = buf
rc = 0
try:
    runpy.run_path(target, run_name="__main__")
except SystemExit as exc:  # noqa: PERF203
    code = exc.code
    rc = code if isinstance(code, int) else (0 if code is None else 1)
finally:
    buf.flush()
    sys.stdout = old

text = raw.getvalue().decode("utf-8", errors="replace")
pathlib.Path(out).write_text(text, encoding="utf-8")
print(f"{target} -> {out} rc={rc} chars={len(text)}")
