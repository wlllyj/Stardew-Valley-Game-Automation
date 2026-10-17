r"""只读：跑 scratch\_t211_api 的反射探针，把输出按 UTF-8 落盘。

用法：
  dotnet build scratch\_t211_api\T211Api.csproj -c Release
  python scratch\_t211_api_run.py scratch\t211-api-out.txt
"""
import os
import subprocess
import sys

EXE = os.path.join("scratch", "_t211_api", "bin", "Release", "net6.0", "T211Api.exe")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = sys.argv[1]
    proc = subprocess.run([EXE], capture_output=True)
    text = proc.stdout.decode("utf-8", "replace")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("rc=%d bytes=%d lines=%d -> %s" % (proc.returncode, len(proc.stdout), text.count("\n"), out))
    if proc.stderr:
        print("stderr:", proc.stderr.decode("utf-8", "replace")[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
