#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 build/dsh_fish 增量部署到 HoloCubic 设备（用 --host 或改 HOST）。

设备接口（实测）：
  * 建目录：POST http://HOST/devtools/api/mkdir?path=<urlencoded>
  * 传文件：PUT  http://HOST/api/system/fs/upload?path=<urlencoded>   注意不带 /devtools 前缀
  * 重启应用：POST /api/system/exit  +  POST /api/system/launch?id=dsh_fish

用法：
    python tools/deploy_app.py            # 全量
    python tools/deploy_app.py main.lua   # 只传指定相对路径（可多个）
"""

from __future__ import annotations

import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HOST = "192.168.1.100"
APP_ID = "dsh_fish"
REMOTE_ROOT = "/sd/apps/" + APP_ID
LOCAL_ROOT = Path(__file__).resolve().parent.parent / "build" / APP_ID
TIMEOUT = 20


def http(method: str, url: str, body: bytes | None = None) -> str:
    req = urllib.request.Request(url, data=body, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


def mkdir(remote_dir: str) -> None:
    url = "http://%s/devtools/api/mkdir?path=%s" % (HOST, urllib.parse.quote(remote_dir, safe=""))
    try:
        http("POST", url)
    except Exception as exc:  # 已存在时设备可能返回非 200
        print("  mkdir %s -> %s" % (remote_dir, exc))


def upload(local: Path, remote: str) -> None:
    data = local.read_bytes()
    url = "http://%s/api/system/fs/upload?path=%s" % (HOST, urllib.parse.quote(remote, safe=""))
    last: Exception | None = None
    for attempt in range(4):
        try:
            http("PUT", url, data)
            return
        except Exception as exc:
            last = exc
            time.sleep(0.5 + attempt * 0.8)
    raise last if last else RuntimeError("upload failed")


def main() -> int:
    if not LOCAL_ROOT.is_dir():
        raise SystemExit("找不到本地目录: %s" % LOCAL_ROOT)

    only = sys.argv[1:]
    files = sorted(p for p in LOCAL_ROOT.rglob("*") if p.is_file())
    if only:
        def hit(rel: str) -> bool:
            for o in only:
                key = o.replace("\\", "/").rstrip("/")
                if rel == key or rel.startswith(key + "/"):
                    return True
            return False

        files = [p for p in files if hit(str(p.relative_to(LOCAL_ROOT)).replace("\\", "/"))]
        if not files:
            raise SystemExit("没有匹配的文件")

    dirs = sorted({str(p.relative_to(LOCAL_ROOT).parent).replace("\\", "/") for p in files})
    for rel in dirs:
        remote = REMOTE_ROOT if rel == "." else REMOTE_ROOT + "/" + rel
        mkdir(remote)

    ok = fail = 0
    started = time.time()
    for i, path in enumerate(files, 1):
        rel = str(path.relative_to(LOCAL_ROOT)).replace("\\", "/")
        try:
            upload(path, REMOTE_ROOT + "/" + rel)
            ok += 1
            print("[%d/%d] OK   %-46s %6.1f KB" % (i, len(files), rel, path.stat().st_size / 1024.0))
        except Exception as exc:
            fail += 1
            print("[%d/%d] FAIL %-46s %s" % (i, len(files), rel, exc))

    print("\n上传完成：成功 %d，失败 %d，用时 %.1fs" % (ok, fail, time.time() - started))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
