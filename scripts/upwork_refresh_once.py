import json, os, shutil, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
HOME=os.environ["USERPROFILE"]
TOK=os.path.join(HOME,".gemini","antigravity","mcp_oauth_tokens.json")
BK_DIR=os.path.join(HOME,"upwork_engine","backup"); os.makedirs(BK_DIR,exist_ok=True)
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
bk=os.path.join(BK_DIR,f"mcp_oauth_tokens.before_refresh.{stamp}.json")
shutil.copy2(TOK,bk); print("backup written:",bk)
d=json.load(open(TOK,encoding="utf-8"))
key="https://mcp.upwork.com/mcp"; e=d[key]; t=e["token"]
old_rt=t.get("refresh_token",""); old_at=t.get("access_token","")
print("token_url:",e.get("token_url")); print("client_id length:",len(e.get("client_id",""))); print("has client_secret:", "client_secret" in e)
print("old expiry:",t.get("expiry"))
form={"grant_type":"refresh_token","refresh_token":old_rt,"client_id":e["client_id"]}
if e.get("client_secret"): form["client_secret"]=e["client_secret"]
body=urllib.parse.urlencode(form).encode()
req=urllib.request.Request(e["token_url"],data=body,headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json","User-Agent":"Antigravity/1.0 (Windows)"},method="POST")
try:
    with urllib.request.urlopen(req,timeout=30) as r:
        status=r.status; resp=json.loads(r.read().decode())
except urllib.error.HTTPError as err:
    print("REFRESH FAILED HTTP",err.code,err.read().decode()[:400]); sys.exit(1)
print("HTTP",status,"response keys:",sorted(resp.keys()))
new_at=resp.get("access_token"); new_rt=resp.get("refresh_token"); exp_in=resp.get("expires_in")
print("expires_in:",exp_in,"token_type:",resp.get("token_type"),"scope:",resp.get("scope"))
print("access_token changed:", bool(new_at) and new_at!=old_at, "| new access length:", len(new_at or ""))
print("refresh_token present:", bool(new_rt), "| ROTATED:", bool(new_rt) and new_rt!=old_rt)
if not new_at: print("no access token in response; file untouched"); sys.exit(1)
# write back so the IDE keeps a valid chain
ist=timezone(timedelta(hours=5,minutes=30))
exp_dt=datetime.now(ist)+timedelta(seconds=int(exp_in or 3600))
t["access_token"]=new_at
if new_rt: t["refresh_token"]=new_rt
t["expiry"]=exp_dt.strftime("%Y-%m-%dT%H:%M:%S.%f0+05:30")
if resp.get("token_type"): t["token_type"]=resp["token_type"]
tmp=TOK+".tmp"
json.dump(d,open(tmp,"w",encoding="utf-8"),indent=2); os.replace(tmp,TOK)
print("IDE token file updated; new expiry:",t["expiry"])
# verify with a read-only MCP call
sys.path.insert(0,r"E:\Ventures\Upwork MCP")
from aryan_implementation.engine.mcp_client import UpworkMCPClient
c=UpworkMCPClient(auth_token=new_at)
res=c.call_raw("list_accounts",{})
accs=res.get("accounts",res) if isinstance(res,dict) else res
try:
    names=[(a.get("name"),a.get("type")) for a in accs] if isinstance(accs,list) else str(accs)[:200]
except Exception: names=str(accs)[:200]
print("list_accounts with refreshed token ->",names)
