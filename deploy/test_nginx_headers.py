#!/usr/bin/env python3
"""Render-only nginx header inheritance regressions, with fake credentials."""
import json,pathlib,re,shlex,subprocess,sys,tempfile,unittest

class HeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();root=pathlib.Path(cls.temp.name);login=root/'login.json';login.write_text(json.dumps({'username':'fixture-admin','password':'fixture-not-real'}));login.chmod(0o600)
        subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('render.py')),str(root),'127.0.0.1','8558','4096','/var/lib/opencode/workspace',str(login),'3650','4097'],check=True)
        cls.text=(root/'etc/opencode/nginx.conf').read_text();cls.locations=[]
        for match in re.finditer(r'(?m)^  location[^\n{]*\{',cls.text):
            start=match.end();depth=1;end=start
            while depth:
                depth+=(cls.text[end]=='{')-(cls.text[end]=='}');end+=1
            cls.locations.append((match.group(),cls.text[start:end-1]))
        cls.login=next(body for name,body in cls.locations if '(login|logout)' in name)
        cls.server=cls.text.split('  location',1)[0]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def headers(self,body):
        values={}
        for line in body.splitlines():
            if line.strip().startswith('add_header '):
                tokens=shlex.split(line.strip().rstrip(';'));self.assertEqual(tokens[-1],'always');values[tokens[1]]=tokens[2]
        return values
    def test_login_referrer_keeps_real_origin(self):self.assertEqual(self.headers(self.login)['Referrer-Policy'],'same-origin')
    def test_app_referrer_remains_private(self):self.assertEqual(self.headers(self.server)['Referrer-Policy'],'no-referrer')
    def test_login_retains_entire_security_header_set(self):
        server=self.headers(self.server);login=self.headers(self.login);self.assertEqual(set(server),set(login))
        for key in server:
            if key!='Referrer-Policy':self.assertEqual(login[key],server[key])
        self.assertIn("frame-ancestors 'none'",login['Content-Security-Policy']);self.assertEqual(login['X-Content-Type-Options'],'nosniff')
    def test_no_other_partial_location_header_override(self):
        for name,body in self.locations:
            headers=self.headers(body)
            if headers:self.assertEqual(set(headers),set(self.headers(self.server)),name)
    def test_image_cache_inherits_cookie_auth_and_old_previews_disabled(self):
        body=next(body for name,body in self.locations if '/chat-images/' in name and 'alias' in body)
        self.assertNotIn('auth_request off',body);self.assertIn('alias /var/lib/opencode-images/',body)
        self.assertIn('location = /image-preview { return 410; }',self.text)
    def test_cookie_upgrade_header_and_upstream_cookie_passthrough(self):
        self.assertEqual(self.headers(self.login)['Set-Cookie'],'$opencode_session_cookie');self.assertNotIn('proxy_hide_header Set-Cookie',self.text)

if __name__=='__main__':unittest.main()
