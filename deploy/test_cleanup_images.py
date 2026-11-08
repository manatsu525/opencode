import os,pathlib,tempfile,unittest
from cleanup_images import cleanup,MAX_AGE_SECONDS
class Tests(unittest.TestCase):
 def test_only_expired_regular_sha_jpeg_files(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);now=2_000_000_000
   old=root/('a'*64+'.jpg');fresh=root/('b'*64+'.jpg');exact=root/('c'*64+'.jpg');other=root/'keep.jpg';symlink=root/('d'*64+'.jpg')
   for p in (old,fresh,exact,other):p.write_bytes(b'image')
   for p in (old,other):os.utime(p,(now-MAX_AGE_SECONDS-1,)*2)
   os.utime(fresh,(now,now));os.utime(exact,(now-MAX_AGE_SECONDS,)*2);symlink.symlink_to(other)
   self.assertEqual(cleanup(root,now),1);self.assertFalse(old.exists());self.assertTrue(all(p.exists() for p in (fresh,exact,other,symlink)))
 def test_installer_and_uninstaller_wire_daily_timer(self):
  here=pathlib.Path(__file__).parent
  rendered=(here/'render.py').read_text();self.assertIn('OnCalendar=daily',rendered);self.assertIn('Persistent=true',rendered);self.assertIn('ReadWritePaths=/var/lib/opencode-images',rendered)
  self.assertIn('enable --now opencode-image-cleanup.timer',(here/'install.sh').read_text());self.assertIn('disable --now opencode-image-cleanup.timer',(here/'uninstall.sh').read_text())
 def test_store_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);(root/'link').symlink_to(root,target_is_directory=True)
   with self.assertRaises(ValueError):cleanup(root/'link')
if __name__=='__main__':unittest.main()
