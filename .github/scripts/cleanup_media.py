#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""threads-media 暫存檔清理（2026-10-24）

規則
1. img/YYYY-MM-DD/xxx  → 用資料夾日期
2. img/bd|qi/MMDD_xxxx.jpg → 用檔名前 4 碼（MMDD，預設今年）
3. vid/YYYY-MM-DD/xxx → 用資料夾日期
4. 解析不到日期 → 不動（安全優先）
5. 檔名出現在 keep.txt → 永不刪
6. 只刪「超過 DAYS 天」的檔

環境變數：GH_TOKEN / REPO / DAYS / DRY
"""
import base64
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ["REPO"]
DAYS = int(os.environ.get("DAYS") or 7)
DRY = (os.environ.get("DRY") or "false").lower() == "true"
API = "https://api.github.com"


def call(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"__error": e.code, "__body": e.read().decode("utf-8", "replace")[:200]}


def keep_names():
    r = call("GET", f"/repos/{REPO}/contents/keep.txt")
    if "__error" in r or "content" not in r:
        return set()
    txt = base64.b64decode(r["content"]).decode("utf-8", "replace")
    out = set()
    for line in txt.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(os.path.basename(line))
    return out


def file_date(path):
    """回傳 date 或 None（解析不到）"""
    parts = path.split("/")
    for p in parts:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", p)
        if m:
            try:
                return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    base = parts[-1]
    m = re.match(r"^(\d{2})(\d{2})_", base)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        today = dt.date.today()
        for year in (today.year, today.year - 1):
            try:
                d = dt.date(year, mm, dd)
            except ValueError:
                continue
            if d <= today:
                return d
    return None


def walk(path=""):
    r = call("GET", f"/repos/{REPO}/contents/{path}")
    if isinstance(r, dict) and "__error" in r:
        return []
    out = []
    for x in r if isinstance(r, list) else []:
        if x["type"] == "dir":
            out += walk(x["path"])
        elif x["type"] == "file":
            out.append(x)
    return out


def main():
    keep = keep_names()
    cutoff = dt.date.today() - dt.timedelta(days=DAYS)
    files = [f for f in walk() if f["path"].startswith(("img/", "vid/"))]
    dead = []
    for f in files:
        if os.path.basename(f["path"]) in keep:
            continue
        d = file_date(f["path"])
        if d is None:
            continue
        if d < cutoff:
            dead.append(f)
    total = sum(f.get("size", 0) for f in dead) / 1024 / 1024
    print(f"掃描 {len(files)} 檔｜超過 {DAYS} 天 ({cutoff} 之前) 命中 {len(dead)} 檔，共 {total:.1f}MB")
    for f in dead:
        print("  -", f["path"])
        if DRY:
            continue
        r = call("DELETE", f"/repos/{REPO}/contents/{f['path']}",
                 {"message": f"chore: 清理過期暫存 {f['path']}", "sha": f["sha"]})
        if "__error" in r:
            print("    ❌ 刪除失敗", r["__error"], r.get("__body", ""))
        else:
            print("    ✅ 已刪")


if __name__ == "__main__":
    main()
