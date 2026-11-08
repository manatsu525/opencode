import base64,html,io,json,pathlib,tempfile,unittest
from unittest.mock import patch
import image_network,image_search,image_config
class Tests(unittest.TestCase):
 def dns(self,host,port,**kwargs):return [(2,1,6,'',('127.0.0.1' if host=='private.test' else '1.1.1.1',port))]
 def test_private_credentials_and_own_targets_rejected(self):
  with patch('image_network.socket.getaddrinfo',side_effect=self.dns):
   for url in ('http://private.test/x','https://a:b@public.test/','file:///etc/passwd','https://public.test:8558/x'):
    with self.assertRaises(ValueError):image_network.target(url)
   with self.assertRaises(ValueError):image_network.target('https://public.test','own.test')
 def test_ipv4_preferred_over_unreachable_ipv6(self):
  with patch('image_network.socket.getaddrinfo',return_value=[(10,1,6,'',('2606:4700:4700::1111',443)),(2,1,6,'',('1.1.1.1',443))]):self.assertEqual(image_network.target('https://public.test')[3][0],'1.1.1.1')
 def test_reject_mapped_private_ipv6(self):
  for ip in ('::ffff:127.0.0.1','64:ff9b::a9fe:a9fe','2002:7f00:1::','fe80::1','169.254.169.254'):
   with patch('image_network.socket.getaddrinfo',return_value=[(10,1,6,'',(ip,443))]),self.assertRaises(ValueError):image_network.target('https://public.test')
 def test_bing_returns_actual_murl_not_og_page(self):
  raw=('<a m="'+html.escape(json.dumps({'murl':'https://cdn.test/photo.jpg','purl':'https://site.test/article','t':'Dog'}),quote=True)+'"></a>').encode()
  with patch('image_search.fetch',return_value=(raw,'text/html','')):
   self.assertEqual(image_search.candidates('柴犬',2)[0]['original_url'],'https://cdn.test/photo.jpg')
 def test_config_merge_idempotent_and_global_rule(self):
  with tempfile.TemporaryDirectory() as root:
   directory=pathlib.Path(root)/'etc/opencode';directory.mkdir(parents=True);file=directory/'opencode.json';file.write_text(json.dumps({'enabled_providers':['opencode-go'],'instructions':['/existing.md'],'mcp':{'existing':{'type':'local','command':['echo']}}}));file.chmod(0o640)
   image_config.install(root,'example.test',8558);image_config.install(root,'example.test',8558);v=json.loads(file.read_text());self.assertIn('existing',v['mcp']);self.assertEqual(v['instructions'],['/existing.md','/etc/opencode/IMAGE_SEARCH.md']);self.assertEqual(file.stat().st_mode&0o777,0o640);self.assertIn('必须实际调用',(directory/'IMAGE_SEARCH.md').read_text())
 def test_mcp_returns_real_image_content_and_url_metadata(self):
  with tempfile.TemporaryDirectory() as root:
   p=pathlib.Path(root)/('a'*64+'.jpg');p.write_bytes(b'jpeg-test');result={'images':[{'display_url':'https://example.test/chat-images/'+p.name}]}
   with patch.dict('os.environ',{'OPENCODE_IMAGE_DIR':root}),patch('image_search.search_images',return_value=result):
    r=image_search.handle({'method':'tools/call','params':{'name':'search_images','arguments':{'query':'cats'}}});self.assertFalse(r['isError']);self.assertEqual([v['type'] for v in r['content']],['text','image']);self.assertEqual(base64.b64decode(r['content'][1]['data']),b'jpeg-test')
 def test_resize_to_1280_jpeg(self):
  try:from PIL import Image
  except ImportError:self.skipTest('Pillow required; run complete test on target VM')
  b=io.BytesIO();Image.new('RGB',(2000,1500),'red').save(b,'PNG')
  with tempfile.TemporaryDirectory() as root,patch('image_search.fetch',return_value=(b.getvalue(),'image/png','https://cdn.test/x')):
   name,size=image_search.store_image('https://cdn.test/x',root);self.assertEqual(size,(1280,960))
   with Image.open(pathlib.Path(root)/name) as image:self.assertEqual(image.format,'JPEG')
if __name__=='__main__':unittest.main()
