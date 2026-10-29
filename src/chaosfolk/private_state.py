"""Owner-only session state; never change permissions on the source repository."""
import ctypes
import errno
from functools import lru_cache
import os
from pathlib import Path
import json
import tempfile
import time


@lru_cache(maxsize=1)
def _windows_security():
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    advapi.SetFileSecurityW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.c_void_p]
    token, size = w.HANDLE(), w.DWORD()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        data = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, data, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p))[0]
        text = w.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            owner = text.value
        finally:
            kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
    finally:
        kernel.CloseHandle(token)
    return kernel, advapi, owner


def secure(path, directory=False):
    path = Path(path)
    if os.name != "nt":
        path.chmod(0o700 if directory else 0o600)
        return
    kernel, advapi, owner = _windows_security()
    descriptor = ctypes.c_void_p()
    inheritance = "OICI" if directory else ""
    sddl = "D:P" + "".join(f"(A;{inheritance};FA;;;{sid})" for sid in (owner, "SY", "BA"))
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not advapi.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)


def session_directory(path):
    path = Path(path).resolve()
    known = any((path / name).exists() for name in ("audit.sqlite3", "journal.jsonl", "serveur.json"))
    if ((path / ".git").exists() or path.parent == path or path == Path.home().resolve()
            or (path == Path.cwd().resolve() and not known)):
        raise ValueError("Choose a dedicated session directory outside the repository root")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    secure(path, directory=True)
    # Existing session files may retain inherited ACLs even after the directory
    # is protected. Refuse links: later writers use fixed paths in this tree.
    for parent, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            child = Path(parent) / name
            if child.is_symlink() or child.is_junction():
                raise ValueError("Private session state must not contain symbolic links or junctions")
            if child.is_file() and child.stat().st_nlink > 1:
                raise ValueError("Private session state must not be hard-linked outside the session")
            secure(child, directory=child.is_dir())
    return path


def _sharing_retry(operation):
    """Allow a Windows reader/replacer to release its transient file handle."""
    deadline = time.monotonic() + 1
    while True:
        try:
            return operation()
        except PermissionError as error:
            code = getattr(error, "winerror", None)
            # Python's CRT-backed open can expose only EACCES, without the
            # original WinError, for the same replace/read sharing collision.
            sharing = code in {5, 32, 33} or (code is None and error.errno == errno.EACCES)
            if os.name != "nt" or not sharing or time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def read_json(path, *, encoding="utf-8"):
    return json.loads(_sharing_retry(lambda: Path(path).read_text(encoding=encoding)))


def write_json(path, value):
    path = Path(path)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".private-", delete=False) as stream:
            temporary = Path(stream.name)
            secure(temporary)
            stream.write(encoded)
        _sharing_retry(lambda: os.replace(temporary, path))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
