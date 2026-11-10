#!/usr/bin/env python3
"""Read-only health/auth/HTML/SSE checks. No model calls; no credentials printed."""
import argparse, base64, http.cookiejar, json, pathlib, ssl, time, urllib.error, urllib.parse, urllib.request
from credentials import read_env
VERSION="2.2.1"
parser=argparse.ArgumentParser();parser.add_argument("--internal",action="store_true");parser.add_argument("--port",type=int,required=True);args=parser.parse_args()
values=read_env("/etc/opencode/server.env")
# The opencode v2 server accepts only its fixed user "opencode"; the public gate accepts the deployment login too.
login=base64.b64encode((values["OPENCODE_SERVER_USERNAME"]+":"+values["OPENCODE_SERVER_PASSWORD"]).encode()).decode()
token=base64.b64encode(("opencode:"+values["OPENCODE_SERVER_PASSWORD"]).encode()).decode() if args.internal else login
origin=("http" if args.internal else "https")+"://127.0.0.1:"+str(args.port)
context=ssl._create_unverified_context() if not args.internal else None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
def get(path,auth=True):
    request=urllib.request.Request(origin+path,headers={"Authorization":"Basic "+token} if auth else {})
    return opener.open(request,timeout=8)
for attempt in range(40):
    try:
        with get("/api/info") as response:
            health=json.load(response)
            if health.get("version") == VERSION:break
    except (OSError, ValueError):time.sleep(0.5)
else:raise SystemExit("Authenticated health check failed; secrets not logged")
if not args.internal:
    try:
        get("/api/info",False)
        raise SystemExit("Unauthenticated API unexpectedly accessible")
    except urllib.error.HTTPError as error:
        if error.code!=401:raise SystemExit("Expected API HTTP 401")
    with get("/",False) as response:
        if b'form action="/login"' not in response.read():raise SystemExit("Login page missing")
    with get("/") as response:
        if b"<!doctype html" not in response.read().lower():raise SystemExit("Frontend HTML missing")
    with get("/api/event") as response:
        if "text/event-stream" not in response.headers.get("Content-Type", ""):raise SystemExit("SSE unavailable")
        if not response.readline():raise SystemExit("SSE initial event missing")
    jar=http.cookiejar.CookieJar()
    browser=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context),urllib.request.HTTPCookieProcessor(jar))
    data=urllib.parse.urlencode({"username":values["OPENCODE_SERVER_USERNAME"],"password":values["OPENCODE_SERVER_PASSWORD"],"next":"/"}).encode()
    with browser.open(urllib.request.Request(origin+"/login",data=data),timeout=8) as response:
        if response.status!=200:raise SystemExit("Cookie login failed")
    cookies=list(jar)
    if len(cookies)!=1 or not cookies[0].secure or cookies[0].expires-time.time()<31535000:raise SystemExit("Persistent secure cookie missing")
    with browser.open(origin+"/api/info",timeout=8) as response:
        if json.load(response).get("version")!=VERSION:raise SystemExit("Cookie-only health failed")
    with browser.open(origin+"/api/event",timeout=8) as response:
        if not response.readline():raise SystemExit("Cookie-only SSE failed")
    with browser.open(urllib.request.Request(origin+"/logout",data=b""),timeout=8) as response:response.read()
print("Authenticated health"+(" + HTTPS/login-cookie/401/HTML/SSE" if not args.internal else "")+" passed; no generation.")
