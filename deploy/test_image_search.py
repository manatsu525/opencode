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
   self.assertEqual(image_search.bing('柴犬',2,None,None,None)[0]['original_url'],'https://cdn.test/photo.jpg')
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
class Relevance(unittest.TestCase):
 def entry(self,t):return {'title':t,'original_url':'https://cdn.test/'+str(abs(hash(t)))+'.jpg','source_url':'https://site.test/'}
 def test_tokens(self):
  self.assertEqual(image_search.query_tokens('威兰达 2026'),{'威兰','兰达'});self.assertEqual(image_search.query_tokens('柴犬'),{'柴犬'})
  self.assertEqual(image_search.query_tokens('Lee Chong Wei 2026'),{'lee','chong','wei'})
 def test_proxy_address_loopback_only(self):
  self.assertEqual(image_network.proxy_address('socks5://127.0.0.1:40000'),('127.0.0.1',40000))
  for bad in ('socks5://10.0.0.1:1080','http://127.0.0.1:40000','socks5://u:p@127.0.0.1:40000','socks5://127.0.0.1','socks5://localhost:1'):self.assertIsNone(image_network.proxy_address(bad))
 def test_retries_unrelated_answer_and_drops_unrelated(self):
  bad=[self.entry('死亡证明模板'+str(i)) for i in range(10)];good=[self.entry('威兰达 外观'+str(i)) for i in range(8)]+[self.entry('无关')]
  calls=[]
  def fake(q,c,d,m,p):calls.append(p);return bad if len(calls)==1 else good
  with patch.dict('os.environ',{'OPENCODE_IMAGE_PROXY':'socks5://127.0.0.1:40000'}),patch('image_search.bing',side_effect=fake):
   r=image_search.candidates('威兰达',4)
  self.assertEqual(calls[:2],[('127.0.0.1',40000),None]);self.assertEqual(len(r),8);self.assertTrue(all('威兰达' in e['title'] for e in r))
 def test_nothing_relevant_returns_empty_not_garbage(self):
  with patch('image_search.bing',return_value=[self.entry('Excel tips')]*5):self.assertEqual(image_search.candidates('威兰达',4),[])
 def test_errors_raise_when_every_attempt_fails(self):
  with patch('image_search.bing',side_effect=ValueError('down')),self.assertRaises(ValueError):image_search.candidates('cats',2)
 def test_proxy_failure_falls_back_to_direct(self):
  def fake(q,c,d,m,p):
   if p:raise OSError('warp down')
   return [self.entry('cute cats '+str(i)) for i in range(6)]
  with patch.dict('os.environ',{'OPENCODE_IMAGE_PROXY':'socks5://127.0.0.1:40000'}),patch('image_search.bing',side_effect=fake):self.assertEqual(len(image_search.candidates('cats',4)),6)
class Fallback(unittest.TestCase):
 env={'OPENCODE_IMAGE_ORIGIN':'https://example.test:8558'}
 def test_google_captcha_gives_relay_link(self):
  with patch.dict('os.environ',self.env),patch('image_search.candidates',return_value=[]),patch('image_search.google',return_value={'status':'captcha'}):
   r=image_search.search_images('威兰达',4)
  self.assertEqual(r['captcha_url'],'https://example.test:8558/imgcaptcha/');self.assertIn('/imgcaptcha/',r['note'])
 def test_google_fills_missing_images(self):
  g={'status':'ok','results':[{'title':'威兰达 g','original_url':'https://g.test/1.jpg','source_url':'https://s.test/1'}]}
  with patch.dict('os.environ',self.env),patch('image_search.candidates',return_value=[]),patch('image_search.google',return_value=g),patch('image_search.store_image',return_value=('a'*64+'.jpg',(10,10))):
   r=image_search.search_images('威兰达',1)
  self.assertEqual(len(r['images']),1);self.assertEqual(r['provider'],'google-images-browser')
 def test_order_google_then_sogou_bing_last(self):
  calls=[]
  def g(q,c,d,e):
   calls.append(e);return {'status':'ok','results':[{'title':'cats '+e,'original_url':'https://%s.test/1.jpg'%e,'source_url':''}]} if e in ('google','sogou') else {'status':'blocked'}
  names=iter(['%064x.jpg'%i for i in range(9)])
  with patch.dict('os.environ',self.env),patch('image_search.candidates',return_value=[{'title':'cats bing','original_url':'https://bing.test/1.jpg','source_url':''}]) as c,patch('image_search.google',side_effect=g),patch('image_search.store_image',side_effect=lambda *a:(next(names),(10,10))):
   r=image_search.search_images('cats',3)
  self.assertEqual(calls,['google','sogou','yahoo','ddg']);self.assertEqual([i['original_url'].split('//')[1][:4] for i in r['images']],['goog','sogo','bing'])
  self.assertEqual(r['provider'],'google+sogou-images-browser+bing')
 def test_enough_google_skips_bing(self):
  g={'status':'ok','results':[{'title':'cats','original_url':'https://c.test/%d.jpg'%i,'source_url':''} for i in range(4)]}
  with patch.dict('os.environ',self.env),patch('image_search.candidates') as c,patch('image_search.google',return_value=g),patch('image_search.store_image',return_value=('b'*64+'.jpg',(10,10))):
   r=image_search.search_images('cats',2)
  c.assert_not_called();self.assertEqual(len(r['images']),2)
 def test_captcha_still_uses_bing(self):
  e=[{'title':'cats','original_url':'https://b.test/1.jpg','source_url':''}]
  with patch.dict('os.environ',self.env),patch('image_search.candidates',return_value=e),patch('image_search.google',side_effect=lambda q,c,d,e:{'status':'captcha'} if e=='google' else {'status':'blocked'}),patch('image_search.store_image',return_value=('c'*64+'.jpg',(10,10))):
   r=image_search.search_images('cats',1)
  self.assertEqual(len(r['images']),1);self.assertIn('captcha_url',r)
if __name__=='__main__':unittest.main()
