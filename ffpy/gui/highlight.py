"""Syntax highlighting for .inp inputs and .out logs."""

import re

from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat

from ffpy.gui.theme import color

_GROUP = re.compile(r"\$(\w+)")
_KEY = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)(\(\d+\))?\s*=")
_NUMBER = re.compile(r"(?<![\w.])[+-]?(\d+\.?\d*|\.\d+)([EeDd][+-]?\d+)?(?![\w.])")
_BOOL = re.compile(r"\.(TRUE|FALSE|T|F)\.", re.I)
_RAW = {"DATA", "VEC"}

DASHES = 2
RAW0 = 100


def _fmt(name, bold=False, italic=False):
    f = QTextCharFormat()
    f.setForeground(color(name))
    if bold:
        f.setFontWeight(QFont.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class InpHighlighter(QSyntaxHighlighter):
    """$GROUP/$END, KEY=, numbers, logicals, ! comments; atom names in $DATA."""

    def __init__(self, document):
        super().__init__(document)
        self.refresh_colors()

    def refresh_colors(self):
        self.f_group = _fmt("group", bold=True)
        self.f_key = _fmt("key")
        self.f_num = _fmt("number")
        self.f_bool = _fmt("bool")
        self.f_comment = _fmt("comment", italic=True)
        self.f_atom = _fmt("atom", bold=True)
        self.f_title = _fmt("atom", italic=True)
        self.rehighlight()

    def highlightBlock(self, text):
        # block state: 0 outside raw groups, RAW0 + n on the n-th line after $DATA/$VEC
        prev = self.previousBlockState()
        in_raw = prev >= RAW0
        n = prev - RAW0 + 1 if in_raw else 0
        cut = text.find("!")
        code = text if cut < 0 else text[:cut]
        if cut >= 0:
            self.setFormat(cut, len(text) - cut, self.f_comment)

        groups = list(_GROUP.finditer(code))
        if in_raw and not any(g.group(1).upper() == "END" for g in groups):
            if n == 1:                      # title line
                self.setFormat(0, len(code), self.f_title)
            elif n == 2:                    # point group line
                self.setFormat(0, len(code), self.f_key)
            else:
                tok = re.match(r"\s*(\S+)", code)
                if tok and not re.match(r"^\s*\d", code):
                    self.setFormat(tok.start(1), len(tok.group(1)), self.f_atom)
                for m in _NUMBER.finditer(code):
                    if not tok or m.start() >= tok.end(1):
                        self.setFormat(m.start(), m.end() - m.start(), self.f_num)
            self.setCurrentBlockState(RAW0 + min(n, 1000))
            return

        state = 0
        for g in groups:
            self.setFormat(g.start(), g.end() - g.start(), self.f_group)
            name = g.group(1).upper()
            if name in _RAW:
                state = RAW0
            elif name == "END":
                state = 0
        if state != RAW0:
            for m in _KEY.finditer(code):
                self.setFormat(m.start(1), m.end(1) - m.start(1), self.f_key)
            for m in _NUMBER.finditer(code):
                self.setFormat(m.start(), m.end() - m.start(), self.f_num)
            for m in _BOOL.finditer(code):
                self.setFormat(m.start(), m.end() - m.start(), self.f_bool)
        self.setCurrentBlockState(state)


class OutHighlighter(QSyntaxHighlighter):
    """Warnings, errors, section headers, termination line, echoed input."""

    def __init__(self, document):
        super().__init__(document)
        self.refresh_colors()

    def refresh_colors(self):
        self.f_warn = _fmt("warning", bold=True)
        self.f_err = _fmt("error", bold=True)
        self.f_ok = _fmt("ok", bold=True)
        self.f_head = _fmt("header", bold=True)
        self.f_muted = _fmt("muted")
        self.f_accent = _fmt("accent", bold=True)
        self.f_bold = QTextCharFormat()
        self.f_bold.setFontWeight(QFont.Bold)
        self.rehighlight()

    def highlightBlock(self, text):
        s = text.strip()
        n = len(text)
        state = 0
        if s and set(s) <= {"-", "="}:
            self.setFormat(0, n, self.f_muted)
            state = DASHES
        elif s.startswith("WARNING"):
            self.setFormat(0, n, self.f_warn)
        elif s.startswith("ERROR") or "TERMINATED ABNORMALLY" in s:
            self.setFormat(0, n, self.f_err)
        elif "TERMINATED NORMALLY" in s or "OPTIMIZATION CONVERGED" in s:
            self.setFormat(0, n, self.f_ok)
        elif text.startswith("  | "):
            self.setFormat(0, n, self.f_muted)
        elif self.previousBlockState() == DASHES and s and s == s.upper() and any(c.isalpha() for c in s):
            self.setFormat(0, n, self.f_head)
        elif s.startswith("FINAL ENERGY") or s.startswith("TOTAL ") and "ENERGY" in s:
            self.setFormat(0, n, self.f_bold)
        for tag in ("HOMO", "LUMO"):
            i = text.find(tag)
            if i >= 0 and text.rstrip().endswith(tag):
                self.setFormat(i, len(tag), self.f_accent)
        self.setCurrentBlockState(state)
