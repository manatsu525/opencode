#!/usr/bin/env python3
"""Extract deployment files, never links/devices/absolute paths or parent traversal."""
import pathlib, shutil, sys, tarfile
archive, destination = sys.argv[1:]
root = pathlib.Path(destination).resolve()
root.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive, "r:gz") as tf:
    members = tf.getmembers()
    if len(members) > 20000 or sum(m.size for m in members) > 1024**3:
        raise SystemExit("Archive exceeds deployment size limits")
    for member in members:
        name = pathlib.PurePosixPath(member.name)
        if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
            raise SystemExit("Unsafe archive member")
        target = root.joinpath(*name.parts)
        if target.is_symlink() or (target != root and root not in target.resolve().parents):
            raise SystemExit("Unsafe archive destination")
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tf.extractfile(member) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        target.chmod(0o644)
