"""Reader for Firefly/GAMESS-style input: $GROUP ... $END -> dictionaries.

Rules:
  * a group starts with $NAME and ends with $END, case-insensitive;
    several groups may share one line, one group may span many lines;
  * inside a keyword group: KEY=VALUE pairs separated by blanks,
    KEY(n)=v1,v2,... for arrays;
  * text after '!' up to the end of the line is a comment;
  * $DATA and $VEC are kept as raw lines;
  * unknown groups and keys are errors, never silently skipped.
"""

import re

from ffpy.errors import InputError, UnsupportedError
from ffpy.schema import IGNORED, RAW_GROUPS, SCHEMA, UNSUPPORTED_GROUPS

_GROUP_RE = re.compile(r"\$(\w+)")
_END_RE = re.compile(r"\$END\b", re.I)
_PAIR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)(?:\((\d+)\))?=(.+)$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([EeDd][+-]?\d+)?$")
_INT_RE = re.compile(r"^[+-]?\d+$")


class Group:
    def __init__(self, name, line):
        self.name = name
        self.line = line
        self.keys = {}      # KEY -> python value
        self.raw = {}       # KEY -> text as written
        self.lines = []     # raw groups only
        self._text = []


class Deck:
    """Parsed input. Use get() so that applied defaults are reported."""

    def __init__(self, text):
        self.text = text
        self.groups = {}
        self.notes = []          # (kind, message) collected while parsing
        self.defaults_used = []  # "$GROUP KEY=value"

    def has(self, group):
        return group in self.groups

    def explicit(self, group, key):
        g = self.groups.get(group)
        return g is not None and key in g.keys

    def get(self, group, key, report_default=True):
        g = self.groups.get(group)
        if g is not None and key in g.keys:
            return g.keys[key]
        spec = SCHEMA[group][key]
        if report_default and spec.default is not None:
            self.defaults_used.append("$%s %s=%s" % (group, key, fmt_value(spec.default)))
        return spec.default


def fmt_value(v):
    if isinstance(v, bool):
        return ".TRUE." if v else ".FALSE."
    if isinstance(v, list):
        return ",".join(fmt_value(x) for x in v)
    if isinstance(v, float):
        return "%g" % v
    return str(v)


def _convert(token):
    t = token.strip()
    u = t.upper()
    if u in (".T.", ".TRUE.", "T", "TRUE"):
        return True
    if u in (".F.", ".FALSE.", "F", "FALSE"):
        return False
    if _INT_RE.match(t):
        return int(t)
    if _FLOAT_RE.match(t):
        return float(u.replace("D", "E"))
    return u


def _typed(group, key, value, raw):
    spec = SCHEMA[group][key]
    where = "$%s %s=%s" % (group, key, raw)
    vals = value if isinstance(value, list) else [value]
    if spec.type == "floatlist":
        out = []
        for v in vals:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise InputError("%s: expected numbers" % where)
            out.append(float(v))
        return out
    if len(vals) != 1:
        raise InputError("%s: a single value is expected" % where)
    v = vals[0]
    if spec.type == "int":
        if isinstance(v, bool) or not isinstance(v, int):
            raise InputError("%s: an integer is expected" % where)
    elif spec.type == "float":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise InputError("%s: a number is expected" % where)
        v = float(v)
    elif spec.type == "bool":
        if not isinstance(v, bool):
            raise InputError("%s: .TRUE. or .FALSE. is expected" % where)
    elif spec.type == "str":
        v = str(v).upper() if not isinstance(v, str) else v
        if group == "CONTRL" and key == "DFTTYP":
            v = v.replace("-", "")
    if spec.choices is not None and v not in spec.choices:
        raise InputError("%s: allowed values are %s"
                         % (where, ", ".join(fmt_value(c) for c in spec.choices)))
    return v


