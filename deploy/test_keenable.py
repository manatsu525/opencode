import json,pathlib,tempfile,unittest
import image_config

class Tests(unittest.TestCase):
 def test_remote_is_keyless_oauth_disabled_and_idempotent(self):
  with tempfile.TemporaryDirectory() as root:
   directory=pathlib.Path(root)/'etc/opencode';directory.mkdir(parents=True);file=directory/'opencode.json'
   old={'mcp':{'existing':{'type':'local','command':['echo']}},'instructions':['/existing.md'],'permission':{'*':'allow'}}
   file.write_text(json.dumps(old));file.chmod(0o640)
   image_config.install(root,'example.test',8558);image_config.install(root,'example.test',8558);config=json.loads(file.read_text())
   self.assertEqual(config['mcp']['keenable_search'],{'type':'remote','url':'https://api.keenable.ai/mcp-public','enabled':True,'oauth':False,'timeout':60000,'headers':{'X-Keenable-Title':'opencode-manatsu'}})
   self.assertEqual(config['mcp']['existing'],old['mcp']['existing']);self.assertEqual(config['permission'],old['permission']);self.assertEqual(file.stat().st_mode&0o777,0o640)
   self.assertEqual(config['instructions'],['/existing.md','/etc/opencode/IMAGE_SEARCH.md'])
 def test_primary_search_and_images_are_preserved(self):
  rule=image_config.INSTRUCTIONS
  for text in ('必须优先使用内置 websearch','不要禁用内置搜索','报错、超时、被限流','没有与问题相关的可用结果','keenable_search_search_web_pages','搜图仍必须使用上面的 image_search'):
   self.assertIn(text,rule)
 def test_limits_privacy_and_no_infinite_retries(self):
  for text in ('Retry-After','不连续重试或绕过限额','每小时 1000 次','私密数据','如实说明'):
   self.assertIn(text,image_config.INSTRUCTIONS)
 def test_install_and_purge_hooks(self):
  here=pathlib.Path(__file__).parent
  self.assertIn('keenable_search',(here/'install.sh').read_text())
  self.assertIn('install_image_search(root,host,port)',(here/'render.py').read_text())
  self.assertIn('Remote keenable_search',(here/'uninstall.sh').read_text())
  self.assertIn('$(path /etc/opencode)',(here/'uninstall.sh').read_text())

if __name__=='__main__':unittest.main()
