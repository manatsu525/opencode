#!/usr/bin/env python3
"""Local cookie gate with multiple users. Opaque one-year sessions; never log credentials or tokens.

The primary user (from server.env) keeps the original backend (opencode.service) and workspace. Every other user gets
an own backend instance (opencode-user@NAME, own port, own workspace and chat history, everything else shared); the
gate tells nginx which port to use. Admins manage users at /account. The backend only accepts its fixed user
`opencode`, so the gate hands nginx a separate Basic header for it. Workspace files: GET /files/list|download|info
read, and POST /files/delete is the only file mutation (same origin, JSON, custom header)."""
import base64, hashlib, hmac, html, http.cookies, http.server, json, os, pathlib, re, secrets, socket, tempfile, threading, time, urllib.parse
import workspace_files

MAX_AGE = 31536000
COOKIE = '__Host-opencode_session'
NAME = re.compile(r'[a-z][a-z0-9_-]{0,31}')
FIRST_PORT, LAST_PORT = 4101, 4999
ITERATIONS = 200000
USERS_ROOT = '/var/lib/opencode/users'

def atomic_json(folder, file, value, mode=0o600):
    fd,name=tempfile.mkstemp(prefix='.tmp-',dir=str(folder))
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as stream:json.dump(value,stream,ensure_ascii=False,indent=1)
        os.replace(name,str(file))
    finally:
        if os.path.exists(name):os.unlink(name)

def hash_password(password):
    salt=secrets.token_hex(16)
    return 'pbkdf2_sha256$%d$%s$%s'%(ITERATIONS,salt,hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),ITERATIONS).hex())

def check_password(stored, password):
    try:
        kind,rounds,salt,digest=stored.split('$')
        if kind!='pbkdf2_sha256':return False
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),int(rounds)).hex(),digest)
    except (ValueError,AttributeError):return False

DUMMY = hash_password(secrets.token_hex(8))

def password_problem(password):
    if not isinstance(password,str) or len(password)<8:return '密码至少 8 位'
    if len(password)>128 or not password.isprintable():return '密码不能超过 128 位或含控制字符'
    return None

class Users:
    """users.json: hashes and roles (gate only). instances.json: name -> port, read by root to run backends."""
    def __init__(self, folder, username, password, backend_port):
        self.folder=pathlib.Path(folder);self.file=self.folder/'users.json';self.instances=self.folder/'instances.json'
        self.lock=threading.RLock();self.primary=username;self.backend_port=backend_port
        try:self.data=json.loads(self.file.read_text())
        except (OSError,ValueError):self.data={}
        self.data.setdefault('users',{})
        fingerprint=hashlib.sha256((username+'\0'+password).encode()).hexdigest()
        users=self.data['users']
        # Install-time credentials win for the primary user: a reinstall with a new password resets it.
        self.fingerprint=fingerprint;previous=self.data.get('primary_fingerprint')
        self.changed_primary=bool(previous) and previous!=fingerprint
        if self.data.get('primary')!=username or previous!=fingerprint or username not in users:
            old=self.data.get('primary')
            if old and old!=username:users.pop(old,None)
            users[username]={'hash':hash_password(password),'admin':True,'port':backend_port,'created':int(time.time())}
            self.data['primary']=username;self.data['primary_fingerprint']=fingerprint
        self.save()
    def save(self):
        with self.lock:
            atomic_json(self.folder,self.file,self.data)
            others={name:info['port'] for name,info in self.data['users'].items() if name!=self.primary}
            atomic_json(self.folder,self.instances,{'users':others},0o644)
    def get(self, name):
        with self.lock:
            info=self.data['users'].get(name)
            return dict(info) if info else None
    def verify(self, name, password):
        info=self.get(name)
        ok=check_password(info['hash'] if info else DUMMY,password)
        return bool(info) and ok
    def workspace(self, name, primary_workspace):
        return primary_workspace if name==self.primary else USERS_ROOT+'/'+name+'/workspace'
    def listing(self):
        with self.lock:
            return [{'name':name,'admin':bool(info.get('admin')),'primary':name==self.primary,'port':info['port'],'created':info.get('created',0)} for name,info in sorted(self.data['users'].items())]
    def create(self, name, password, admin):
        with self.lock:
            if name in self.data['users']:raise ValueError('用户已存在')
            used={info['port'] for info in self.data['users'].values()}
            port=next((p for p in range(FIRST_PORT,LAST_PORT+1) if p not in used),None)
            if port is None:raise ValueError('没有可用端口')
            self.data['users'][name]={'hash':hash_password(password),'admin':bool(admin),'port':port,'created':int(time.time())};self.save()
    def set_password(self, name, password):
        with self.lock:
            if name not in self.data['users']:raise KeyError(name)
            self.data['users'][name]['hash']=hash_password(password);self.save()
    def set_admin(self, name, admin):
        with self.lock:
            if name not in self.data['users']:raise KeyError(name)
            self.data['users'][name]['admin']=bool(admin);self.save()
    def delete(self, name):
        with self.lock:
            if name not in self.data['users']:raise KeyError(name)
            del self.data['users'][name];self.save()