def _parse_keywords(group, deck):
    text = " ".join(group._text)
    text = re.sub(r"\s*=\s*", "=", text)
    text = re.sub(r"\s*,\s*", ",", text)
    schema = SCHEMA[group.name]
    for tok in text.split():
        m = _PAIR_RE.match(tok)
        if not m:
            raise InputError("$%s (line %d): cannot read '%s', expected KEY=VALUE"
                             % (group.name, group.line, tok))
        key, index, rawval = m.group(1).upper(), m.group(2), m.group(3)
        if key in IGNORED.get(group.name, ()):
            deck.notes.append(("warning", "$%s %s=%s is accepted but has no effect in ffpy"
                               % (group.name, key, rawval)))
            continue
        if key not in schema:
            raise InputError("$%s: unknown keyword %s. Known keywords: %s"
                             % (group.name, key, ", ".join(sorted(schema))))
        if key in group.keys:
            raise InputError("$%s: keyword %s given twice" % (group.name, key))
        parts = [_convert(p) for p in rawval.split(",") if p != ""]
        value = parts if (len(parts) > 1 or schema[key].type == "floatlist") else parts[0]
        if index is not None and int(index) != 1:
            raise UnsupportedError("$%s %s(%s)=...: arrays must start at index 1"
                                   % (group.name, key, index))
        group.keys[key] = _typed(group.name, key, value, rawval)
        group.raw[key] = rawval


def parse_input(text):
    deck = Deck(text)
    current = None
    for lineno, rawline in enumerate(text.splitlines(), 1):
        line = rawline.split("!", 1)[0].rstrip()
        if current is not None and current.name in RAW_GROUPS:
            m = _END_RE.search(line)
            if not m:
                current.lines.append(line)
                continue
            if line[:m.start()].strip():
                current.lines.append(line[:m.start()])
            deck.groups[current.name] = current
            current = None
            line = line[m.end():]
            if not line.strip():
                continue
        pos = 0
        while pos <= len(line):
            if current is None:
                m = _GROUP_RE.search(line, pos)
                if not m:
                    if line[pos:].strip():
                        deck.notes.append(("warning", "line %d: text outside of any group "
                                           "ignored: %s" % (lineno, line[pos:].strip())))
                    break
                if line[pos:m.start()].strip():
                    deck.notes.append(("warning", "line %d: text outside of any group "
                                       "ignored: %s" % (lineno, line[pos:m.start()].strip())))
                name = m.group(1).upper()
                if name == "END":
                    raise InputError("line %d: $END without an open group" % lineno)
                if m.start() == 0:
                    deck.notes.append(("warning", "line %d: $%s starts in column 1; "
                                       "Firefly expects column 2 or later" % (lineno, name)))
                if name in UNSUPPORTED_GROUPS:
                    raise UnsupportedError("$%s (%s) is not supported by ffpy"
                                           % (name, UNSUPPORTED_GROUPS[name]))
                if name not in SCHEMA and name not in RAW_GROUPS:
                    raise InputError("line %d: unknown group $%s. Supported groups: %s"
                                     % (lineno, name, ", ".join(
                                         "$" + g for g in sorted(set(SCHEMA) | RAW_GROUPS))))
                if name in deck.groups:
                    raise InputError("line %d: group $%s given twice" % (lineno, name))
                current = Group(name, lineno)
                if name in RAW_GROUPS:
                    # the rest of the $DATA/$VEC line is not used
                    break
                pos = m.end()
            else:
                m = _END_RE.search(line, pos)
                nxt = _GROUP_RE.search(line, pos)
                if nxt and (not m or nxt.start() < m.start()):
                    raise InputError("line %d: $%s opened at line %d is missing $END"
                                     % (lineno, current.name, current.line))
                if not m:
                    current._text.append(line[pos:])
                    break
                current._text.append(line[pos:m.start()])
                deck.groups[current.name] = current
                _parse_keywords(current, deck)
                current = None
                pos = m.end()
    if current is not None:
        raise InputError("$%s opened at line %d is missing $END" % (current.name, current.line))
    if "DATA" not in deck.groups:
        raise InputError("$DATA group is missing")
    return deck
