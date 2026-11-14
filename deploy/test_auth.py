#!/usr/bin/env python3
"""Network-local tests; no model/server-provider calls and no real credentials."""
import base64, hashlib, http.client, json, pathlib, tempfile, threading, time, unittest, urllib.parse
from unittest.mock import patch
from auth import COOKIE, MAX_AGE, Sessions, make_server

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.username='test-admin';self.password='fake-test-secret'
        self.server=make_server(('127.0.0.1',0),self.username,self.password,'https://test.example:8558',self.temp.name)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path='/auth',method='GET',body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        connection.request(method,path,body=body,headers=headers or {});response=connection.getresponse()
        result=(response.status,dict(response.getheaders()),response.read());connection.close();return result
    def login(self,**values):
        data={'username':self.username,'password':self.password,**values}
        return self.request('/login','POST',urllib.parse.urlencode(data),{'Origin':'https://test.example:8558','Content-Type':'application/x-www-form-urlencoded'})
    def token(self):return self.login()[1]['Set-Cookie'].split(';')[0]
    def test_login_form(self):
        status,headers,body=self.request('/login');self.assertEqual(status,200);self.assertIn(b'autocomplete="current-password"',body);self.assertNotIn(self.password.encode(),body);self.assertEqual(headers['Cache-Control'],'no-store')
    def test_login_head(self):
        status,headers,body=self.request("/login","HEAD");self.assertEqual(status,200);self.assertEqual(body,b"");self.assertGreater(int(headers["Content-Length"]),0)
    def test_proxy_login_does_not_redirect_to_itself(self):
        _,_,body=self.request("/login",headers={"X-Original-URI":"/login"});self.assertIn(b'name="next" value="/"',body)
    def test_api_no_basic_challenge(self):
        status,headers,_=self.request();self.assertEqual(status,401);self.assertNotIn('WWW-Authenticate',headers)
    def test_correct_basic(self):
        status,headers,_=self.request(headers={'Authorization':'Basic '+base64.b64encode((self.username+':'+self.password).encode()).decode()});self.assertEqual(status,200);self.assertIn('X-Opencode-Authorization',headers);self.assertNotIn('Set-Cookie',headers)
    def test_wrong_basic(self):self.assertEqual(self.request(headers={'Authorization':'Basic bad'})[0],401)
    def test_login_cookie_attributes(self):
        status,headers,_=self.login();self.assertEqual(status,303)
        for item in (COOKIE+'=', 'Path=/', 'Max-Age='+str(MAX_AGE),'Secure','HttpOnly','SameSite=Lax'):self.assertIn(item,headers['Set-Cookie'])
        self.assertNotIn('Domain=',headers['Set-Cookie']);self.assertEqual(headers['Location'],'/')
    def test_cookie_auth(self):self.assertEqual(self.request(headers={'Cookie':self.token()})[0],200)
    def test_same_origin_form_post_allowed(self):
        body=urllib.parse.urlencode({"username":self.username,"password":self.password})
        status,headers,_=self.request('/login','POST',body,{'Origin':'https://test.example:8558','X-Original-Origin':'https://test.example:8558','Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(status,303);self.assertIn(COOKIE+'=',headers['Set-Cookie'])
    def test_null_origin_post_still_denied(self):
        self.assertEqual(self.request('/login','POST','',{'Origin':'null','X-Original-Origin':'null'})[0],403)
    def test_wrong_password(self):self.assertEqual(self.login(password='incorrect')[0],401)
    def test_wrong_username(self):self.assertEqual(self.login(username='opencode')[0],401)
    def restarted(self,password=None):
        return make_server(('127.0.0.1',0),self.username,password or self.password,'https://test.example:8558',self.temp.name)
    def test_cookie_survives_restart(self):
        token=self.token().split('=',1)[1];other=self.restarted();self.assertEqual(other.sessions.user(token),self.username);other.server_close()
    def test_password_change_invalidates(self):
        token=self.token().split('=',1)[1];other=self.restarted('changed-secret');self.assertIsNone(other.sessions.user(token));other.server_close()
    def test_token_not_stored_raw(self):
        token=self.token().split('=',1)[1];file=pathlib.Path(self.temp.name)/'sessions.json';text=file.read_text();self.assertNotIn(token,text);self.assertNotIn(self.password,text);self.assertNotIn(self.password,(pathlib.Path(self.temp.name)/'users.json').read_text());self.assertIn(hashlib.sha256(token.encode()).hexdigest(),text);self.assertEqual(file.stat().st_mode&0o777,0o600)
    def test_expiry(self):
        token=self.token().split('=',1)[1]
        with patch('auth.time.time',return_value=time.time()+MAX_AGE+1):self.assertIsNone(self.server.sessions.user(token))
    def test_cross_origin_post_denied(self):self.assertEqual(self.request('/login','POST','',{'Origin':'https://test.example:8557'})[0],403)
    def test_cross_origin_websocket_denied(self):self.assertEqual(self.request(headers={'Cookie':self.token(),'X-Original-Origin':'https://test.example:8557'})[0],403)
    def test_same_origin_websocket_allowed(self):self.assertEqual(self.request(headers={'Cookie':self.token(),'X-Original-Origin':'https://test.example:8558'})[0],200)
    def test_redirect_safety(self):
        for value in ('https://evil.example/','//evil.example/','/\\evil.example/','/\r\ninvalid','/%2fevil.example/','/login','/logout'):
            self.assertEqual(self.login(next=value)[1]['Location'],'/')
        self.assertEqual(self.login(next='/project/session')[1]['Location'],'/project/session')
    def test_logout(self):
        token=self.token();status,headers,_=self.request('/logout','POST','',{'Cookie':token,'Origin':'https://test.example:8558'});self.assertEqual(status,303);self.assertIn('Max-Age=0',headers['Set-Cookie']);self.assertEqual(self.request(headers={'Cookie':token})[0],401)
    def test_basic_browser_upgrade(self):
        status,headers,_=self.request(headers={'Authorization':'Basic '+base64.b64encode((self.username+':'+self.password).encode()).decode(),'X-Original-Accept':'text/html'});self.assertEqual(status,200);self.assertIn('Set-Cookie',headers)
    def test_oversized_login(self):self.assertEqual(self.request('/login','POST','x'*8193)[0],400)

    # ---- multi-user ----
    ORIGIN='https://test.example:8558'
    def account(self,cookie,body):
        return self.request('/account/api','POST',json.dumps(body),{'Cookie':cookie,'Origin':self.ORIGIN,'Content-Type':'application/json','X-OpenCode-Account':'1'})
    def login_as(self,user,password):
        status,headers,_=self.request('/login','POST',urllib.parse.urlencode({'username':user,'password':password}),{'Origin':self.ORIGIN,'Content-Type':'application/x-www-form-urlencoded'})
        return status,(headers.get('Set-Cookie','').split(';')[0])
    def test_primary_routes_to_primary_backend(self):
        status,headers,_=self.request(headers={'Cookie':self.token()});self.assertEqual(status,200);self.assertEqual(headers['X-Opencode-Port'],'4096')
    def test_v1_sessions_migrate(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        folder=pathlib.Path(self.temp.name)
        for name in ('users.json','instances.json'):(folder/name).unlink()
        token='legacy-token';fp=hashlib.sha256((self.username+'\0'+self.password).encode()).hexdigest()
        (folder/'sessions.json').write_text(json.dumps({'credentials':fp,'tokens':{hashlib.sha256(token.encode()).hexdigest():int(time.time())+100}}))
        self.server=self.restarted();self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.assertEqual(self.server.sessions.user(token),self.username)
    def test_admin_creates_user_with_own_backend(self):
        admin=self.token()
        status,_,body=self.account(admin,{'action':'create','name':'alice','password':'alice-secret-1','admin':False});self.assertEqual(status,200,body)
        instances=json.loads((pathlib.Path(self.temp.name)/'instances.json').read_text())
        self.assertEqual(instances,{'users':{'alice':4101}})
        status,alice=self.login_as('alice','alice-secret-1');self.assertEqual(status,303)
        status,headers,_=self.request(headers={'Cookie':alice});self.assertEqual(headers['X-Opencode-Port'],'4101');self.assertEqual(headers['X-Opencode-User'],'alice')
        # a normal user cannot manage users
        status,_,_=self.account(alice,{'action':'create','name':'bob','password':'bob-secret-12'});self.assertEqual(status,403)
        status,_,_=self.account(alice,{'action':'delete','name':'test-admin'});self.assertEqual(status,403)
        # but can change their own password (requires the current one)
        self.assertEqual(self.account(alice,{'action':'passwd','old':'wrong-pass','new':'alice-secret-2'})[0],403)
        self.assertEqual(self.account(alice,{'action':'passwd','old':'alice-secret-1','new':'alice-secret-2'})[0],200)
        self.assertEqual(self.login_as('alice','alice-secret-1')[0],401);self.assertEqual(self.login_as('alice','alice-secret-2')[0],303)
    def test_reset_and_delete_revoke_sessions(self):
        admin=self.token();self.account(admin,{'action':'create','name':'bob','password':'bob-secret-12'})
        _,bob=self.login_as('bob','bob-secret-12');self.assertEqual(self.request(headers={'Cookie':bob})[0],200)
        self.assertEqual(self.account(admin,{'action':'reset','name':'bob','password':'bob-secret-34'})[0],200)
        self.assertEqual(self.request(headers={'Cookie':bob})[0],401)
        _,bob=self.login_as('bob','bob-secret-34')
        self.assertEqual(self.account(admin,{'action':'delete','name':'bob'})[0],200)
        self.assertEqual(self.request(headers={'Cookie':bob})[0],401)
        self.assertEqual(json.loads((pathlib.Path(self.temp.name)/'instances.json').read_text()),{'users':{}})
    def test_primary_protected(self):
        admin=self.token();self.account(admin,{'action':'create','name':'carol','password':'carol-secret','admin':True})
        _,carol=self.login_as('carol','carol-secret')
        for body in ({'action':'delete','name':'test-admin'},{'action':'reset','name':'test-admin','password':'xxxxxxxxxx'},{'action':'set_admin','name':'test-admin','admin':False}):
            self.assertEqual(self.account(carol,body)[0],403)
        self.assertEqual(self.account(carol,{'action':'delete','name':'carol'})[0],403)
    def test_account_rejects_cross_site_and_bad_names(self):
        admin=self.token()
        status,_,_=self.request('/account/api','POST','{"action":"create"}',{'Cookie':admin,'Origin':'https://evil.example','Content-Type':'application/json','X-OpenCode-Account':'1'});self.assertEqual(status,403)
        status,_,_=self.request('/account/api','POST','{"action":"create"}',{'Cookie':admin,'Origin':self.ORIGIN,'Content-Type':'application/json'});self.assertEqual(status,403)
        for name in ('Alice','../x','a b','',  'x'*40):
            self.assertEqual(self.account(admin,{'action':'create','name':name,'password':'long-enough-1'})[0],400)
        self.assertEqual(self.account(admin,{'action':'create','name':'dave','password':'short'})[0],400)
    def test_state(self):
        admin=self.token();self.account(admin,{'action':'create','name':'erin','password':'erin-secret-1'})
        status,_,body=self.request('/account/state',headers={'Cookie':admin});data=json.loads(body)
        self.assertTrue(data['admin']);self.assertEqual([u['name'] for u in data['users']],['erin','test-admin'])
        self.assertNotIn('hash',body.decode())
        _,erin=self.login_as('erin','erin-secret-1');data=json.loads(self.request('/account/state',headers={'Cookie':erin})[2])
        self.assertFalse(data['admin']);self.assertNotIn('users',data);self.assertEqual(data['workspace'],'/var/lib/opencode/users/erin/workspace')

if __name__=='__main__':unittest.main()
