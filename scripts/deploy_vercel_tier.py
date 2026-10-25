"""
Create/deploy the Vercel standby project and set environment variable NAMES only
in logs. Secret values are never printed.

Requires VERCEL_PERSONAL_ACCESS_TOKEN and STATE_REPO in repo .env.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV: dict = {}
for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip().strip("'\"")

TOKEN = ENV.get("VERCEL_PERSONAL_ACCESS_TOKEN") or os.environ.get("VERCEL_PERSONAL_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("VERCEL_PERSONAL_ACCESS_TOKEN missing")

PROJECT_NAME = "upwork-engine"
API = "https://api.vercel.com"


def api(method: str, path: str, body=None, timeout=60):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "upwork-engine-deploy/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw[:500]}
        return e.code, parsed


def main():
    status, me = api("GET", "/v2/user")
    if status != 200:
        print("auth failed", status, list(me.keys()) if isinstance(me, dict) else me)
        sys.exit(1)
    user = (me.get("user") or me)
    uid = user.get("id") or user.get("uid")
    print("vercel user ok", bool(uid))

    status, projects = api("GET", f"/v9/projects?limit=50")
    existing = None
    for p in (projects.get("projects") or []):
        if p.get("name") == PROJECT_NAME:
            existing = p
            break
    if existing:
        print("project exists", PROJECT_NAME, existing.get("id"))
        project_id = existing["id"]
    else:
        status, created = api("POST", "/v10/projects", {
            "name": PROJECT_NAME,
            "framework": None,
        })
        print("create project", status, created.get("id") or created.get("error") or list(created.keys())[:6])
        if status not in (200, 201):
            sys.exit(1)
        project_id = created["id"]

    env_pairs = {
        "ENGINE_TIER": "vercel",
        "UPWORK_ENGINE_DIR": "/tmp/upwork_engine",
        "STATE_REPO": ENV.get("STATE_REPO", ""),
        "STATE_REPO_TOKEN": ENV.get("STATE_REPO_TOKEN") or ENV.get("GITHUB_PERSONAL_ACCESS_TOKEN", ""),
        "TICK_SECRET": ENV.get("TICK_SECRET", ""),
        "CRON_SECRET": ENV.get("TICK_SECRET", ""),
        "TELEGRAM_BOT_TOKEN": ENV.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": ENV.get("TELEGRAM_CHAT_ID", ""),
        "GROQ_API_KEY": ENV.get("GROQ_API_KEY", ""),
        "GOOGLE_STUDIO_API_KEY": ENV.get("GOOGLE_STUDIO_API_KEY", ""),
        "NOTION_API_KEY": ENV.get("NOTION_API_KEY", ""),
        "TICK_TIME_BUDGET_S": "45",
    }
    print("upserting env keys:", sorted(k for k, v in env_pairs.items() if v))
    for key, val in env_pairs.items():
        if not val:
            print("skip empty", key)
            continue
        # delete existing then create for production/preview/development
        api("POST", f"/v10/projects/{project_id}/env", {
            "key": key,
            "value": val,
            "type": "encrypted",
            "target": ["production", "preview", "development"],
            "upsert": True,
        })

    print("invoking vercel deploy (npx)...")
    import shutil
    npx_bin = shutil.which("npx") or "npx.cmd"
    env = os.environ.copy()
    env["VERCEL_ORG_ID"] = uid or ""
    env["VERCEL_PROJECT_ID"] = project_id
    proc = subprocess.run(
        [
            npx_bin, "--yes", "vercel@latest",
            "--token", TOKEN,
            "--yes",
            "--prod",
            "--name", PROJECT_NAME,
        ],
        cwd=str(REPO),
        env=env,
        text=True,
    )
    print("npx vercel exit", proc.returncode)
    status, proj = api("GET", f"/v9/projects/{PROJECT_NAME}")
    aliases = []
    if status == 200:
        print("project targets", list((proj.get("targets") or {}).keys()))
        aliases = [t.get("url") for t in (proj.get("alias") or []) if isinstance(t, dict)]
        prod = ((proj.get("targets") or {}).get("production") or {})
        print("production url host", (prod.get("url") or "")[:80])
        print("aliases count", len(proj.get("alias") or []))
        with open(REPO / "scripts" / ".vercel_project_meta.json", "w", encoding="utf-8") as f:
            json.dump({
                "project_id": project_id,
                "name": PROJECT_NAME,
                "production_url": prod.get("url"),
                "alias": proj.get("alias"),
            }, f, indent=2)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
