#!/usr/bin/env python3
"""Shared headless Chromium for image search fallback, with a human captcha relay.

One process for every opencode backend (127.0.0.1:4098). Playwright's sync API lives on one worker
thread; HTTP handlers hand it jobs through a queue. The browser profile (cookies, e.g. a solved Google
captcha) persists on disk; the browser closes after idling and reopens on demand.

Internal API (loopback only, used by image_search.py):
  POST /search {"query":..,"count":..}  -> {"status":"ok","results":[...]} | {"status":"captcha"} | {"status":"error"}
Relay (behind the 8558 login gate, nginx location /imgcaptcha/):
  GET  /imgcaptcha/            page that mirrors the browser and forwards taps/keys
  GET  /imgcaptcha/shot        current screenshot (PNG)
  GET  /imgcaptcha/state       {"pending":bool,"solved":bool}
  POST /imgcaptcha/act         {"type":"click","x":..,"y":..} | {"type":"text","text":..} | {"type":"key","key":..}
"""
import json,os,queue,re,threading,time,urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

PORT=int(os.environ.get('IMGBROWSER_PORT','4098'))
PROFILE=os.environ.get('IMGBROWSER_PROFILE','/var/lib/opencode-imgbrowser/profile')
PROXY=os.environ.get('IMGBROWSER_PROXY','socks5://127.0.0.1:40000')
IDLE=int(os.environ.get('IMGBROWSER_IDLE','900'))
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
VIEW={'width':412,'height':860}
jobs=queue.Queue()
state={'pending':False,'solved_at':0.0,'last_used':0.0}

def blocked(url):return '/sorry/' in url or 'google.com/sorry' in url

GOOGLE_ITEM=re.compile(r'\[0,"([A-Za-z0-9_-]{8,40})",\["https://encrypted-tbn[^"]*",\d+,\d+\],\["(https?://[^"]+)",(\d+),(\d+)\]')
GOOGLE_META=re.compile(r'"2003":\[null,"[^"]*","(https?://[^"]+)","((?:[^"\\]|\\.)*)"')
def unjs(text):
    try:return json.loads('"'+text+'"')
    except Exception:return text
def parse_google(html,count):
    """Image results from the udm=2 page's inline data: docid, thumbnail, original [url,h,w], then metadata."""
    out=[];seen=set()
    for m in GOOGLE_ITEM.finditer(html):
        url=unjs(m.group(2))
        if url in seen:continue
        seen.add(url);meta=GOOGLE_META.search(html,m.end(),m.end()+3000)
        out.append({'title':unjs(meta.group(2))[:250] if meta else '','original_url':url,'source_url':unjs(meta.group(1)) if meta else '','width':int(m.group(4)),'height':int(m.group(3))})
        if len(out)>=count:break
    return out

SOGOU_ITEM=re.compile(r'"title":"((?:[^"\\]|\\.)*)","name":"[^"]*","oriPicUrl":"((?:[^"\\]|\\.)+)".{0,600}?"url":"((?:[^"\\]|\\.)*)"',re.S)
def clean(rows,count):
    out=[];seen=set()
    for r in rows:
        url=str(r.get('original_url') or '')
        if not url.startswith(('https://','http://')) or url in seen:continue
        seen.add(url);out.append({'title':str(r.get('title') or '')[:250],'original_url':url,'source_url':str(r.get('source_url') or '')[:4096]})
        if len(out)>=count:break
    return out
def parse_sogou(html,count):
    return clean([{'title':unjs(m.group(1)),'original_url':unjs(m.group(2)),'source_url':unjs(m.group(3))} for m in SOGOU_ITEM.finditer(html)],count)

