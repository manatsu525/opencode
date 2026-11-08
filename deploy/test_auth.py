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
    def test_wrong_password(self):self.assertEqual(self.login(password='incorrect')[0],401)
    def test_wrong_username(self):self.assertEqual(self.login(username='opencode')[0],401)
    def test_cookie_survives_restart(self):
        token=self.token().split('=',1)[1];self.assertTrue(Sessions(self.temp.name,self.username,self.password).valid(token))
    def test_password_change_invalidates(self):
        token=self.token().split('=',1)[1];self.assertFalse(Sessions(self.temp.name,self.username,'changed-secret').valid(token))
    def test_token_not_stored_raw(self):
        token=self.token().split('=',1)[1];file=pathlib.Path(self.temp.name)/'sessions.json';text=file.read_text();self.assertNotIn(token,text);self.assertNotIn(self.password,text);self.assertIn(hashlib.sha256(token.encode()).hexdigest(),text);self.assertEqual(file.stat().st_mode&0o777,0o600)
    def test_expiry(self):
        token=self.token().split('=',1)[1]
        with patch('auth.time.time',return_value=time.time()+MAX_AGE+1):self.assertFalse(Sessions(self.temp.name,self.username,self.password).valid(token))
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

if __name__=='__main__':unittest.main()
