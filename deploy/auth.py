#!/usr/bin/env python3
"""Local cookie gate. Opaque one-year sessions; never log credentials or tokens."""
import base64, hashlib, hmac, html, http.cookies, http.server, json, os, pathlib, secrets, tempfile, threading, time, urllib.parse

MAX_AGE = 31536000
COOKIE = '__Host-opencode_session'

class Sessions:
    def __init__(self, folder, username, password):
        self.folder=pathlib.Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.folder.chmod(0o700)
        self.file=self.folder/'sessions.json';self.lock=threading.RLock()
        self.fingerprint=hashlib.sha256((username+'\0'+password).encode()).hexdigest()
        try:
            data=json.loads(self.file.read_text())
            self.tokens=data.get('tokens',{}) if hmac.compare_digest(data.get('credentials',''),self.fingerprint) else {}
        except (OSError,ValueError):self.tokens={}
    def save(self):
        fd,name=tempfile.mkstemp(prefix='.sessions-',dir=str(self.folder))
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w') as stream:json.dump({'credentials':self.fingerprint,'tokens':self.tokens},stream)
            os.replace(name,self.file)
        finally:
            if os.path.exists(name):os.unlink(name)
    def issue(self):
        with self.lock:
            now=int(time.time());self.tokens={key:expiry for key,expiry in self.tokens.items() if expiry>now}
            if len(self.tokens)>=1024:self.tokens.pop(min(self.tokens,key=self.tokens.get))
            token=secrets.token_urlsafe(32);self.tokens[hashlib.sha256(token.encode()).hexdigest()]=now+MAX_AGE;self.save()
            return token
    def valid(self, token):
        if not token or len(token)>256:return False
        with self.lock:return self.tokens.get(hashlib.sha256(token.encode()).hexdigest(),0)>time.time()
    def revoke(self, token):
        with self.lock:
            self.tokens.pop(hashlib.sha256(token.encode()).hexdigest(),None);self.save()

def make_server(address, username, password, origin, folder):
    sessions=Sessions(folder,username,password)
    backend='Basic '+base64.b64encode((username+':'+password).encode()).decode()
    def cookie(token,age=MAX_AGE):
        return COOKIE+'='+token+'; Path=/; Max-Age='+str(age)+'; Secure; HttpOnly; SameSite=Lax'
    def safe_next(value):
        decoded=urllib.parse.unquote(value)
        return value if value.startswith('/') and not decoded.startswith('//') and '\\' not in decoded and not any(ord(c)<32 for c in decoded) and urllib.parse.urlsplit(decoded).path not in ('/login','/logout') else '/'
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body=b'',headers=None):
            self.send_response(status);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
            for key,value in (headers or {}).items():self.send_header(key,value)
            self.end_headers()
            if self.command!='HEAD':self.wfile.write(body)
        def token(self):
            try:
                values=http.cookies.SimpleCookie();values.load(self.headers.get('Cookie',''));value=values.get(COOKIE)
                return value.value if value else ''
            except http.cookies.CookieError:return ''
        def same_origin(self):
            supplied=self.headers.get('X-Original-Origin') or self.headers.get('Origin')
            return not supplied or hmac.compare_digest(supplied,origin)
        def do_GET(self):
            path=urllib.parse.urlsplit(self.path)
            if path.path=='/image-preview':
                if not self.same_origin():self.reply(403);return
                if not (sessions.valid(self.token()) or hmac.compare_digest(self.headers.get('Authorization','').encode(),backend.encode())):self.reply(401);return
                from image_preview import preview
                url=urllib.parse.parse_qs(path.query).get('url',[''])[0]
                images=preview(url,urllib.parse.urlsplit(origin).hostname)
                self.reply(200,json.dumps({'images':images}).encode(),{'Content-Type':'application/json'});return
            if path.path=='/auth':
                if not self.same_origin():self.reply(403);return
                if sessions.valid(self.token()):self.reply(200,headers={'X-Opencode-Authorization':backend});return
                supplied=self.headers.get('Authorization','')
                if supplied and hmac.compare_digest(supplied.encode(),backend.encode()):
                    headers={'X-Opencode-Authorization':backend}
                    # Convert a browser's cached Basic login once; API checks do not mint sessions.
                    if 'text/html' in self.headers.get('X-Original-Accept',''):
                        headers['Set-Cookie']=cookie(sessions.issue())
                    self.reply(200,headers=headers);return
                self.reply(401);return
            if path.path!='/login':self.reply(404);return
            next_url=safe_next(urllib.parse.parse_qs(path.query).get('next',[self.headers.get('X-Original-URI','/')])[0])
            page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenCode 登录</title><style>body{color-scheme:light dark;font:16px system-ui;margin:0;min-height:100dvh;display:grid;place-items:center;background:#18181b;color:#fafafa}form{width:min(320px,calc(100vw - 48px));display:grid;gap:14px}h1{font-size:24px}input,button{box-sizing:border-box;width:100%;font:inherit;min-height:44px;border:1px solid #71717a;border-radius:8px;padding:10px;background:#27272a;color:inherit}button{background:#f4f4f5;color:#18181b;cursor:pointer}small{color:#a1a1aa}</style><form action="/login" method="post"><h1>OpenCode</h1><label>用户名<input name="username" autocomplete="username" required value="'''+html.escape(username,quote=True)+'''"></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><input type="hidden" name="next" value="'''+html.escape(next_url,quote=True)+'''"><button type="submit">登录</button><small>此浏览器保持登录一年。清理网站数据或使用无痕模式会提前退出。</small></form></html>'''
            self.reply(200,page.encode(),{'Content-Type':'text/html; charset=utf-8'})
        def do_HEAD(self):self.do_GET()
        def do_POST(self):
            if not self.same_origin():self.reply(403);return
            path=urllib.parse.urlsplit(self.path).path
            if path=='/logout':
                sessions.revoke(self.token());self.reply(303,headers={'Set-Cookie':cookie('',0),'Location':'/login'});return
            if path!='/login':self.reply(404);return
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:self.reply(400);return
            if length<1 or length>8192:self.reply(400);return
            try:data=urllib.parse.parse_qs(self.rfile.read(length).decode(),keep_blank_values=True)
            except UnicodeError:self.reply(400);return
            user=data.get('username',[''])[0];secret=data.get('password',[''])[0]
            if not (hmac.compare_digest(user.encode(),username.encode()) and hmac.compare_digest(secret.encode(),password.encode())):
                self.reply(401,'用户名或密码不正确。请返回重试。'.encode(),{'Content-Type':'text/plain; charset=utf-8'});return
            self.reply(303,headers={'Set-Cookie':cookie(sessions.issue()),'Location':safe_next(data.get('next',['/'])[0])})
    class LoginServer(http.server.ThreadingHTTPServer):
        daemon_threads=True
        request_queue_size=128
    return LoginServer(address,Handler)

if __name__=='__main__':
    make_server(('127.0.0.1',int(os.environ.get('OPENCODE_AUTH_PORT','4097'))),os.environ['OPENCODE_SERVER_USERNAME'],os.environ['OPENCODE_SERVER_PASSWORD'],os.environ['OPENCODE_PUBLIC_ORIGIN'],os.environ.get('OPENCODE_AUTH_STATE','/var/lib/opencode-auth')).serve_forever()