class Worker(threading.Thread):
    daemon=True
    def __init__(self):super().__init__();self.pw=None;self.ctx=None;self.cap=None
    def ensure(self):
        if self.ctx:return
        from playwright.sync_api import sync_playwright
        self.pw=sync_playwright().start()
        opts=dict(headless=True,user_agent=UA,locale='zh-CN',viewport=VIEW,device_scale_factor=2,is_mobile=False,args=['--no-sandbox','--disable-blink-features=AutomationControlled','--disable-dev-shm-usage'])
        if PROXY:opts['proxy']={'server':PROXY}
        os.makedirs(PROFILE,mode=0o700,exist_ok=True)
        self.ctx=self.pw.chromium.launch_persistent_context(PROFILE,**opts)
        self.ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    def close(self):
        try:
            if self.ctx:self.ctx.close()
            if self.pw:self.pw.stop()
        except Exception:pass
        self.pw=self.ctx=self.cap=None
    def run(self):
        while True:
            try:job=jobs.get(timeout=30)
            except queue.Empty:
                if self.ctx and not state['pending'] and time.time()-state['last_used']>IDLE:self.close()
                continue
            fn,args,box,done=job
            try:box['value']=getattr(self,fn)(*args)
            except Exception as e:
                box['error']=type(e).__name__+': '+str(e)[:200]
                if fn=='search' and not state['pending']:self.close()
            finally:
                state['last_used']=time.time();done.set()
    # --- jobs (run on the worker thread only) ---
    def search(self,query,count,days=None,engine='google'):
        self.ensure()
        if engine!='google':return getattr(self,'search_'+engine)(query,count)
        if state['pending'] and self.cap and not blocked(self.cap.url):self.finish_captcha()
        if state['pending']:return {'status':'captcha'}
        page=self.ctx.new_page()
        try:
            page.goto('https://www.google.com/search?udm=2&hl=zh-CN&q='+urllib.parse.quote(query)+({1:'&tbs=qdr:d',7:'&tbs=qdr:w',30:'&tbs=qdr:m',365:'&tbs=qdr:y'}.get(days,'')),wait_until='domcontentloaded',timeout=30000)
            if blocked(page.url):
                self.cap=page;page=None;state['pending']=True;return {'status':'captcha'}
            page.wait_for_timeout(1200)
            return {'status':'ok','results':parse_google(page.content(),count*3)}
        finally:
            if page:page.close()
    def search_sogou(self,query,count):
        page=self.ctx.new_page()
        try:
            page.goto('https://pic.sogou.com/pics?query='+urllib.parse.quote(query),wait_until='domcontentloaded',timeout=25000)
            page.wait_for_timeout(1500)
            if 'antispider' in page.url:return {'status':'blocked'}
            return {'status':'ok','results':parse_sogou(page.content(),count*3)}
        finally:page.close()
    def search_yahoo(self,query,count):
        page=self.ctx.new_page()
        try:
            page.goto('https://images.search.yahoo.com/search/images?p='+urllib.parse.quote(query),wait_until='domcontentloaded',timeout=25000)
            page.wait_for_timeout(1500)
            rows=page.eval_on_selector_all('a[data-origurl]',"""e=>e.map(a=>{const i=a.querySelector('img');return {original_url:a.getAttribute('data-origurl')||'',source_url:a.getAttribute('data-referenceurl')||'',title:((i&&i.alt)||a.getAttribute('aria-label')||a.innerText||'').trim()}})""")
            return {'status':'ok','results':clean(rows,count*3)}
        finally:page.close()
    def search_ddg(self,query,count):
        page=self.ctx.new_page();found=[]
        def grab(response):
            if '/i.js' in response.url and response.status==200:
                try:found.extend(response.json().get('results',[]))
                except Exception:pass
        page.on('response',grab)
        try:
            page.goto('https://duckduckgo.com/?ia=images&iax=images&q='+urllib.parse.quote(query),wait_until='domcontentloaded',timeout=25000)
            if 'home-error' in page.url or '/418' in page.url:return {'status':'blocked'}
            page.wait_for_timeout(2500)
            return {'status':'ok','results':clean([{'original_url':r.get('image',''),'source_url':r.get('url',''),'title':r.get('title','')} for r in found],count*3)}
        finally:page.close()
    def finish_captcha(self):
        state['pending']=False;state['solved_at']=time.time()
        try:self.cap.close()
        except Exception:pass
        self.cap=None
    def shot(self):
        if not (state['pending'] and self.cap):return None
        if not blocked(self.cap.url):self.finish_captcha();return None
        return self.cap.screenshot(type='png')
    def act(self,data):
        if not (state['pending'] and self.cap):return False
        kind=data.get('type')
        if kind=='click':
            x=float(data.get('x',0));y=float(data.get('y',0))
            if not (0<=x<=VIEW['width'] and 0<=y<=VIEW['height']):raise ValueError('out of view')
            self.cap.mouse.click(x,y)
        elif kind=='text':
            text=str(data.get('text',''))[:200];self.cap.keyboard.type(text,delay=40)
        elif kind=='key':
            key=str(data.get('key',''))
            if key not in ('Enter','Backspace','Tab','Escape'):raise ValueError('key')
            self.cap.keyboard.press(key)
        elif kind=='reload':self.cap.reload(wait_until='domcontentloaded')
        else:raise ValueError('type')
        self.cap.wait_for_timeout(600)
        if not blocked(self.cap.url):self.finish_captcha()
        return True

def call(fn,*args,timeout=110):
    box={};done=threading.Event();jobs.put((fn,args,box,done))
    if not done.wait(timeout):return {'error':'timeout'}
    return box

