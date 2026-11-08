#!/usr/bin/env python3
"""Remove only this deployment's regular cached JPEG files older than seven days."""
import pathlib,re,stat,time
MAX_AGE_SECONDS=7*24*60*60

def cleanup(directory='/var/lib/opencode-images',now=None):
    root=pathlib.Path(directory)
    if root.is_symlink():raise ValueError('Image store must not be a symlink')
    if not root.exists():return 0
    cutoff=(time.time() if now is None else now)-MAX_AGE_SECONDS;removed=0
    for file in root.iterdir():
        if not re.fullmatch('[a-f0-9]{64}[.]jpg',file.name):continue
        info=file.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_mtime<cutoff:
            file.unlink();removed+=1
    return removed
if __name__=='__main__':print('Expired cached images removed:',cleanup())
