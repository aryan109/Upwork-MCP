"""Read-only Railway probe used on 2026-10-10 to diagnose the blind runner.

Modes:
  python scripts/railway_probe.py probe                       # auth check, services, environments, volumes
  python scripts/railway_probe.py details                     # deployments, service settings, variable NAMES
  python scripts/railway_probe.py logs <deployment_id> [n]    # runtime logs (default 5000 lines) -> jsonl

Output goes to %USERPROFILE%\\upwork_engine\\cloud_backup\\railway. Secret values are never printed.
Starting point for RailwayProvider in cloud_backup.py (see RESILIENCE_ANALYSIS_AND_PLAN.md, Part E).
"""
import json
import os
import sys
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = {}
for line in open(os.path.join(REPO_ROOT, ".env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip().strip("'\"")

TOKEN = ENV["RAILWAY_TOKEN"]          # project access token (sent as Project-Access-Token header)
PROJECT = ENV["RAILWAY_PROJECT_ID"]
URL = "https://backboard.railway.app/graphql/v2"
SERVICE_ID = "d35fc7d1-1790-451b-b554-fa900ff4778b"      # upwork-engine
ENV_ID = "7b03e4ad-2c8a-4325-b699-0085b1355009"          # production
OUT_DIR = os.path.join(os.environ.get("USERPROFILE", ""), "upwork_engine", "cloud_backup", "railway")
os.makedirs(OUT_DIR, exist_ok=True)


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    hdrs = {
        "Content-Type": "application/json",
        # Cloudflare rejects the default urllib user agent (error 1010)
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) upwork-engine-probe",
        "Project-Access-Token": TOKEN,
    }
    req = urllib.request.Request(URL, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:500]}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"

    if mode == "probe":
        r = gql(
            "query($id:String!){ project(id:$id){ id name services{edges{node{id name}}} "
            "environments{edges{node{id name}}} volumes{edges{node{id name volumeInstances{edges{node{"
            "id mountPath sizeMB currentSizeMB serviceId environmentId}}}}}} } }",
            {"id": PROJECT},
        )
        print(json.dumps(r, indent=2)[:3000])

    elif mode == "details":
        r = gql(
            "query($p:String!,$s:String!,$e:String!){ deployments(first:30,input:{projectId:$p,serviceId:$s,"
            "environmentId:$e}){edges{node{id status createdAt staticUrl meta}}} }",
            {"p": PROJECT, "s": SERVICE_ID, "e": ENV_ID},
        )
        deps = [ed["node"] for ed in ((r.get("data") or {}).get("deployments") or {}).get("edges", [])]
        for n in deps:
            meta = n.get("meta") or {}
            print("DEPLOY", n["createdAt"], n["status"], n["id"], "commit:", str(meta.get("commitHash", ""))[:8])
        if "errors" in r:
            print("deployments errors:", r["errors"])
        json.dump(deps, open(os.path.join(OUT_DIR, "deployments.json"), "w"), indent=2)

        r = gql(
            "query($s:String!){ service(id:$s){ name serviceInstances{edges{node{environmentId healthcheckPath "
            "healthcheckTimeout restartPolicyType restartPolicyMaxRetries startCommand numReplicas region "
            "sleepApplication domains{serviceDomains{domain} customDomains{domain}} }}} } }",
            {"s": SERVICE_ID},
        )
        print("SERVICE", json.dumps(r)[:1500])
        json.dump(r, open(os.path.join(OUT_DIR, "service.json"), "w"), indent=2)

        r = gql(
            "query($p:String!,$s:String!,$e:String!){ variables(projectId:$p,serviceId:$s,environmentId:$e) }",
            {"p": PROJECT, "s": SERVICE_ID, "e": ENV_ID},
        )
        v = (r.get("data") or {}).get("variables") or {}
        names = sorted(v.keys()) if isinstance(v, dict) else r
        print("VARIABLE NAMES:", names)
        json.dump({"variable_names": names}, open(os.path.join(OUT_DIR, "variable_names.json"), "w"), indent=2)

    elif mode == "logs":
        dep_id = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
        r = gql(
            "query($d:String!,$l:Int!){ deploymentLogs(deploymentId:$d,limit:$l){ timestamp severity message } }",
            {"d": dep_id, "l": limit},
        )
        logs = (r.get("data") or {}).get("deploymentLogs")
        if logs is None:
            print("ERR", json.dumps(r)[:800])
            sys.exit(1)
        out = os.path.join(OUT_DIR, f"logs_{dep_id[:8]}.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for entry in logs:
                f.write(json.dumps(entry) + "\n")
        print("saved", len(logs), "lines ->", out)
        if logs:
            print("range:", logs[0]["timestamp"], "->", logs[-1]["timestamp"])

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
