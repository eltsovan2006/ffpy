"""Runs ffpy jobs as child processes, one at a time, with a queue.

The child is ffpy.exe next to ffpy-gui.exe in the frozen build, or
"python -m ffpy" from a source checkout. Its log arrives line by line on
stdout (--pipe); a reader thread forwards it through Qt signals.
"""

import os
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal

CREATE_NO_WINDOW = 0x08000000


def ffpy_command():
    if getattr(sys, "frozen", False):
        exe = os.path.join(os.path.dirname(sys.executable), "ffpy.exe")
        return [exe]
    return [sys.executable, "-m", "ffpy"]


class RunManager(QObject):
    line = Signal(str)
    started = Signal(str)            # input path
    finished = Signal(str, int)      # input path, exit code (-1: stopped)
    queue_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.current = None
        self.queue = []
        self.threads = 8
        self.t_start = None
        self._stopped = False

    def is_running(self):
        return self.proc is not None

    def enqueue(self, paths):
        for p in paths:
            if p not in self.queue and p != self.current:
                self.queue.append(p)
        self.queue_changed.emit(len(self.queue))
        if not self.is_running():
            self._next()

    def _next(self):
        if not self.queue:
            return
        path = self.queue.pop(0)
        self.queue_changed.emit(len(self.queue))
        self._start(path)

    def _start(self, path):
        cmd = ffpy_command() + [path, "--pipe", "-n", str(self.threads)]
        env = dict(os.environ)
        if not getattr(sys, "frozen", False):
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        self.current = path
        self._stopped = False
        self.t_start = time.time()
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                cwd=os.path.dirname(os.path.abspath(path)), env=env, creationflags=flags)
        except OSError as e:
            self.proc = None
            self.line.emit("Не удалось запустить ffpy: %s (%s)" % (e, " ".join(cmd)))
            self.finished.emit(path, 9)
            self.current = None
            self._next()
            return
        self.started.emit(path)
        threading.Thread(target=self._read, args=(self.proc, path), daemon=True).start()

    def _read(self, proc, path):
        for raw in iter(proc.stdout.readline, b""):
            self.line.emit(raw.decode("utf-8", "replace").rstrip("\r\n"))
        code = proc.wait()
        if self._stopped:
            code = -1
        self.proc = None
        self.current = None
        self.finished.emit(path, code)
        self._next()

    def stop(self, clear_queue=True):
        if clear_queue:
            self.queue.clear()
            self.queue_changed.emit(0)
        if self.proc is not None:
            self._stopped = True
            try:
                self.proc.kill()
            except OSError:
                pass

    def elapsed(self):
        return time.time() - self.t_start if self.t_start and self.is_running() else 0.0
