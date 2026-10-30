"""Keep a process group alive until its test and all descendants are cleaned up.

The helper waits for admission before launching the command. On Windows this
lets the parent assign a kill-on-close job before any test child can be created.
"""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


class WindowsJob:
    def __init__(self, process):
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", w.DWORD), ("min_working_set", ctypes.c_size_t), ("max_working_set", ctypes.c_size_t),
                        ("active_limit", w.DWORD), ("affinity", ctypes.c_size_t),
                        ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_ulonglong * 6), ("memory", ctypes.c_size_t * 4)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.api.CloseHandle(self.handle)
            self.handle = None
            raise

    def close(self):
        if self.handle:
            try:
                if not self.api.TerminateJobObject(self.handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
                # Basic accounting: four LARGE_INTEGERs followed by four DWORDs.
                data = ctypes.create_string_buffer(48)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if not self.api.QueryInformationJobObject(self.handle, 1, data, 48, None):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if ctypes.c_uint32.from_buffer(data, 40).value == 0:
                        return
                    time.sleep(0.01)
                raise RuntimeError("Owned test processes did not stop")
            finally:
                self.api.CloseHandle(self.handle)
                self.handle = None


class OwnedProcess:
    def __init__(self, argv, *, cwd=None, env=None, stdout=None, stderr=None, bufsize=0):
        from .private_state import secure
        self.directory = tempfile.TemporaryDirectory(prefix="chaosfolk-owned-")
        self.status = Path(self.directory.name) / "exit.json"
        self.job = None
        self.code = None
        self.closed = False
        self.process = None
        try:
            secure(self.status.parent, directory=True)
            self.process = subprocess.Popen(
                [getattr(sys, "_base_executable", sys.executable), "-I", str(Path(__file__).resolve()), str(self.status)],
                cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, bufsize=bufsize,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")
            if os.name == "nt":
                self.job = WindowsJob(self.process)
            self.process.stdin.write((json.dumps([os.fspath(x) for x in argv]) + "\n").encode())
            self.process.stdin.flush()
        except BaseException:
            self.close()
            raise
        self.pid, self.stdout = self.process.pid, self.process.stdout

    def poll(self):
        if self.code is None:
            try:
                self.code = json.loads(self.status.read_text(encoding="utf-8"))
            except FileNotFoundError:
                self.code = self.process.poll()
        return self.code

    @property
    def returncode(self):
        return self.poll()

    def wait(self, timeout=None):
        deadline = time.monotonic() + timeout if timeout is not None else None
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("owned test", timeout)
            time.sleep(0.01)
        return self.code

    def kill(self):
        self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.job:
                self.job.close()
            elif self.process and self.process.poll() is None:
                if os.name != "nt":
                    os.killpg(self.process.pid, signal.SIGKILL)
                else:
                    self.process.kill()
        finally:
            if self.process:
                self.process.wait(timeout=5)
                if self.process.stdin:
                    self.process.stdin.close()
            self.directory.cleanup()


def _helper(status):
    argv = json.loads(sys.stdin.buffer.readline())
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        code = process.wait()
    except OSError:
        code = 127
    temporary = status.with_suffix(".tmp")
    temporary.write_text(json.dumps(code), encoding="utf-8")
    temporary.replace(status)
    # Retain the group's root identity until the parent has cleaned up the job.
    sys.stdin.buffer.read()


if __name__ == "__main__":
    _helper(Path(sys.argv[1]))
