#!/usr/bin/env python3
"""Workspace browser/download tests through the real auth sidecar handler (no model calls)."""
import hashlib, http.client, json, os, pathlib, tempfile, threading, unittest, urllib.parse
from auth import make_server
import workspace_files

class WorkspaceFileTests(unittest.TestCase):
    def setUp(self):
        self.state=tempfile.TemporaryDirectory();self.outside=tempfile.TemporaryDirectory();self.ws=tempfile.TemporaryDirectory()
        root=pathlib.Path(self.ws.name)
        (root/'xiangqi.html').write_bytes('<!doctype html>\n<html lang="zh-CN">象棋\n</html>\n\n'.encode())
        os.chmod(root/'xiangqi.html',0o600)
        self.binary=os.urandom(3*1024*1024+17)+b'\0\r\n  ';(root/'game.bin').write_bytes(self.binary)
        (root/'docs/深层 目录').mkdir(parents=True);(root/'docs/深层 目录/报告 #1.txt').write_text('  trailing whitespace kept  \n\n')
        (root/'.gitignore').write_text('build/\n');(root/'build').mkdir();(root/'build/out.js').write_text('ignored but listed')
        secret=pathlib.Path(self.outside.name)/'secret.txt';secret.write_text('outside')
        os.symlink(secret,root/'link.txt');os.symlink(self.outside.name,root/'linkdir');os.mkfifo(root/'pipe')
        self.server=make_server(('127.0.0.1',0),'test-admin','fake-test-secret','https://test.example:8558',self.state.name,self.ws.name)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        status,headers,_=self.request('/login','POST',urllib.parse.urlencode({'username':'test-admin','password':'fake-test-secret'}),{'Origin':'https://test.example:8558','Content-Type':'application/x-www-form-urlencoded'},auth=False)
        self.cookie=headers['Set-Cookie'].split(';')[0]
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        for item in (self.state,self.outside,self.ws):item.cleanup()
    def request(self,path,method='GET',body=None,headers=None,auth=True):
        headers=dict(headers or {})
        if auth:headers['Cookie']=self.cookie
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        connection.request(method,path,body=body,headers=headers);response=connection.getresponse()
        result=(response.status,dict(response.getheaders()),response.read());connection.close();return result
    def listing(self,path=''):
        status,headers,body=self.request('/files/list?path='+urllib.parse.quote(path));self.assertEqual(status,200,body);return json.loads(body)
    def download(self,path):return self.request('/files/download?path='+urllib.parse.quote(path))
    def test_root_listing_includes_ignored_hidden_and_marks_special(self):
        entries={e['name']:e for e in self.listing()['entries']}
        self.assertEqual(entries['docs']['type'],'directory');self.assertEqual(entries['build']['type'],'directory');self.assertIn('.gitignore',entries)
        self.assertEqual(entries['xiangqi.html']['type'],'file');self.assertEqual(entries['game.bin']['size'],len(self.binary))
        self.assertEqual(entries['link.txt']['type'],'symlink');self.assertEqual(entries['linkdir']['type'],'symlink');self.assertEqual(entries['pipe']['type'],'other')
        self.assertEqual([e['type'] for e in self.listing()['entries']][:2],['directory']*2)
    def test_nested_unicode_listing_and_download(self):
        self.assertEqual([e['path'] for e in self.listing('docs')['entries']],['docs/深层 目录'])
        nested=self.listing('docs/深层 目录')['entries'][0];self.assertEqual(nested['path'],'docs/深层 目录/报告 #1.txt')
        status,headers,body=self.download(nested['path']);self.assertEqual(status,200);self.assertEqual(body,b'  trailing whitespace kept  \n\n')
        self.assertEqual(headers['Content-Disposition'],"attachment; filename=\"__ #1.txt\"; filename*=UTF-8''%E6%8A%A5%E5%91%8A%20%231.txt")
        self.assertEqual(self.listing('build')['entries'][0]['name'],'out.js')
    def test_exact_bytes_and_security_headers(self):
        for name,expected in (('xiangqi.html',(pathlib.Path(self.ws.name)/'xiangqi.html').read_bytes()),('game.bin',self.binary)):
            status,headers,body=self.download(name);self.assertEqual(status,200)
            self.assertEqual(hashlib.sha256(body).hexdigest(),hashlib.sha256(expected).hexdigest());self.assertEqual(int(headers['Content-Length']),len(expected))
            self.assertEqual(headers['Content-Type'],'application/octet-stream');self.assertTrue(headers['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff');self.assertEqual(headers['Cache-Control'],'no-store');self.assertIn('sandbox',headers['Content-Security-Policy'])
        status,headers,body=self.request('/files/download?path=game.bin','HEAD');self.assertEqual((status,body),(200,b''));self.assertEqual(int(headers['Content-Length']),len(self.binary))
    def test_owner_only_0600_file(self):
        self.assertEqual(os.stat(pathlib.Path(self.ws.name)/'xiangqi.html').st_mode&0o777,0o600);self.assertEqual(self.download('xiangqi.html')[0],200)
    def test_unauthenticated_401(self):
        for path in ('/files/list?path=','/files/download?path=xiangqi.html'):
            status,_,body=self.request(path,auth=False);self.assertEqual(status,401);self.assertNotIn(b'html',body)
            self.assertEqual(self.request(path,headers={'Cookie':'__Host-opencode_session=forged'},auth=False)[0],401)
    def test_traversal_absolute_symlink_special_rejected(self):
        for path,status in (('../'+pathlib.Path(self.outside.name).name+'/secret.txt',400),('/etc/passwd',400),('docs/../../x',400),('a\\..\\b',400),('x\x00y',400),
                            ('link.txt',403),('linkdir/secret.txt',403),('pipe',403),('docs',403),('',400),('missing.txt',404),('missing/x',404)):
            with self.subTest(path=path):
                self.assertEqual(self.request('/files/download?path='+urllib.parse.quote(path))[0],status)
        for path,status in (('linkdir',403),('../',400),('/',400),('xiangqi.html',403)):
            with self.subTest(list=path):self.assertEqual(self.request('/files/list?path='+urllib.parse.quote(path))[0],status)
    def test_symlink_swap_race_is_refused(self):
        # A directory replaced by a symlink between listing and download must not be followed.
        root=pathlib.Path(self.ws.name);(root/'swap').mkdir();(root/'swap/f.txt').write_text('in');self.assertEqual(self.download('swap/f.txt')[0],200)
        (root/'swap/f.txt').unlink();(root/'swap').rmdir();os.symlink(self.outside.name,root/'swap');(pathlib.Path(self.outside.name)/'f.txt').write_text('out')
        self.assertEqual(self.download('swap/f.txt')[0],403)
    def test_unknown_files_route_404_and_no_workspace(self):
        self.assertEqual(self.request('/files/other')[0],404)
        server=make_server(('127.0.0.1',0),'a','b','https://x',self.state.name);self.assertIsNotNone(server);server.server_close()
    def test_components_and_disposition_helpers(self):
        self.assertEqual(workspace_files.components('a//./b/'),['a','b'])
        self.assertEqual(workspace_files.disposition('a"b;c%.txt'),'attachment; filename="a_b_c_.txt"; filename*=UTF-8\'\'a%22b%3Bc%25.txt')
        with self.assertRaises(workspace_files.Refused):workspace_files.components('x'*5000)

if __name__=='__main__':unittest.main()
