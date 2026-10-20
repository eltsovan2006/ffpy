"""The .out log: one writer for the file, optionally echoed to the console."""

import sys


class Log:
    def __init__(self, path=None, echo=True):
        self.path = path
        self.echo = echo
        self._fh = open(path, "w", encoding="utf-8", newline="\n") if path else None
        self.warnings = []

    def write(self, text=""):
        for line in str(text).split("\n"):
            line = line.rstrip()
            if self._fh:
                self._fh.write(line + "\n")
            if self.echo:
                try:
                    sys.stdout.write(line + "\n")
                except UnicodeEncodeError:
                    sys.stdout.write(line.encode("ascii", "replace").decode() + "\n")
        if self._fh:
            self._fh.flush()
        if self.echo:
            sys.stdout.flush()

    __call__ = write

    def blank(self):
        self.write("")

    def section(self, title):
        self.write("")
        self.write(" " + "-" * (len(title) + 4))
        self.write("  " + title.upper())
        self.write(" " + "-" * (len(title) + 4))

    def warning(self, msg):
        """Every warning goes on its own line starting with WARNING."""
        self.warnings.append(msg)
        self.write(" WARNING: " + msg)

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None


class NullLog(Log):
    def __init__(self):
        super().__init__(None, echo=False)