class Sessions:
    def __init__(self, folder, primary, fingerprint, revoke_primary=False):
        self.folder=pathlib.Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.folder.chmod(0o700)
        self.file=self.folder/'sessions.json';self.lock=threading.RLock()
        try:data=json.loads(self.file.read_text())
        except (OSError,ValueError):data={}
        tokens=data.get('tokens',{}) if isinstance(data.get('tokens'),dict) else {}
        # Version 1 sessions survive only when the install-time credentials are unchanged.
        if data.get('version')!=2 and not hmac.compare_digest(str(data.get('credentials','')),fingerprint):tokens={}
        self.tokens={}
        for key,value in tokens.items():
            # Version 1 stored only an expiry: those sessions belonged to the single (primary) user.
            if isinstance(value,(int,float)):value=[primary,int(value)]
            if isinstance(value,list) and len(value)==2:self.tokens[key]=value
        if revoke_primary:self.tokens={k:v for k,v in self.tokens.items() if v[0]!=primary}
        self.save()
    def save(self):
        with self.lock:atomic_json(self.folder,self.file,{'version':2,'tokens':self.tokens})
    def issue(self, user):
        with self.lock:
            now=int(time.time());self.tokens={key:value for key,value in self.tokens.items() if value[1]>now}
            if len(self.tokens)>=4096:self.tokens.pop(min(self.tokens,key=lambda k:self.tokens[k][1]))
            token=secrets.token_urlsafe(32);self.tokens[hashlib.sha256(token.encode()).hexdigest()]=[user,now+MAX_AGE];self.save()
            return token
    def user(self, token):
        if not token or len(token)>256:return None
        with self.lock:
            value=self.tokens.get(hashlib.sha256(token.encode()).hexdigest())
            return value[0] if value and value[1]>time.time() else None
    def revoke(self, token):
        with self.lock:
            self.tokens.pop(hashlib.sha256(token.encode()).hexdigest(),None);self.save()
    def revoke_user(self, user, keep=None):
        with self.lock:
            keep_key=hashlib.sha256(keep.encode()).hexdigest() if keep else None
            self.tokens={k:v for k,v in self.tokens.items() if v[0]!=user or k==keep_key};self.save()

MUTATION_HEADER = 'X-OpenCode-Files'
ACCOUNT_HEADER = 'X-OpenCode-Account'
MAX_BODY = 8192

def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=0.3):return True
    except OSError:return False

PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenCode 账号</title>
<style>body{color-scheme:light dark;font:15px system-ui;margin:0;background:#18181b;color:#fafafa}main{max-width:560px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px}h2{font-size:17px;margin-top:28px}
input,button,select{box-sizing:border-box;font:inherit;min-height:40px;border:1px solid #52525b;border-radius:8px;padding:8px 10px;background:#27272a;color:inherit}button{cursor:pointer;background:#f4f4f5;color:#18181b}button.ghost{background:#27272a;color:#fafafa}button.danger{background:#7f1d1d;color:#fff;border-color:#991b1b}
form{display:grid;gap:10px}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.card{border:1px solid #3f3f46;border-radius:10px;padding:12px;margin:10px 0}.muted{color:#a1a1aa;font-size:13px}#msg{min-height:20px;color:#fbbf24}a{color:#93c5fd}label.check{display:flex;gap:8px;align-items:center}label.check input{min-height:auto}</style>
<main><div class="row" style="justify-content:space-between"><h1>账号</h1><a href="/">返回 OpenCode</a></div>
<div id="who" class="muted"></div><div id="msg"></div>
<h2>修改我的密码</h2><form id="pw"><input name="old" type="password" placeholder="当前密码" autocomplete="current-password" required><input name="new" type="password" placeholder="新密码（至少 8 位）" autocomplete="new-password" required><button>修改密码</button></form>
<div id="admin" hidden><h2>新建用户</h2><form id="create"><input name="name" placeholder="用户名（小写字母开头，可含数字 _ -）" autocomplete="off" required><input name="password" type="password" placeholder="初始密码（至少 8 位）" autocomplete="new-password" required><label class="check"><input name="admin" type="checkbox">管理员（可管理用户）</label><button>创建</button></form>
<p class="muted">每个用户有独立的工作目录和聊天记录，其它目录与管理员共享。新用户的后端启动约需十几秒。</p><h2>用户</h2><div id="users"></div></div>
<form method="post" action="/logout" style="margin-top:32px"><button class="ghost">退出登录</button></form></main>
<script>
const msg=t=>{document.getElementById('msg').textContent=t||''}
async function api(body){const r=await fetch('/account/api',{method:'POST',headers:{'Content-Type':'application/json','X-OpenCode-Account':'1'},body:JSON.stringify(body)});let d={};try{d=await r.json()}catch(e){}if(!r.ok)throw new Error(d.error||('失败 '+r.status));return d}
function el(tag,attrs,...kids){const e=document.createElement(tag);Object.assign(e,attrs||{});for(const k of kids)e.append(k);return e}
async function load(){const r=await fetch('/account/state',{headers:{'X-OpenCode-Account':'1'}});if(r.status==401){location='/login?next=/account';return}const s=await r.json();
document.getElementById('who').textContent='当前用户：'+s.user+(s.admin?'（管理员）':'')+'　工作目录：'+s.workspace;
document.getElementById('admin').hidden=!s.admin;if(!s.admin)return;const box=document.getElementById('users');box.replaceChildren();
for(const u of s.users){const c=el('div',{className:'card'});c.append(el('div',{},el('b',{textContent:u.name}),' ',el('span',{className:'muted',textContent:(u.primary?'主账号 · ':'')+(u.admin?'管理员':'普通用户')+' · 后端'+(u.running?'运行中':'未就绪')+' · 工作目录 '+u.workspace})));
if(!u.primary){const row=el('div',{className:'row'});
row.append(el('button',{className:'ghost',textContent:'重置密码',onclick:async()=>{const p=prompt('给 '+u.name+' 设新密码（至少 8 位）');if(!p)return;try{await api({action:'reset',name:u.name,password:p});msg('已重置 '+u.name+' 的密码，其已登录设备需重新登录')}catch(e){msg(e.message)}}}));
if(u.name!==s.user)row.append(el('button',{className:'ghost',textContent:u.admin?'取消管理员':'设为管理员',onclick:async()=>{try{await api({action:'set_admin',name:u.name,admin:!u.admin});load()}catch(e){msg(e.message)}}}));
if(u.name!==s.user)row.append(el('button',{className:'danger',textContent:'删除',onclick:async()=>{if(!confirm('删除用户 '+u.name+'？其后端会停止，工作目录和聊天记录移入归档目录（不立即删除）。'))return;try{await api({action:'delete',name:u.name});msg('已删除 '+u.name);load()}catch(e){msg(e.message)}}}));
c.append(row)}box.append(c)}}
document.getElementById('pw').onsubmit=async e=>{e.preventDefault();const f=e.target;try{await api({action:'passwd',old:f.old.value,new:f.new.value});f.reset();msg('密码已修改，其它设备需重新登录')}catch(x){msg(x.message)}};
document.getElementById('create').onsubmit=async e=>{e.preventDefault();const f=e.target;try{await api({action:'create',name:f.name.value.trim(),password:f.password.value,admin:f.admin.checked});f.reset();msg('已创建，后端启动中');load();setTimeout(load,15000)}catch(x){msg(x.message)}};
load()
</script></html>'''

def make_server(address, username, password, origin, folder, workspace=None, backend_username='opencode', backend_port=4096):
    folder=pathlib.Path(folder);folder.mkdir(parents=True,exist_ok=True);folder.chmod(0o700)
    users=Users(folder,username,password,int(backend_port))
    sessions=Sessions(folder,username,users.fingerprint,users.changed_primary)
    def basic(user):return 'Basic '+base64.b64encode((user+':'+password).encode()).decode()
    # login: what a browser or API client may send (primary user only); backend: what nginx injects.
    login=basic(username);backend=basic(backend_username)
    def basic_ok(supplied):
        return bool(supplied) and (hmac.compare_digest(supplied.encode(),login.encode()) or hmac.compare_digest(supplied.encode(),backend.encode()))
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
        def current(self):
            """The signed-in user that still exists, or None."""
            name=sessions.user(self.token())
            if name and users.get(name):return name
            if basic_ok(self.headers.get('Authorization','')):return username
            return None
        def json_reply(self,status,value):
            self.reply(status,json.dumps(value,ensure_ascii=False).encode(),{'Content-Type':'application/json; charset=utf-8','X-Content-Type-Options':'nosniff'})
        def refused(self,error):
            self.json_reply(error.status,{'error':error.reason})
        def files(self,path):
            # nginx already ran auth_request; check again so the sidecar is never an open file server.
            user=self.current()
            if not user:self.reply(401,b'login required',{'Content-Type':'text/plain; charset=utf-8'});return
            if not workspace:self.reply(404);return
            root=users.workspace(user,workspace)
            query=urllib.parse.parse_qs(path.query,keep_blank_values=True).get('path',[''])
            try:
                if path.path=='/files/list':
                    self.json_reply(200,workspace_files.list_directory(root,query[0]));return
                if path.path=='/files/info':
                    self.json_reply(200,workspace_files.inspect(root,query[0]));return
                if path.path!='/files/download':self.reply(404);return
                file,size,name=workspace_files.open_file(root,query[0])
            except workspace_files.Refused as error:
                self.refused(error);return
            try:
                self.send_response(200)
                for key,value in workspace_files.download_headers(name,size).items():self.send_header(key,value)
                self.end_headers()
                if self.command!='HEAD':workspace_files.stream(file,size,self.wfile)
            except OSError:self.close_connection=True
            finally:os.close(file)
        def state(self):
            user=self.current()
            if not user:self.json_reply(401,{'error':'login required'});return
            info=users.get(user);result={'user':user,'admin':bool(info.get('admin')),'workspace':users.workspace(user,workspace or '')}
            if result['admin']:
                result['users']=[dict(item,workspace=users.workspace(item['name'],workspace or ''),running=port_open(item['port'])) for item in users.listing()]
            self.json_reply(200,result)
        def do_GET(self):
            path=urllib.parse.urlsplit(self.path)
            if path.path in ('/files/delete','/account/api'):self.reply(405,headers={'Allow':'POST'});return
            if path.path.startswith('/files/'):self.files(path);return
            if path.path=='/account':
                if not self.current():self.reply(303,headers={'Location':'/login?next=/account'});return
                self.reply(200,PAGE.encode(),{'Content-Type':'text/html; charset=utf-8'});return
            if path.path=='/account/state':self.state();return
            if path.path=='/auth':
                if not self.same_origin():self.reply(403);return
                name=sessions.user(self.token())
                info=users.get(name) if name else None
                if info:self.reply(200,headers={'X-Opencode-Authorization':backend,'X-Opencode-Port':str(info['port']),'X-Opencode-User':name});return
                if basic_ok(self.headers.get('Authorization','')):
                    headers={'X-Opencode-Authorization':backend,'X-Opencode-Port':str(users.backend_port),'X-Opencode-User':username}
                    # Convert a browser's cached Basic login once; API checks do not mint sessions.
                    if 'text/html' in self.headers.get('X-Original-Accept',''):
                        headers['Set-Cookie']=cookie(sessions.issue(username))
                    self.reply(200,headers=headers);return
                self.reply(401);return
            if path.path!='/login':self.reply(404);return
            next_url=safe_next(urllib.parse.parse_qs(path.query).get('next',[self.headers.get('X-Original-URI','/')])[0])
            page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenCode 登录</title><style>body{color-scheme:light dark;font:16px system-ui;margin:0;min-height:100dvh;display:grid;place-items:center;background:#18181b;color:#fafafa}form{width:min(320px,calc(100vw - 48px));display:grid;gap:14px}h1{font-size:24px}input,button{box-sizing:border-box;width:100%;font:inherit;min-height:44px;border:1px solid #71717a;border-radius:8px;padding:10px;background:#27272a;color:inherit}button{background:#f4f4f5;color:#18181b;cursor:pointer}small{color:#a1a1aa}</style><form action="/login" method="post"><h1>OpenCode</h1><label>用户名<input name="username" autocomplete="username" autocapitalize="none" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><input type="hidden" name="next" value="'''+html.escape(next_url,quote=True)+'''"><button type="submit">登录</button><small>此浏览器保持登录一年。清理网站数据或使用无痕模式会提前退出。</small></form></html>'''
            self.reply(200,page.encode(),{'Content-Type':'text/html; charset=utf-8'})
        def do_HEAD(self):self.do_GET()
        def read_json(self, header, value):
            # A mutation must prove it comes from this site's own script: the exact Origin (never optional here),
            # a custom header no form or link can set, a JSON body, and a same-origin fetch when the browser says.
            supplied=self.headers.get('Origin','')
            if not supplied or not hmac.compare_digest(supplied,origin):self.json_reply(403,{'error':'origin'});return None
            if self.headers.get('Sec-Fetch-Site','same-origin')!='same-origin':self.json_reply(403,{'error':'origin'});return None
            if self.headers.get(header)!=value:self.json_reply(403,{'error':'header'});return None
            if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':self.json_reply(415,{'error':'json required'});return None
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:self.json_reply(400,{'error':'length'});return None
            if length<1 or length>MAX_BODY:self.json_reply(400,{'error':'length'});return None
            try:data=json.loads(self.rfile.read(length).decode())
            except (UnicodeError,ValueError):self.json_reply(400,{'error':'invalid json'});return None
            if not isinstance(data,dict):self.json_reply(400,{'error':'invalid request'});return None
            return data
        def delete_file(self):
            user=self.current()
            data=self.read_json(MUTATION_HEADER,'delete')
            if data is None:return
            if not user:self.json_reply(401,{'error':'login required'});return
            if not workspace:self.reply(404);return
            if not isinstance(data.get('path'),str) or not isinstance(data.get('type'),str):
                self.json_reply(400,{'error':'invalid request'});return
            try:self.json_reply(200,{'deleted':workspace_files.delete(users.workspace(user,workspace),data['path'],data['type'])})
            except workspace_files.Refused as error:self.refused(error)
            except OSError:self.json_reply(500,{'error':'failed'})
        def account(self):
            user=self.current()
            data=self.read_json(ACCOUNT_HEADER,'1')
            if data is None:return
            if not user:self.json_reply(401,{'error':'login required'});return
            action=data.get('action')
            if action=='passwd':
                old,new=data.get('old'),data.get('new')
                if not isinstance(old,str) or not users.verify(user,old):time.sleep(0.5);self.json_reply(403,{'error':'当前密码不正确'});return
                problem=password_problem(new)
                if problem:self.json_reply(400,{'error':problem});return
                users.set_password(user,new);sessions.revoke_user(user,keep=self.token());self.json_reply(200,{'ok':True});return
            if not users.get(user).get('admin'):self.json_reply(403,{'error':'需要管理员'});return
            name=data.get('name')
            if not isinstance(name,str) or not NAME.fullmatch(name):self.json_reply(400,{'error':'用户名须为小写字母开头，1-32 位小写字母、数字、_ 或 -'});return
            if action=='create':
                problem=password_problem(data.get('password'))
                if problem:self.json_reply(400,{'error':problem});return
                try:users.create(name,data['password'],data.get('admin') is True)
                except ValueError as error:self.json_reply(409,{'error':str(error)});return
                self.json_reply(200,{'ok':True});return
            if not users.get(name):self.json_reply(404,{'error':'用户不存在'});return
            if name==users.primary:self.json_reply(403,{'error':'主账号只能自己改密码'});return
            if action=='reset':
                problem=password_problem(data.get('password'))
                if problem:self.json_reply(400,{'error':problem});return
                users.set_password(name,data['password']);sessions.revoke_user(name);self.json_reply(200,{'ok':True});return
            if name==user:self.json_reply(403,{'error':'不能修改或删除自己'});return
            if action=='set_admin':users.set_admin(name,data.get('admin') is True);self.json_reply(200,{'ok':True});return
            if action=='delete':users.delete(name);sessions.revoke_user(name);self.json_reply(200,{'ok':True});return
            self.json_reply(400,{'error':'unknown action'})
        def do_POST(self):
            path=urllib.parse.urlsplit(self.path).path
            if path=='/files/delete':self.delete_file();return
            if path=='/account/api':self.account();return
            if not self.same_origin():self.reply(403);return
            if path=='/logout':
                sessions.revoke(self.token());self.reply(303,headers={'Set-Cookie':cookie('',0),'Location':'/login'});return
            if path!='/login':self.reply(404);return
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:self.reply(400);return
            if length<1 or length>8192:self.reply(400);return
            try:data=urllib.parse.parse_qs(self.rfile.read(length).decode(),keep_blank_values=True)
            except UnicodeError:self.reply(400);return
            user=data.get('username',[''])[0].strip();secret=data.get('password',[''])[0]
            if not users.verify(user,secret):
                time.sleep(0.5)
                self.reply(401,'用户名或密码不正确。请返回重试。'.encode(),{'Content-Type':'text/plain; charset=utf-8'});return
            self.reply(303,headers={'Set-Cookie':cookie(sessions.issue(user)),'Location':safe_next(data.get('next',['/'])[0])})
    class LoginServer(http.server.ThreadingHTTPServer):
        daemon_threads=True
        request_queue_size=128
    server=LoginServer(address,Handler);server.users=users;server.sessions=sessions
    return server

if __name__=='__main__':
    make_server(('127.0.0.1',int(os.environ.get('OPENCODE_AUTH_PORT','4097'))),os.environ['OPENCODE_SERVER_USERNAME'],os.environ['OPENCODE_SERVER_PASSWORD'],os.environ['OPENCODE_PUBLIC_ORIGIN'],os.environ.get('OPENCODE_AUTH_STATE','/var/lib/opencode-auth'),os.environ.get('OPENCODE_WORKSPACE'),os.environ.get('OPENCODE_BACKEND_USERNAME','opencode'),int(os.environ.get('OPENCODE_BACKEND_PORT','4096'))).serve_forever()
