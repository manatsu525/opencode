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

ORIGIN='https://test.example:8558'

class WorkspaceDeleteTests(WorkspaceFileTests):
    """Deletion: only POST, same origin, custom header, JSON; strict containment; symlinks never followed."""
    def delete(self,path,kind,headers=None,auth=True,method='POST',body=None):
        base={'Origin':ORIGIN,'Content-Type':'application/json','X-OpenCode-Files':'delete','Sec-Fetch-Site':'same-origin'}
        base.update(headers or {})
        base={k:v for k,v in base.items() if v is not None}
        status,_,raw=self.request('/files/delete',method,json.dumps({'path':path,'type':kind}) if body is None else body,base,auth)
        return status,(json.loads(raw) if raw[:1]==b'{' else raw)
    def info(self,path):
        status,_,raw=self.request('/files/info?path='+urllib.parse.quote(path));return status,json.loads(raw)
    def test_delete_file(self):
        root=pathlib.Path(self.ws.name)
        self.assertEqual(self.info('xiangqi.html')[1]['files'],1)
        self.assertEqual(self.delete('xiangqi.html','file'),(200,{'deleted':{'files':1,'directories':0,'symlinks':0}}))
        self.assertFalse((root/'xiangqi.html').exists())
        self.assertNotIn('xiangqi.html',[e['name'] for e in self.listing()['entries']])
        self.assertEqual(self.delete('xiangqi.html','file')[0],404)
    def test_recursive_folder_counts_and_inner_symlinks_unlinked_not_followed(self):
        root=pathlib.Path(self.ws.name);outside=pathlib.Path(self.outside.name)
        os.symlink(outside,root/'docs/out-link');os.symlink(outside/'secret.txt',root/'docs/深层 目录/file-link')
        status,info=self.info('docs')
        self.assertEqual(status,200)
        self.assertEqual((info['type'],info['files'],info['directories'],info['symlinks'],info['truncated']),('directory',1,1,2,False))
        self.assertEqual(info['bytes'],len('  trailing whitespace kept  \n\n'.encode()))
        self.assertEqual(self.delete('docs','directory'),(200,{'deleted':{'files':1,'directories':2,'symlinks':2}}))
        self.assertFalse((root/'docs').exists())
        self.assertEqual((outside/'secret.txt').read_text(),'outside')
    def test_root_and_traversal_refused(self):
        for path in ('','/','.','./','docs/..','../x','/etc/passwd','a\\b','x\x00y'):
            with self.subTest(path=path):
                status,_=self.delete(path,'directory');self.assertEqual(status,400)
        self.assertTrue(pathlib.Path(self.ws.name,'docs').exists())
    def test_top_level_symlink_refused_and_path_through_symlink_refused(self):
        root=pathlib.Path(self.ws.name);outside=pathlib.Path(self.outside.name)
        self.assertEqual(self.delete('link.txt','file'),(400,{'error':'symlink'}))
        self.assertEqual(self.delete('linkdir','directory'),(400,{'error':'symlink'}))
        self.assertEqual(self.delete('linkdir/secret.txt','file')[0],403)
        self.assertEqual(self.info('linkdir')[0],400)
        self.assertTrue(os.path.islink(root/'link.txt'));self.assertTrue((outside/'secret.txt').exists())
    def test_type_mismatch_and_special_refused(self):
        self.assertEqual(self.delete('docs','file'),(409,{'error':'changed'}))
        self.assertEqual(self.delete('xiangqi.html','directory'),(409,{'error':'changed'}))
        self.assertEqual(self.delete('pipe','file')[0],409)
        self.assertEqual(self.delete('xiangqi.html','symlink')[0],400)
        self.assertEqual(self.info('pipe')[0],403)
    def test_csrf_protections(self):
        root=pathlib.Path(self.ws.name)
        cases=[({'Origin':None},403),({'Origin':'https://evil.example'},403),({'Origin':'null'},403),
               ({'X-OpenCode-Files':None},403),({'X-OpenCode-Files':'1'},403),({'Sec-Fetch-Site':'cross-site'},403),
               ({'Sec-Fetch-Site':'same-site'},403),({'Content-Type':'text/plain'},415),({'Content-Type':'application/x-www-form-urlencoded'},415)]
        for headers,status in cases:
            with self.subTest(headers=headers):self.assertEqual(self.delete('xiangqi.html','file',headers)[0],status)
        self.assertEqual(self.delete('xiangqi.html','file',auth=False)[0],401)
        self.assertEqual(self.delete('xiangqi.html','file',{'Cookie':'__Host-opencode_session=forged'},auth=False)[0],401)
        self.assertEqual(self.delete('xiangqi.html','file',body='not json')[0],400)
        self.assertEqual(self.delete('xiangqi.html','file',body='[]')[0],400)
        self.assertEqual(self.delete('xiangqi.html','file',body='x'*9000)[0],400)
        # GET never mutates.
        self.assertEqual(self.request('/files/delete?path=xiangqi.html')[0],405)
        self.assertEqual(self.request('/files/info?path=xiangqi.html')[0],200)
        self.assertTrue((root/'xiangqi.html').exists())
    def test_directory_swapped_for_symlink_mid_delete(self):
        root=pathlib.Path(self.ws.name);outside=pathlib.Path(self.outside.name)
        (root/'victim').mkdir();(root/'victim/a.txt').write_text('a')
        original=workspace_files._purge
        def swap(fd,totals,depth,device):
            # Replace the folder by a symlink to the outside right after the server opened it.
            if depth==1:
                (root/'victim/a.txt').rename(root/'a-moved.txt');(root/'victim').rmdir();os.symlink(outside,root/'victim')
            return original(fd,totals,depth,device)
        workspace_files._purge=swap
        try:status,_=self.delete('victim','directory')
        finally:workspace_files._purge=original
        self.assertEqual(status,409)
        self.assertEqual((outside/'secret.txt').read_text(),'outside')
        self.assertTrue(os.path.islink(root/'victim'))
    def test_backend_header_and_login_both_accepted_by_auth(self):
        import base64
        for user in ('test-admin','opencode'):
            token='Basic '+base64.b64encode((user+':fake-test-secret').encode()).decode()
            status,headers,_=self.request('/auth',headers={'Authorization':token},auth=False)
            self.assertEqual(status,200)
            self.assertEqual(headers['X-Opencode-Authorization'],'Basic '+base64.b64encode(b'opencode:fake-test-secret').decode())

if __name__=='__main__':unittest.main()
