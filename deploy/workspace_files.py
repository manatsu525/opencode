#!/usr/bin/env python3
"""Workspace browser for the auth sidecar: list directories, stream exact bytes, inspect and delete entries.

Every path is resolved component by component with openat(dir_fd, name, O_NOFOLLOW) starting
from a directory fd for the workspace root, so symlinks (at any depth), '..', absolute paths and
rename races cannot escape the root. Only regular files are served; FIFOs/devices/sockets are
refused (O_NONBLOCK prevents blocking on FIFOs before the fstat check).

Deletion works on the same descriptors: unlinkat/rmdir relative to a directory fd, never by path. The root itself
and a symlink named directly as the target are refused; inside a folder, symlinks are unlinked and never followed.
A directory that is swapped (for a symlink or another inode) or sits on a different mount aborts the deletion."""
import errno, os, stat, urllib.parse

CHUNK = 1 << 20
MAX_ENTRIES = 5000
MAX_PATH = 4096
MAX_COUNT = 200000
MAX_DEPTH = 256
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK | getattr(os, 'O_NOCTTY', 0)

class Refused(Exception):
    def __init__(self, status, reason):
        super().__init__(reason); self.status = status; self.reason = reason

def components(value):
    """Split a client path (relative to the workspace) into validated names."""
    if not isinstance(value, str) or len(value) > MAX_PATH: raise Refused(400, 'invalid path')
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or '\\' in value: raise Refused(400, 'invalid path')
    if value.startswith('/'): raise Refused(400, 'absolute paths are not allowed')
    parts = [part for part in value.split('/') if part not in ('', '.')]
    if any(part == '..' for part in parts): raise Refused(400, 'parent references are not allowed')
    return parts

def open_root(root):
    try: return os.open(root, DIR_FLAGS)
    except OSError: raise Refused(503, 'workspace unavailable')

def walk(root, parts):
    """Return a directory fd for parts; every component must be a real (non-symlink) directory."""
    fd = open_root(root)
    try:
        for name in parts:
            try: child = os.open(name, DIR_FLAGS, dir_fd=fd)
            except OSError as error: raise Refused(404 if error.errno == errno.ENOENT else 403, 'not a directory inside the workspace')
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise

def list_directory(root, value):
    parts = components(value)
    fd = walk(root, parts)
    try:
        entries = []
        with os.scandir(fd) as items:
            for item in items:
                if len(entries) >= MAX_ENTRIES: break
                try: item.name.encode('utf-8')
                except UnicodeEncodeError: continue  # non-UTF-8 names cannot round-trip through URLs
                try: info = os.stat(item.name, dir_fd=fd, follow_symlinks=False)
                except OSError: continue
                mode = info.st_mode
                kind = 'directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else 'other'
                entries.append({'name': item.name, 'path': '/'.join(parts + [item.name]), 'type': kind, 'size': info.st_size if kind == 'file' else None, 'mtime': int(info.st_mtime)})
        entries.sort(key=lambda e: (e['type'] != 'directory', e['name'].lower()))
        return {'path': '/'.join(parts), 'entries': entries, 'truncated': len(entries) >= MAX_ENTRIES}
    finally:
        os.close(fd)

def open_file(root, value):
    parts = components(value)
    if not parts: raise Refused(400, 'a file path is required')
    fd = walk(root, parts[:-1])
    try:
        try: file = os.open(parts[-1], FILE_FLAGS, dir_fd=fd)
        except OSError as error:
            raise Refused(404 if error.errno == errno.ENOENT else 403, 'not a regular file inside the workspace')
    finally:
        os.close(fd)
    info = os.fstat(file)
    if not stat.S_ISREG(info.st_mode):
        os.close(file); raise Refused(403, 'only regular files can be downloaded')
    return file, info.st_size, parts[-1]

def disposition(name):
    fallback = ''.join(c if 32 <= ord(c) < 127 and c not in '"\\;%' else '_' for c in name) or 'download'
    return 'attachment; filename="' + fallback + '"; filename*=UTF-8\'\'' + urllib.parse.quote(name, safe='')

def download_headers(name, size):
    return {
        'Content-Type': 'application/octet-stream',
        'Content-Length': str(size),
        'Content-Disposition': disposition(name),
        'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "sandbox; default-src 'none'",
        'Cache-Control': 'no-store',
        'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'no-referrer',
    }

def stream(file, size, output):
    """Copy exactly size bytes (a file growing during transfer is truncated to its fstat size)."""
    remaining = size
    while remaining > 0:
        chunk = os.read(file, min(CHUNK, remaining))
        if not chunk: raise OSError('file shrank during download')
        output.write(chunk); remaining -= len(chunk)