PAGE='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>搜图人工验证</title><style>body{margin:0;font:15px -apple-system,system-ui,sans-serif;background:#111;color:#eee}
header{padding:10px 12px}#s{font-size:13px;color:#aaa}#wrap{position:relative;max-width:412px;margin:0 auto}
img{width:100%;display:block;touch-action:manipulation;background:#222}form{display:flex;gap:6px;padding:8px 12px;max-width:412px;margin:0 auto}
input{flex:1;padding:8px;font-size:16px;border-radius:6px;border:1px solid #444;background:#222;color:#eee}button{padding:8px 12px;font-size:15px;border-radius:6px;border:0;background:#3b82f6;color:#fff}
.k{background:#333}#ok{display:none;padding:24px 12px;font-size:17px;text-align:center}</style></head><body>
<header><b>搜图需要人工验证</b><div id="s">点画面里的验证框；图片题直接点格子。画面每秒刷新。</div></header>
<div id="ok">✅ 验证已通过，可以关掉这页，回到对话让它重试搜图。</div>
<div id="wrap"><img id="v" alt="浏览器画面"></div>
<form id="f"><input id="t" placeholder="需要输入文字时在这里输入" autocomplete="off"><button>输入</button></form>
<form><button type="button" class="k" data-k="Enter">回车</button><button type="button" class="k" data-k="Backspace">退格</button><button type="button" class="k" data-r="1">刷新验证页</button></form>
<script>
const W=412,H=860,v=document.getElementById('v');let busy=false;
async function act(d){if(busy)return;busy=true;try{await fetch('act',{method:'POST',headers:{'Content-Type':'application/json','X-Imgcaptcha':'1'},body:JSON.stringify(d)})}finally{busy=false;tick()}}
v.addEventListener('click',e=>{const r=v.getBoundingClientRect();act({type:'click',x:(e.clientX-r.left)*W/r.width,y:(e.clientY-r.top)*H/r.height})});
document.getElementById('f').addEventListener('submit',e=>{e.preventDefault();const t=document.getElementById('t');act({type:'text',text:t.value});t.value=''});
document.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>act({type:'key',key:b.dataset.k}));
document.querySelector('[data-r]').onclick=()=>act({type:'reload'});
async function tick(){try{const s=await (await fetch('state',{cache:'no-store'})).json();
 if(!s.pending){document.getElementById('ok').style.display='block';document.getElementById('wrap').style.display='none';document.querySelectorAll('form').forEach(f=>f.style.display='none');
  document.getElementById('s').textContent=s.solved?'':'当前没有待处理的验证。';return}
 const u=URL.createObjectURL(await (await fetch('shot?'+Date.now(),{cache:'no-store'})).blob());const o=v.src;v.src=u;if(o)URL.revokeObjectURL(o)}catch(e){}}
tick();setInterval(()=>{if(!busy)tick()},1000);
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    server_version='imgbrowser'
    def log_message(self,*a):pass
    def send(self,code,body,ctype='application/json'):
        if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode()
        elif isinstance(body,str):body=body.encode()
        self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def body(self):
        n=int(self.headers.get('Content-Length') or 0)
        if n>8192:raise ValueError('too large')
        return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        path=urllib.parse.urlsplit(self.path).path
        if path=='/imgcaptcha/':return self.send(200,PAGE,'text/html; charset=utf-8')
        if path=='/imgcaptcha/state':return self.send(200,{'pending':state['pending'],'solved':time.time()-state['solved_at']<600})
        if path=='/imgcaptcha/shot':
            r=call('shot',timeout=20);png=r.get('value')
            return self.send(200,png,'image/png') if png else self.send(204,b'','text/plain')
        if path=='/health':return self.send(200,{'ok':True,'pending':state['pending']})
        self.send(404,{'error':'not found'})
    def do_POST(self):
        path=urllib.parse.urlsplit(self.path).path
        try:data=self.body()
        except Exception:return self.send(400,{'error':'bad request'})
        if path=='/search':
            # Internal only: nginx never forwards /search (it only maps /imgcaptcha/).
            if self.headers.get('X-Forwarded-For') or self.client_address[0] not in ('127.0.0.1','::1'):return self.send(403,{'error':'forbidden'})
            q=data.get('query');c=data.get('count',4)
            if not isinstance(q,str) or not q.strip() or len(q)>300 or not isinstance(c,int) or not 1<=c<=8:return self.send(400,{'error':'bad query'})
            d=data.get('days');engine=data.get('engine','google')
            if d not in (None,1,7,30,365) or engine not in ('google','sogou','yahoo','ddg'):return self.send(400,{'error':'bad request'})
            r=call('search',q,c,d,engine)
            if 'error' in r:return self.send(200,{'status':'error','error':r['error']})
            return self.send(200,r['value'])
        if path=='/imgcaptcha/act':
            if self.headers.get('X-Imgcaptcha')!='1':return self.send(403,{'error':'forbidden'})
            r=call('act',data,timeout=30)
            return self.send(200 if 'error' not in r else 400,{'ok':bool(r.get('value'))})
        self.send(404,{'error':'not found'})

def main():
    Worker().start()
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
if __name__=='__main__':main()
