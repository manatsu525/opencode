import http.client,io,tempfile,threading,unittest
from unittest.mock import patch
from urllib.parse import urlencode
import auth,image_preview

class ImagePreviewTests(unittest.TestCase):
    def dns(self,host,port,**kwargs):
        return [(2,1,6,'',('127.0.0.1' if host=='private.test' else '1.1.1.1',port))]
    def test_private_literal_dns_and_non_http_targets_rejected(self):
        with patch('image_preview.socket.getaddrinfo',side_effect=self.dns):
            for url in ('file:///etc/passwd','http://private.test/a','https://u:p@example.com','https://example.com:8558','https://example.com/\nfoo'):
                with self.subTest(url=url),self.assertRaises(ValueError):image_preview.target(url)
            self.assertEqual(image_preview.target('https://example.com/a')[3],'1.1.1.1')
    def test_mapped_private_and_ipv6_translation_targets_rejected(self):
        for ip in ('::ffff:127.0.0.1','64:ff9b::a9fe:a9fe','2002:7f00:1::','fe80::1','169.254.169.254'):
            with patch('image_preview.socket.getaddrinfo',return_value=[(10,1,6,'',(ip,443))]),self.assertRaises(ValueError):image_preview.target('https://untrusted.test/')
    def test_own_host_and_alias_rejected(self):
        with patch('image_preview.socket.getaddrinfo',side_effect=self.dns):
            for host in ('own.test','alias.test'):
                with self.assertRaises(ValueError):image_preview.target('https://'+host,'own.test')
    def test_og_and_twitter_metadata_prioritized(self):
        parser=image_preview.PageImages();parser.feed('<img src="/logo.png"><meta property="og:image" content="/photo.jpg?a=1&amp;b=2"><meta name="twitter:image" content="https://cdn.example/p.jpg">')
        self.assertEqual(parser.preferred,['/photo.jpg?a=1&b=2','https://cdn.example/p.jpg']);self.assertEqual(parser.fallback,[])
    def test_direct_image_response_and_redirect_revalidation(self):
        class Connection:
            def __init__(self,*args,**kwargs):pass
            def request(self,*args,**kwargs):pass
            def getresponse(self):return self.response
            def close(self):pass
        class ImageResponse:
            status=200
            def getheader(self,name,default=''):return 'image/jpeg' if name=='Content-Type' else default
        class RedirectResponse:
            status=302
            def getheader(self,name,default=''):return 'http://private.test/' if name=='Location' else default
        with patch('image_preview.socket.getaddrinfo',side_effect=self.dns),patch('image_preview.http.client.HTTPConnection',Connection):
            Connection.response=ImageResponse();self.assertEqual(image_preview.load_page('https://example.com/photo'),['https://example.com/photo'])
            Connection.response=RedirectResponse()
            with self.assertRaises(ValueError):image_preview.load_page('https://example.com/article')
    def test_failures_cached_without_model_calls(self):
        image_preview.cache.clear()
        with patch('image_preview.load_page',side_effect=OSError('unreachable')) as load:
            self.assertEqual(image_preview.preview('https://example.com/x'),[]);self.assertEqual(image_preview.preview('https://example.com/x'),[]);self.assertEqual(load.call_count,1)
    def test_helper_requires_login_and_returns_previews_for_cookie(self):
        with tempfile.TemporaryDirectory() as state:
            server=auth.make_server(('127.0.0.1',0),'tester','test-secret','https://example.test',state)
            threading.Thread(target=server.serve_forever,daemon=True).start();connection=http.client.HTTPConnection(*server.server_address)
            try:
                connection.request('GET','/image-preview?url=https://public.test');response=connection.getresponse();self.assertEqual(response.status,401);response.read()
                connection.request('POST','/login',urlencode({'username':'tester','password':'test-secret'}),{'Origin':'https://example.test','Content-Type':'application/x-www-form-urlencoded'});response=connection.getresponse();self.assertEqual(response.status,303);cookie=response.getheader('Set-Cookie').split(';')[0];response.read()
                with patch('image_preview.preview',return_value=['https://cdn.test/photo.jpg']):
                    connection.request('GET','/image-preview?url=https://public.test',headers={'Cookie':cookie});response=connection.getresponse();self.assertEqual(response.status,200);self.assertIn(b'photo.jpg',response.read())
            finally:connection.close();server.shutdown();server.server_close()
if __name__=='__main__':unittest.main()
