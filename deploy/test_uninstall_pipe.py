"""Standalone uninstall: default full removal, one /dev/tty confirmation (Enter = yes), --yes, --keep-data."""
import os,pathlib,pty,select,subprocess,tempfile,time,unittest
HERE=pathlib.Path(__file__).resolve().parent
SRC=(HERE/'uninstall.sh').read_bytes()
DATA=('etc/opencode','var/lib/opencode','var/lib/opencode-images','var/lib/opencode-auth','var/cache/opencode')
def tree(t):
 root=pathlib.Path(t)/'root'
 for d in DATA+('opt/opencode/deploy','var/lib/opencode-web','etc/systemd/system','usr/local/bin','home/octo'):(root/d).mkdir(parents=True,exist_ok=True)
 (root/'etc/opencode/opencode.json').write_text('{}');(root/'etc/systemd/system/opencode.service').write_text('');(root/'etc/systemd/system/octo.service').write_text('')
 (root/'usr/local/bin/opencode-uninstall').write_bytes(SRC);(root/'usr/local/bin/img-search').write_text('x');(root/'home/octo/keep').write_text('x')
 return root
def gone(root):return not any((root/d).exists() for d in DATA+('opt/opencode','var/lib/opencode-web','etc/systemd/system/opencode.service','usr/local/bin/opencode-uninstall'))
def untouched(root):return all((root/p).exists() for p in ('home/octo/keep','usr/local/bin/img-search','etc/systemd/system/octo.service'))
def piped_with_tty(root,answer):
 """Like `curl ... | sudo bash`: script on stdin (a pipe), confirmation read from the controlling pty."""
 r,w=os.pipe();pid,fd=pty.fork()
 if pid==0:
  os.close(w);os.dup2(r,0);os.environ['DESTDIR']=str(root);os.execvp('bash',['bash'])
 os.close(r);os.write(w,SRC);os.close(w);out=b'';sent=False;deadline=time.time()+20
 while time.time()<deadline:
  ready,_,_=select.select([fd],[],[],0.2)
  if ready:
   try:chunk=os.read(fd,4096)
   except OSError:break
   if not chunk:break
   out+=chunk
  if not sent and '[Y/n]'.encode() in out:os.write(fd,answer);sent=True
 _,status=os.waitpid(pid,0);return os.waitstatus_to_exitcode(status),out.decode(errors='replace')
class Tests(unittest.TestCase):
 def test_piped_enter_confirms_full_removal(self):
  with tempfile.TemporaryDirectory() as t:
   root=tree(t);code,out=piped_with_tty(root,b'\r')
   self.assertEqual(code,0,out);self.assertIn('确定要彻底卸载 OpenCode 吗',out);self.assertTrue(gone(root));self.assertTrue(untouched(root))
 def test_piped_n_cancels_and_keeps_everything(self):
  with tempfile.TemporaryDirectory() as t:
   root=tree(t);code,out=piped_with_tty(root,b'n\r')
   self.assertNotEqual(code,0);self.assertIn('Cancelled',out);self.assertTrue(all((root/d).exists() for d in DATA+('usr/local/bin/opencode-uninstall',)))
 def test_no_tty_requires_yes(self):
  with tempfile.TemporaryDirectory() as t:
   root=tree(t);env={**os.environ,'DESTDIR':str(root)}
   r=subprocess.run(['setsid','-w','bash','-s'],input=SRC,env=env,capture_output=True)
   self.assertNotEqual(r.returncode,0);self.assertIn(b'--yes',r.stderr);self.assertTrue((root/'etc/opencode').exists())
   r=subprocess.run(['setsid','-w','bash','-s','--','--yes'],input=SRC,env=env,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(gone(root));self.assertTrue(untouched(root))
 def test_keep_data(self):
  with tempfile.TemporaryDirectory() as t:
   root=tree(t);r=subprocess.run(['bash','-s','--','--yes','--keep-data'],input=SRC,env={**os.environ,'DESTDIR':str(root)},capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   self.assertTrue(all((root/d).exists() for d in DATA));self.assertFalse((root/'opt/opencode').exists());self.assertFalse((root/'usr/local/bin/opencode-uninstall').exists())
 def test_rejects_bad_destdir_and_option(self):
  for env,args in (({'DESTDIR':'/'},['--yes']),({'DESTDIR':'/tmp/x'},['--bogus'])):
   self.assertNotEqual(subprocess.run(['bash','-s','--',*args],input=SRC,env={**os.environ,**env},capture_output=True).returncode,0)
 def test_standalone_no_helper_sourcing(self):
  self.assertNotIn(b'source ',SRC);self.assertIn(b'/usr/local/bin/opencode-uninstall',(HERE/'install.sh').read_bytes())
if __name__=='__main__':unittest.main()
