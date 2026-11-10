import os,pathlib,subprocess,tempfile,unittest
HERE=pathlib.Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def test_piped_purge_without_sibling_common(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t)/'root'
   for d in ('etc/opencode','var/lib/opencode/workspace','var/lib/opencode-images','var/lib/opencode-auth','var/cache/opencode','opt/opencode/deploy','etc/systemd/system'):(root/d).mkdir(parents=True)
   (root/'etc/opencode/opencode.json').write_text('{}');(root/'etc/systemd/system/opencode.service').write_text('')
   keep=root/'home/octo/keep';keep.parent.mkdir(parents=True);keep.write_text('x')
   r=subprocess.run(['bash','-s','--','--yes','--purge'],input=(HERE/'uninstall.sh').read_bytes(),cwd=t,env={**os.environ,'DESTDIR':str(root)},capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr.decode())
   for d in ('etc/opencode','var/lib/opencode','var/lib/opencode-images','var/lib/opencode-auth','var/cache/opencode','opt/opencode','etc/systemd/system/opencode.service'):self.assertFalse((root/d).exists(),d)
   self.assertTrue(keep.exists())
 def test_piped_requires_yes_and_rejects_bad_destdir(self):
  src=(HERE/'uninstall.sh').read_bytes()
  self.assertNotEqual(subprocess.run(['bash','-s'],input=src,env={**os.environ,'DESTDIR':'/tmp/x'},capture_output=True).returncode,0)
  self.assertNotEqual(subprocess.run(['bash','-s','--','--yes'],input=src,env={**os.environ,'DESTDIR':'/'},capture_output=True).returncode,0)
if __name__=='__main__':unittest.main()
