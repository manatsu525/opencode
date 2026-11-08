#!/usr/bin/env python3
"""Read-only health/auth/HTML/SSE checks. No model calls; no credentials printed."""
import argparse, base64, json, pathlib, ssl, time, urllib.error, urllib.request
parser=argparse.ArgumentParser();parser.add_argument("--internal",action="store_true");parser.add_argument("--port",type=int,required=True);args=parser.parse_args()
values=dict(line.split("=",1) for line in pathlib.Path("/etc/opencode/server.env").read_text().splitlines() if "=" in line and not line.startswith("#"))
token=base64.b64encode((values["OPENCODE_SERVER_USERNAME"]+":"+values["OPENCODE_SERVER_PASSWORD"]).encode()).decode()
origin=("http" if args.internal else "https")+"://127.0.0.1:"+str(args.port)
context=ssl._create_unverified_context() if not args.internal else None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
def get(path,auth=True):
    request=urllib.request.Request(origin+path,headers={"Authorization":"Basic "+token} if auth else {})
    return opener.open(request,timeout=8)
for attempt in range(40):
    try:
        with get("/global/health") as response:
            health=json.load(response)
            if health.get("healthy") is True:break
    except (OSError, ValueError):time.sleep(0.5)
else:raise SystemExit("Authenticated health check failed; secrets not logged")
if not args.internal:
    try:
        get("/",False)
        raise SystemExit("Unauthenticated frontend unexpectedly accessible")
    except urllib.error.HTTPError as error:
        if error.code!=401:raise SystemExit("Expected HTTP 401")
    with get("/") as response:
        if b"<!doctype html" not in response.read().lower():raise SystemExit("Frontend HTML missing")
    with get("/global/event") as response:
        if "text/event-stream" not in response.headers.get("Content-Type", ""):raise SystemExit("SSE unavailable")
        if not response.readline():raise SystemExit("SSE initial event missing")
print("Authenticated health"+(" + HTTPS/401/HTML/SSE" if not args.internal else "")+" passed; no generation.")