def _target(root, value):
    """Parent directory fd, name and lstat of a non-root entry; refuses the root and a top-level symlink."""
    parts = components(value)
    if not parts: raise Refused(400, 'root')
    parent = walk(root, parts[:-1])
    try:
        try: info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except OSError as error: raise Refused(404 if error.errno == errno.ENOENT else 403, 'missing')
        if stat.S_ISLNK(info.st_mode): raise Refused(400, 'symlink')
        return parent, parts, info
    except BaseException:
        os.close(parent); raise

def _kind(mode):
    return 'directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else 'other'

def _open_dir(fd, name, expect, device):
    """Open a child directory without following links; it must be the inode lstat saw, on the workspace mount."""
    try: child = os.open(name, DIR_FLAGS, dir_fd=fd)
    except OSError: raise Refused(409, 'changed')
    info = os.fstat(child)
    if (info.st_dev, info.st_ino) != (expect.st_dev, expect.st_ino):
        os.close(child); raise Refused(409, 'changed')
    if info.st_dev != device:
        os.close(child); raise Refused(403, 'mount')
    return child

def _count(fd, totals, depth, device):
    if depth > MAX_DEPTH: raise Refused(400, 'too deep')
    with os.scandir(fd) as items:
        names = [item.name for item in items]
    for name in names:
        if totals['files'] + totals['directories'] + totals['symlinks'] >= MAX_COUNT:
            totals['truncated'] = True; return
        try: info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except OSError: continue
        if stat.S_ISDIR(info.st_mode):
            totals['directories'] += 1
            if info.st_dev != device: continue
            try: child = _open_dir(fd, name, info, device)
            except Refused: continue
            try: _count(child, totals, depth + 1, device)
            finally: os.close(child)
        elif stat.S_ISLNK(info.st_mode): totals['symlinks'] += 1
        else:
            totals['files'] += 1; totals['bytes'] += info.st_size

def inspect(root, value):
    """Type, size and (for folders) recursive counts of what deleting value would remove."""
    parent, parts, info = _target(root, value)
    try:
        result = {'path': '/'.join(parts), 'type': _kind(info.st_mode), 'files': 0, 'directories': 0, 'symlinks': 0, 'bytes': 0, 'truncated': False}
        if stat.S_ISREG(info.st_mode):
            result['files'] = 1; result['bytes'] = info.st_size
        elif stat.S_ISDIR(info.st_mode):
            device = os.fstat(parent).st_dev
            if info.st_dev != device: raise Refused(403, 'mount')
            child = _open_dir(parent, parts[-1], info, device)
            try: _count(child, result, 1, device)
            finally: os.close(child)
        else: raise Refused(403, 'unsupported')
        return result
    finally:
        os.close(parent)

def _purge(fd, totals, depth, device):
    if depth > MAX_DEPTH: raise Refused(400, 'too deep')
    with os.scandir(fd) as items:
        names = [item.name for item in items]
    for name in names:
        try: info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError: continue
        if stat.S_ISDIR(info.st_mode):
            child = _open_dir(fd, name, info, device)
            try: _purge(child, totals, depth + 1, device)
            finally: os.close(child)
            os.rmdir(name, dir_fd=fd); totals['directories'] += 1
        else:
            # unlinkat never follows a symlink: the link goes, its target stays.
            os.unlink(name, dir_fd=fd)
            totals['symlinks' if stat.S_ISLNK(info.st_mode) else 'files'] += 1

def delete(root, value, expected):
    """Delete a file, or a folder recursively; expected is the type the user confirmed."""
    parent, parts, info = _target(root, value)
    try:
        kind = _kind(info.st_mode)
        if expected not in ('file', 'directory'): raise Refused(400, 'invalid type')
        if kind != expected: raise Refused(409, 'changed')
        totals = {'files': 0, 'directories': 0, 'symlinks': 0}
        if kind == 'file':
            os.unlink(parts[-1], dir_fd=parent); totals['files'] = 1
            return totals
        device = os.fstat(parent).st_dev
        if info.st_dev != device: raise Refused(403, 'mount')
        child = _open_dir(parent, parts[-1], info, device)
        try: _purge(child, totals, 1, device)
        finally: os.close(child)
        try: os.rmdir(parts[-1], dir_fd=parent)
        except OSError: raise Refused(409, 'changed')
        totals['directories'] += 1
        return totals
    except PermissionError: raise Refused(403, 'permission')
    finally:
        os.close(parent)
