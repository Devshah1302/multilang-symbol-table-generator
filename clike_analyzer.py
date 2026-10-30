"""
clike_analyzer.py - Phases 2 and 3 for C, C++, Java and JavaScript.

After the lexer has produced tokens, this analyzer walks through them once,
statement by statement, and:
  * recognises declarations of variables, constants, functions, parameters,
    classes, structs, imports and #include / #define lines,
  * stores every declared name in the SYMBOL TABLE,
  * checks every use of a name (is it declared? is it a constant? does the
    type of the value match?),
  * checks syntax rules such as missing semicolons and unmatched brackets.

Language differences come from the settings in languages.py and a few
`if self.java:` / `if self.js:` rules (for example, Java does not allow
storing a double in an int, JavaScript does not need semicolons).
"""
import re
from languages import LANGUAGES
from lexer import tokenize, Token

OPEN, CLOSE = "([{", ")]}"
PAIR = {")": "(", "]": "[", "}": "{", "(": ")", "[": "]", "{": "}"}
END_KINDS = {"IDENTIFIER", "INT", "FLOAT", "CHAR", "STRING", "BOOL", "NULL"}
NOT_STATEMENT_START = {"else", "catch", "finally", "instanceof", "extends", "implements",
                       "throws", "in", "of", "as", "from"}
JS_STATEMENT_WORDS = {"let", "const", "var", "function", "class", "if", "for", "while",
                      "return", "import", "export", "switch", "try", "throw", "do"}
COMPOUND_ASSIGN = {"+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", ">>>="}
RANK = {"byte": 1, "short": 2, "char": 2, "int": 3, "long": 4, "float": 5, "double": 6}
CPP_EXTRA_TYPES = {"exception", "runtime_error", "ostream", "istream", "ifstream", "ofstream"}


def category(type_text):
    """Group a type into: integer, decimal, char, bool, string, cstring or other."""
    if not type_text:
        return None
    if "<" in type_text:
        return "other"
    words = type_text.replace("*", " ").replace("&", " ").split("[")[0].split()
    if "*" in type_text or "[" in type_text:
        return "cstring" if "char" in words else "other"
    if "String" in words or "string" in words:
        return "string"
    if {"bool", "boolean", "_Bool"} & set(words):
        return "bool"
    if {"double", "float"} & set(words):
        return "decimal"
    if "char" in words:
        return "char"
    if words and set(words) <= {"int", "long", "short", "byte", "size_t", "signed", "unsigned"}:
        return "integer"
    return "other"


def numeric_name(type_text):
    for word in ("double", "float", "long", "short", "byte", "char"):
        if word in type_text.split():
            return word
    return "int"


class Block:
    """An internal { } block. Used only to know which names are visible;
    it is not shown to the user."""
    def __init__(self, kind, parent=None, func="inherit", cls="inherit"):
        self.kind = kind            # global, function, class, enum, block, header, init, object
        self.parent = parent
        self.names = {}
        self.func = (parent.func if parent else None) if func == "inherit" else func
        self.cls = (parent.cls if parent else None) if cls == "inherit" else cls
        self.extra_pops = 0
        self.statement = True
        self.typedef = False
        self.word = ""
        self.saved = None


class CLikeAnalyzer:
    def __init__(self, code, language):
        self.code, self.lang = code, language
        self.cfg = LANGUAGES[language]
        self.c, self.cpp = language == "C", language == "C++"
        self.java, self.js = language == "Java", language == "JavaScript"
        self.toks, self.errors = tokenize(code, self.cfg)
        self.warnings, self.symbols = [], []
        self.global_block = Block("global")
        self.blocks = [self.global_block]
        self.user_types = set(CPP_EXTRA_TYPES) if self.cpp else set()
        self.class_members = {}
        self.unresolved = []
        self.parens = []
        self.stmt_start, self.stmt_first, self.after_control = True, None, False
        self.pending_block, self.pending_headers = None, 0
        self.decl = None
        self.typedef_mode, self.after_type_body = False, None
        self.arrow_params, self.arrow_buffer = set(), []
        self.reported = set()

    # ------------------------------------------------------------ helpers
    def tok(self, i):
        if 0 <= i < len(self.toks):
            return self.toks[i]
        last = self.toks[-1].line if self.toks else 1
        return Token("EOF", "", last, len(self.code), len(self.code))

    def text(self, i):
        return self.tok(i).text

    def error(self, line, kind, message):
        key = ("E", line, kind, message)
        if key not in self.reported:
            self.reported.add(key)
            self.errors.append({"line": line, "type": kind, "message": message})

    def warn(self, line, kind, message):
        key = ("W", line, kind, message)
        if key not in self.reported:
            self.reported.add(key)
            self.warnings.append({"line": line, "type": kind, "message": message})

    def source(self, a, b):
        """Original source text from token a to token b (both included)."""
        if a > b or a >= len(self.toks):
            return ""
        b = min(b, len(self.toks) - 1)
        text = " ".join(self.code[self.toks[a].start:self.toks[b].end].split())
        return text if len(text) <= 45 else text[:42] + "..."

    def match_close(self, i):
        """Index of the bracket that closes the one at position i."""
        opener, depth = self.text(i), 0
        if opener not in OPEN:
            return None
        closer = PAIR[opener]
        for k in range(i, len(self.toks)):
            if self.toks[k].kind != "SEPARATOR":
                continue
            if self.toks[k].text == opener:
                depth += 1
            elif self.toks[k].text == closer:
                depth -= 1
                if depth == 0:
                    return k
        return None

    def match_open(self, i):
        closer, depth = self.text(i), 0
        if closer not in CLOSE:
            return None
        opener = PAIR[closer]
        for k in range(i, -1, -1):
            if self.toks[k].kind != "SEPARATOR":
                continue
            if self.toks[k].text == closer:
                depth += 1
            elif self.toks[k].text == opener:
                depth -= 1
                if depth == 0:
                    return k
        return None

    def match_angle(self, i):
        """Index of the '>' that closes the generic '<' at i (List<List<Integer>>)."""
        depth = 0
        for k in range(i, min(len(self.toks), i + 40)):
            t = self.toks[k].text
            if t == "<":
                depth += 1
            elif t in (">", ">>", ">>>"):
                depth -= len(t)
                if depth <= 0:
                    return k
            elif t in (";", "{", "}", "=", "(", ")"):
                return None
        return None

    def split_args(self, a, b):
        """Split tokens a..b-1 at top-level commas -> list of (start, end)."""
        parts, depth, start = [], 0, a
        for k in range(a, b):
            t = self.toks[k]
            if t.kind == "SEPARATOR" and t.text in OPEN:
                depth += 1
            elif t.kind == "SEPARATOR" and t.text in CLOSE:
                depth -= 1
            elif t.text == "," and depth == 0:
                parts.append((start, k))
                start = k + 1
        if start < b:
            parts.append((start, b))
        return parts

    def newline_break(self, k):
        """True if a new statement clearly starts at token k on a new line."""
        if k <= 0 or k >= len(self.toks):
            return False
        prev, cur = self.toks[k - 1], self.toks[k]
        if cur.line == prev.line:
            return False
        prev_ok = prev.kind in END_KINDS or prev.text in (")", "]", "++", "--", "this")
        cur_ok = cur.kind in ("IDENTIFIER", "TYPE") or (cur.kind == "KEYWORD" and cur.text not in NOT_STATEMENT_START)
        return prev_ok and cur_ok

    def expr_end(self, k):
        """Index where the expression starting at k ends (',' ';' or a closing bracket)."""
        depth, start = 0, k
        while k < len(self.toks):
            t = self.toks[k]
            if t.kind == "SEPARATOR" and t.text in OPEN:
                depth += 1
            elif t.kind == "SEPARATOR" and t.text in CLOSE:
                if depth == 0:
                    return k
                depth -= 1
            elif depth == 0 and t.kind == "SEPARATOR" and t.text in ",;":
                return k
            elif depth == 0 and k > start and self.newline_break(k):
                return k
            k += 1
        return k

    # ------------------------------------------------------------ symbol table
    def where(self, block):
        if block.func:
            return f"method {block.func}" if self.java else f"function {block.func}"
        return f"class {block.cls}" if block.cls else "the program"

    def add_symbol(self, name_tok, kind, vtype, block, const=False, word="", value="",
                   initialized=False):
        name, line = name_tok.text, name_tok.line
        old = block.names.get(name)
        if old is not None:
            if self.js and word == "var" and old.get("word") == "var":
                return old                                   # var may be declared again
            if self.js:
                msg = f"Identifier '{name}' has already been declared (SyntaxError)"
            elif self.java:
                msg = f"variable {name} is already defined in {self.where(block)} (line {old['line']})"
            else:
                msg = f"redefinition of '{name}' (first declared at line {old['line']})"
            self.error(line, "Duplicate Declaration", msg)
            return None
        if self.java and kind in ("variable", "constant") and block.func:
            b = block.parent                                 # Java: a local may not hide another local
            while b is not None and b.func == block.func and b.kind != "class":
                other = b.names.get(name)
                if other and other["kind"] in ("variable", "constant", "parameter"):
                    self.error(line, "Duplicate Declaration",
                               f"variable {name} is already defined in {self.where(block)} (line {other['line']})")
                    return None
                b = b.parent
        cat = category(vtype)
        sym = {"name": name, "kind": kind, "type": vtype or "-", "line": line, "value": value,
               "uses": 0, "initialized": initialized, "const": const, "word": word,
               "local": bool(block.func) or self.js,
               "scalar": cat in ("integer", "decimal", "char", "bool", "string") or (self.java and kind == "variable"),
               "body": False}
        block.names[name] = sym
        self.symbols.append(sym)
        if block.kind in ("class", "enum") and block.cls:
            self.class_members.setdefault(block.cls, {})[name] = sym
        return sym

    def lookup(self, name):
        for b in reversed(self.blocks):
            if name in b.names:
                return b.names[name]
        cls = self.blocks[-1].cls
        if cls and name in self.class_members.get(cls, {}):
            return self.class_members[cls][name]
        return None

    def member_lookup(self, name):
        for members in self.class_members.values():
            if name in members:
                return members[name]
        return None

    # ------------------------------------------------------------ type checking
    def infer(self, a, b):
        """Type of the expression in tokens a..b-1 as (category, name), or None if unknown."""
        if a >= b:
            return None
        cats, compare, plus = [], False, False
        for k in range(a, b):
            t, x = self.toks[k], self.toks[k].text
            if t.kind == "INT":
                cats.append(("integer", "long" if x[-1] in "lL" else "int"))
            elif t.kind == "FLOAT":
                cats.append(("decimal", "float" if x[-1] in "fF" else "double"))
            elif t.kind == "CHAR":
                cats.append(("char", "char"))
            elif t.kind == "STRING":
                cats.append(("string", "String" if self.java else "string"))
            elif t.kind == "BOOL":
                cats.append(("bool", "boolean" if self.java else "bool"))
            elif t.kind == "NULL":
                cats.append(("null", "null"))
            elif t.kind == "IDENTIFIER":
                if self.text(k + 1) in ("(", ".", "[", "->", "::") or self.text(k - 1) in (".", "->", "::"):
                    return None
                sym = self.lookup(x)
                if sym is None or sym["kind"] not in ("variable", "constant", "parameter", "field"):
                    return None
                cat = category(sym["type"])
                if cat in (None, "other", "cstring"):
                    return None
                cats.append((cat, "String" if cat == "string" and self.java else numeric_name(sym["type"])
                             if cat in ("integer", "decimal", "char") else sym["type"]))
            elif x in ("==", "!=", "<", ">", "<=", ">=", "&&", "||", "!"):
                compare = True
            elif x == "+":
                plus = True
            elif x in ("-", "*", "/", "%", "(", ")"):
                continue
            else:
                return None
        if not cats:
            return None
        if compare:
            return ("bool", "boolean") if self.java else ("bool", "bool") if self.cpp else ("integer", "int")
        kinds = {c for c, _ in cats}
        if "string" in kinds:
            if len(cats) == 1:
                return cats[0]
            return ("string", "String") if (self.java and plus) else None
        if kinds & {"null", "bool"}:
            return cats[0] if len(cats) == 1 else None
        if len(cats) == 1:
            return cats[0]
        best = max(cats, key=lambda c: RANK.get(c[1], 3))
        return ("integer", "int") if best[0] == "char" else best

    def check_types(self, sym, a, b, line, is_init):
        if self.js or sym is None:
            return
        expr = self.infer(a, b)
        target = sym["type"]
        tcat = category(target)
        if expr is None or tcat in (None, "other"):
            return
        ecat, ename = expr
        name = sym["name"]
        if self.java:
            msg = None
            if tcat == "string" and ecat not in ("string", "null"):
                msg = f"incompatible types: {ename} cannot be converted to String"
            elif ecat == "string" and tcat != "string":
                msg = f"incompatible types: String cannot be converted to {target}"
            elif (tcat == "bool") != (ecat == "bool"):
                msg = f"incompatible types: {ename} cannot be converted to {target}"
            elif ecat == "null" and tcat != "string":
                msg = f"incompatible types: <null> cannot be converted to {target}"
            elif tcat in ("integer", "decimal", "char") and ecat in ("integer", "decimal", "char"):
                t_name = numeric_name(target)
                int_to_small = ename == "int" and t_name in ("byte", "short", "char")
                if RANK.get(ename, 3) > RANK.get(t_name, 3) and not int_to_small:
                    msg = f"incompatible types: possible lossy conversion from {ename} to {t_name}"
            if msg:
                self.error(line, "Type Mismatch", msg)
            return
        # C and C++
        if ecat == "string":
            if tcat == "cstring" or (self.cpp and tcat == "string"):
                return
            self.error(line, "Type Mismatch", f"cannot store a string in '{name}' of type {target}")
        elif self.cpp and tcat == "string" and ecat in ("integer", "decimal", "char", "bool"):
            if is_init:
                self.error(line, "Type Mismatch", f"cannot convert {ename} to string for '{name}'")
            else:
                self.warn(line, "Type Mismatch", f"assigning a {ename} to string '{name}' stores a single character")
        elif tcat == "cstring" and ecat in ("decimal", "bool", "char"):
            self.error(line, "Type Mismatch", f"cannot store a {ename} in '{name}' of type {target}")
        elif tcat in ("integer", "char") and ecat == "decimal":
            self.warn(line, "Data Loss", f"'{name}' is {target}: the {ename} value will lose its decimal part")

    # ------------------------------------------------------------ main loop
    def run(self):
        self.check_brackets()
        if self.js or self.java:
            self.mark_arrow_params()
        i = 0
        while i < len(self.toks):
            t = self.toks[i]
            if t.kind == "PREPROCESSOR":
                self.preprocessor(t)
                self.stmt_start = True
                i += 1
                continue
            if t.kind == "ANNOTATION":
                i = (self.match_close(i + 1) or i) + 1 if self.text(i + 1) == "(" else i + 1
                continue
            if self.implied_break(i):
                prev = self.toks[i - 1]
                self.error(prev.line, "Syntax", f"Missing ';' at end of line {prev.line}")
                self.end_statement()
            elif self.js and not self.parens and self.blocks[-1].kind not in ("object", "init") and (
                    self.newline_break(i) or (t.line > self.tok(i - 1).line and t.text in JS_STATEMENT_WORDS)):
                self.end_statement()                         # JavaScript: a new line can end a statement
            self.after_control = False
            if self.stmt_start:
                self.stmt_first = t.text
                j = self.statement_start(i)
                if j is not None:
                    i = j
                    continue
                self.stmt_start = False
            i = self.scan(i)
        self.resolve_later_uses()
        self.unused_warnings()
        return self.result()

    def implied_break(self, i):
        """A statement ended without ';' (C, C++, Java): a new statement starts on the
        next line, or the block closes with '}' right after an expression."""
        if not self.cfg.get("semicolons") or self.parens or self.after_control or i == 0 \
                or self.blocks[-1].kind not in ("block", "function", "class", "header"):
            return False
        prev = self.toks[i - 1]
        if self.text(i) == "}" and not self.stmt_start and (prev.kind in END_KINDS or prev.text in (")", "]", "++", "--")):
            return True
        return self.newline_break(i)

    def check_brackets(self):
        stack = []
        for t in self.toks:
            if t.kind != "SEPARATOR":
                continue
            if t.text in OPEN:
                stack.append(t)
            elif t.text in CLOSE:
                want = PAIR[t.text]
                if stack and stack[-1].text == want:
                    stack.pop()
                elif any(s.text == want for s in stack):
                    while stack[-1].text != want:
                        s = stack.pop()
                        self.error(s.line, "Syntax", f"Missing '{PAIR[s.text]}' for '{s.text}' opened at line {s.line}")
                    stack.pop()
                else:
                    self.error(t.line, "Syntax", f"Unmatched '{t.text}' (no opening '{want}')")
        for s in stack:
            self.error(s.line, "Syntax", f"Missing '{PAIR[s.text]}' for '{s.text}' opened at line {s.line}")

    def mark_arrow_params(self):
        """Find parameters of arrow functions / lambdas: (a, b) => ...  x -> ..."""
        arrow = "=>" if self.js else "->"
        for k, t in enumerate(self.toks):
            if t.text != arrow or k == 0:
                continue
            p = self.toks[k - 1]
            if p.kind == "IDENTIFIER":
                self.arrow_params.add(k - 1)
            elif p.text == ")":
                o = self.match_open(k - 1)
                if o is None:
                    continue
                for q in range(o + 1, k - 1):
                    if self.toks[q].kind == "IDENTIFIER" and self.text(q + 1) in (",", ")", "=") \
                            and self.text(q - 1) != ":":
                        self.arrow_params.add(q)

    def end_statement(self):
        self.decl, self.typedef_mode, self.after_type_body = None, False, None
        while self.pending_headers > 0 and self.blocks[-1].kind == "header":
            self.blocks.pop()
            self.pending_headers -= 1
        self.pending_headers = 0
        self.pending_block = None
        self.stmt_start, self.stmt_first = True, None
        self.arrow_buffer = []

    # ------------------------------------------------------------ statement starts
    def statement_start(self, i):
        """Try to read a declaration at the start of a statement.
        Returns the index to continue from, or None if this is not a declaration."""
        t, x, nxt = self.toks[i], self.toks[i].text, self.text(i + 1)
        blk = self.blocks[-1]
        if nxt == ":" and blk.kind != "object" and (t.kind == "IDENTIFIER" or x in ("public", "private", "protected")):
            return i + 2                                     # label or  public:
        if self.c or self.cpp:
            if x == "typedef":
                self.typedef_mode = True
                return i + 1
            if x == "template" and nxt == "<":
                close = self.match_angle(i + 1) or i + 1
                for k in range(i + 2, close):
                    if self.toks[k].kind == "IDENTIFIER":
                        self.user_types.add(self.toks[k].text)
                return close + 1
            if x == "namespace" and self.text(i + 2) == "{":
                self.pending_block = {"kind": "namespace", "name": None}
                return i + 2
            if x == "using":
                return self.skip_to_semicolon(i)
        if self.java and x in ("package", "import"):
            end = self.skip_to_semicolon(i)
            if x == "import":
                self.java_import(i, end)
            return end
        if self.js:
            if x in ("export", "default", "async") and nxt != ":":
                return i + 1
            if x == "import" and nxt != "(":
                return self.js_import(i)
            if x in ("let", "const", "var"):
                return self.js_declaration(i)
            if x == "function":
                return self.js_function(i, statement=True)
            if x == "class":
                return self.class_header(i, i)
            if blk.kind == "class":
                return self.js_class_member(i)
            return None
        # ----- C, C++ and Java
        k = i
        while self.text(k) in self.cfg["modifiers"] or self.text(k) in ("abstract", "final"):
            k += 1
        if self.text(k) in ("class", "interface", "enum", "struct", "union", "record"):
            if not (self.c and self.text(k) in ("class", "interface", "record")):
                result = self.class_header(i, k)
                if result is not None:
                    return result
        if self.cpp and self.text(k) == "~" and self.text(k + 2) == "(":
            return self.function_def(self.tok(k + 1), "-", k + 2, blk.cls, "destructor", record=False)
        if self.cpp and self.tok(k).kind == "IDENTIFIER" and self.text(k + 1) == "::" and self.text(k + 3) == "(" \
                and self.text(k + 2) == self.text(k):
            return self.function_def(self.tok(k + 2), "-", k + 3, self.text(k), "constructor")
        if blk.kind == "class" and self.text(k) == blk.cls and self.text(k + 1) == "(":
            return self.function_def(self.tok(k), "-", k + 1, blk.cls, "constructor")
        res = self.parse_type(i)
        if res is None:
            return None
        vtype, j, is_const = res
        if self.cpp and self.text(j) == "operator":          # Complex operator+(const Complex &o)
            q = j + 1
            while q < len(self.toks) and self.text(q) != "(" or q == j + 1:
                q += 1
            t = self.tok(j)
            name_tok = Token("IDENTIFIER", "operator" + "".join(self.text(x) for x in range(j + 1, q)),
                             t.line, t.start, self.tok(q - 1).end)
            kind = "method" if blk.kind == "class" else "function"
            return self.function_def(name_tok, vtype, q, blk.cls if blk.kind == "class" else None, kind, sig_start=j)
        if self.tok(j).kind != "IDENTIFIER":
            return None
        after = self.text(j + 1)
        if self.cpp and after == "::" and self.tok(j + 2).kind == "IDENTIFIER" and self.text(j + 3) == "(":
            return self.function_def(self.tok(j + 2), vtype, j + 3, self.text(j), "method")
        if after == "(":
            close = self.match_close(j + 1)
            if close is None:
                return None
            if self.body_follows(close) or blk.func is None:
                kind = "method" if blk.kind == "class" else "function"
                return self.function_def(self.tok(j), vtype, j + 1, blk.cls if blk.kind == "class" else None, kind)
            return self.declare_variable(vtype, j, is_const)  # C++ object: Student s("Dev", 90);
        if after in ("=", ";", ",", "[", ")", ":", "{") or self.tok(j + 1).line > self.tok(j).line:
            return self.declare_variable(vtype, j, is_const)
        return None

    def skip_to_semicolon(self, i):
        k = i
        while k < len(self.toks) and self.text(k) != ";":
            k += 1
        return k

    def body_follows(self, close):
        k = close + 1
        while self.text(k) in ("const", "override", "noexcept", "final", "volatile"):
            k += 1
        if self.text(k) in ("throws", ":", "->"):
            while k < len(self.toks) and self.text(k) not in ("{", ";"):
                k += 1
        return self.text(k) == "{"

    def parse_type(self, i):
        """Read a type such as  const unsigned int,  char*,  int[],  vector<int>,
        struct Point,  std::string.  Returns (type_text, next_index, is_const) or None."""
        k, is_const = i, False
        while self.text(k) in self.cfg["modifiers"] or self.text(k) in ("final", "abstract"):
            if self.text(k) in ("const", "final", "constexpr"):
                is_const = True
            k += 1
        words = []
        if self.text(k) in ("struct", "enum", "union") and self.tok(k + 1).kind == "IDENTIFIER":
            words = [self.text(k), self.text(k + 1)]
            k += 2
        else:
            if self.cpp and self.text(k) == "std" and self.text(k + 1) == "::":
                k += 2
            while self.tok(k).kind == "TYPE":
                words.append(self.text(k))
                k += 1
            if not words:
                t = self.tok(k)
                if t.kind == "IDENTIFIER" and (t.text in self.user_types or t.text in self.cfg["library_types"]
                                               or t.text[0].isupper()):
                    words = [t.text]
                    k += 1
                    if self.tok(k).kind == "IDENTIFIER" and t.text in self.global_block.names:
                        self.global_block.names[t.text]["uses"] += 1     # Student s1;  uses class Student
                else:
                    return None
        if self.text(k) == "const":
            is_const, k = True, k + 1
        type_text = " ".join(words)
        if self.cfg["generics"] and self.text(k) == "<":
            close = self.match_angle(k)
            if close is None:
                return None
            type_text += self.source(k, close).replace(" ", "")
            k = close + 1
        while (self.c or self.cpp) and self.text(k) in ("*", "&", "&&"):
            type_text += self.text(k)
            k += 1
        while self.java and self.text(k) == "[" and self.text(k + 1) == "]":
            type_text += "[]"
            k += 2
        return type_text, k, is_const

    def parse_params(self, a, b):
        params = []
        for s, e in self.split_args(a, b):
            if self.js:
                k = s + 1 if self.text(s) == "..." else s
                if self.tok(k).kind == "IDENTIFIER":
                    params.append((self.tok(k), "any", False))
                elif self.text(k) in ("{", "["):
                    close = self.match_close(k) or e
                    for q in range(k + 1, close):
                        if self.tok(q).kind == "IDENTIFIER" and self.text(q + 1) != ":":
                            params.append((self.tok(q), "any", False))
                continue
            if e - s == 1 and self.text(s) == "void":
                continue
            res = self.parse_type(s)
            if res is None:
                continue
            ptype, k, pconst = res
            if self.text(k) == "...":
                ptype, k = ptype + "...", k + 1
            if k < e and self.tok(k).kind == "IDENTIFIER":
                name = self.tok(k)
                k += 1
                while self.text(k) == "[" and k < e:
                    close = self.match_close(k)
                    if close is None:
                        break
                    ptype += "[]"
                    k = close + 1
                params.append((name, ptype, pconst))
        return params

    def function_def(self, name_tok, ftype, open_i, cls, kind, record=True, sig_start=None):
        close = self.match_close(open_i)
        if close is None:
            return None
        params = self.parse_params(open_i + 1, close)
        has_body = self.body_follows(close)
        k = close + 1
        if has_body:
            while self.text(k) != "{":
                k += 1
        signature = self.source(sig_start if sig_start is not None else self.toks.index(name_tok), close)
        if record:
            self.add_function(name_tok, kind, ftype, signature, cls, has_body)
        if has_body:
            self.pending_block = {"kind": "function", "name": name_tok.text, "params": params,
                                  "cls": cls, "statement": True}
        self.stmt_start = False
        return k

    def add_function(self, name_tok, kind, ftype, signature, cls, has_body):
        blk = self.blocks[-1]
        owner = blk
        if cls and blk.kind != "class":                      # C++  void Student::show() { }
            existing = self.class_members.get(cls, {}).get(name_tok.text)
            if existing:
                existing["body"] = True
                return existing
            owner = self.global_block
        old = owner.names.get(name_tok.text)
        if old and old["kind"] in ("function", "method", "constructor", "function (prototype)"):
            if not old["body"] and has_body:                 # prototype, then the real function
                old["body"], old["kind"], old["line"] = True, kind, name_tok.line
                return old
            if self.c and old["body"] and has_body:
                self.error(name_tok.line, "Duplicate Declaration",
                           f"redefinition of function '{name_tok.text}' (first defined at line {old['line']})")
                return old
            if self.cpp or self.java or not has_body:        # overloading is allowed
                sym = dict(old, line=name_tok.line, value=signature, uses=0, body=has_body)
                self.symbols.append(sym)
                return sym
        sym = self.add_symbol(name_tok, kind if has_body else "function (prototype)", ftype, owner,
                              value=signature, initialized=True)
        if sym:
            sym["body"] = has_body
        return sym

    def declare_variable(self, vtype, j, is_const, word=""):
        name_tok = self.tok(j)
        k = j + 1
        full_type = vtype
        while self.text(k) == "[" and not self.js:          # int marks[5]
            close = self.match_close(k)
            if close is None:
                break
            full_type += self.source(k, close).replace(" ", "")
            k = close + 1
        blk = self.blocks[-1]
        self.stmt_start = False
        base = vtype.rstrip("*&")
        self.decl = {"type": base, "const": is_const, "depth": len(self.parens), "block": blk, "word": word}
        if self.typedef_mode:
            self.user_types.add(name_tok.text)
            self.add_symbol(name_tok, "typedef", full_type, blk, initialized=True)
            return k
        kind = "field" if blk.kind == "class" else "constant" if is_const else "variable"
        init_start = k + 1 if self.text(k) == "=" else None
        initialized = blk.kind in ("class", "global") or self.text(k) in ("(", ":", ")", "{") \
            or (self.cpp and category(full_type) in ("string", "other"))
        value = ""
        if init_start is not None:
            end = self.expr_end(init_start)
            value = self.source(init_start, end - 1)
            initialized = True
            if full_type in ("auto", "var"):
                guess = self.infer(init_start, end)
                if guess:
                    full_type = f"{full_type} ({guess[1]})"
        elif self.text(k) == "(":
            close = self.match_close(k) or k
            value = self.source(k, close)
        sym = self.add_symbol(name_tok, kind, full_type, blk, const=is_const, value=value,
                              initialized=initialized)
        if sym is None:
            return k
        if init_start is not None:
            self.check_types(sym, init_start, self.expr_end(init_start), name_tok.line, is_init=True)
        elif is_const and kind == "constant" and self.cpp and blk.kind != "header" \
                and self.text(k) not in ("(", "{", ":", ")"):
            self.error(name_tok.line, "Constant", f"uninitialized const '{name_tok.text}'")
        return k

    def class_header(self, i, k):
        word = self.text(k)
        name_tok = self.tok(k + 1) if self.tok(k + 1).kind == "IDENTIFIER" else None
        if (self.c or self.cpp) and word in ("struct", "union", "enum") and name_tok \
                and self.text(k + 2) not in ("{", ":", ";"):
            return None                                      # struct Point p;  (a variable)
        q = k + 1
        while q < len(self.toks) and self.text(q) not in ("{", ";"):
            q += 1
        if q >= len(self.toks):
            return None
        name = name_tok.text if name_tok else None
        if name:
            self.user_types.add(name)
            self.class_members.setdefault(name, {})
        if self.text(q) == ";":                              # forward declaration: class A;
            return q
        if name:
            self.add_symbol(name_tok, "record" if word == "record" else word, word, self.blocks[-1],
                            value=self.source(i, q - 1), initialized=True)
        self.pending_block = {"kind": "enum" if word == "enum" else "class", "name": name or "(anonymous)",
                              "word": word, "statement": True, "typedef": self.typedef_mode}
        self.stmt_start = False
        return q

    def preprocessor(self, t):
        m = re.match(r"#\s*include\s*[<\"]([^>\"]+)[>\"]", t.text)
        if m:
            fake = Token("IDENTIFIER", m.group(1), t.line, t.start, t.end)
            if m.group(1) not in self.global_block.names:
                self.add_symbol(fake, "header file", "-", self.global_block, value=t.text, initialized=True)
            return
        m = re.match(r"#\s*define\s+([A-Za-z_]\w*)(\([^)]*\))?\s*(.*)", t.text)
        if m:
            value = m.group(3).strip()
            if re.fullmatch(r"-?\d+", value):
                vtype = "int"
            elif re.fullmatch(r"-?\d*\.\d+[fF]?", value):
                vtype = "double"
            elif value.startswith('"'):
                vtype = "char*"
            else:
                vtype = "macro"
            fake = Token("IDENTIFIER", m.group(1), t.line, t.start, t.end)
            sym = self.add_symbol(fake, "macro", vtype, self.global_block, const=True,
                                  value=value + (m.group(2) or ""), initialized=True)
            if sym:
                sym["macro"] = True

    def java_import(self, i, end):
        parts = [self.text(k) for k in range(i + 1, end) if self.text(k) not in (".", "static")]
        if not parts:
            return
        last = self.tok(end - 1)
        if last.text != "*":
            self.user_types.add(last.text)
        fake = Token("IDENTIFIER", last.text if last.text != "*" else ".".join(parts), last.line, last.start, last.end)
        self.add_symbol(fake, "import", "class" if last.text != "*" else "package", self.global_block,
                        value=self.source(i, end - 1), initialized=True)

    # ------------------------------------------------------------ JavaScript statements
    def js_import(self, i):
        k = i + 1
        while k < len(self.toks) and self.tok(k).kind != "STRING" and self.text(k) != ";":
            t = self.tok(k)
            if t.kind == "IDENTIFIER" and self.text(k + 1) != "as":
                self.add_symbol(t, "import", "module", self.global_block, value=f"import {t.text}", initialized=True)
            k += 1
        self.stmt_start = False
        return k + 1 if self.tok(k).kind == "STRING" else k

    def js_declaration(self, i):
        word = self.text(i)
        self.decl = {"type": None, "const": word == "const", "depth": len(self.parens),
                     "block": self.blocks[-1], "word": word}
        self.stmt_start = False
        k = i + 1
        if self.text(k) in ("{", "["):
            return self.js_destructure(k, word)
        if self.tok(k).kind == "IDENTIFIER":
            return self.js_declare_name(k, word)
        return k

    def js_target_block(self, word):
        if word != "var":
            return self.blocks[-1]
        for b in reversed(self.blocks):                      # var belongs to the whole function
            if b.kind in ("function", "global"):
                return b
        return self.global_block

    def js_declare_name(self, k, word):
        name_tok = self.tok(k)
        blk = self.js_target_block(word)
        kind = "constant" if word == "const" else "variable"
        vtype, value, initialized = "undefined", "", False
        if self.text(k + 1) == "=":
            end = self.expr_end(k + 2)
            vtype, value, initialized = self.js_infer(k + 2, end), self.source(k + 2, end - 1), True
        elif self.text(k + 1) in ("of", "in"):
            vtype, initialized = "any", True
        elif word == "const":
            self.error(name_tok.line, "Syntax", f"Missing initializer in const declaration '{name_tok.text}'")
        self.add_symbol(name_tok, kind, vtype, blk, const=word == "const", word=word, value=value,
                        initialized=initialized)
        return k + 1

    def js_destructure(self, k, word):
        close = self.match_close(k)
        if close is None:
            return k + 1
        blk = self.js_target_block(word)
        for q in range(k + 1, close):
            t = self.tok(q)
            if t.kind == "IDENTIFIER" and self.text(q + 1) in (",", "}", "]", "="):
                self.add_symbol(t, "constant" if word == "const" else "variable", "any", blk,
                                const=word == "const", word=word, value="(destructured)", initialized=True)
        return close + 1

    def js_infer(self, a, b):
        if a >= b:
            return "undefined"
        first = self.tok(a)
        if first.text == "[" and self.match_close(a) == b - 1:
            return "array"
        if first.text == "{" and self.match_close(a) == b - 1:
            return "object"
        if first.text in ("function", "async") or any(self.text(k) == "=>" for k in range(a, b)):
            return "function"
        if first.text == "new" and self.tok(a + 1).kind == "IDENTIFIER":
            return f"object ({self.text(a + 1)})"
        kinds = set()
        for k in range(a, b):
            t = self.toks[k]
            if t.kind in ("INT", "FLOAT"):
                kinds.add("number")
            elif t.kind == "STRING":
                kinds.add("string")
            elif t.kind == "BOOL":
                kinds.add("boolean")
            elif t.kind == "NULL":
                kinds.add("null")
            elif t.text in ("===", "!==", "==", "!=", "<", ">", "<=", ">=", "&&", "||", "!"):
                return "boolean"
            elif t.kind == "IDENTIFIER":
                if self.text(k + 1) in ("(", ".", "[") or self.text(k - 1) == ".":
                    return "any"
                sym = self.lookup(t.text)
                if sym and sym["type"] in ("number", "string", "boolean"):
                    kinds.add(sym["type"])
                else:
                    return "any"
            elif t.text not in ("+", "-", "*", "/", "%", "(", ")"):
                return "any"
        if "string" in kinds:
            return "string"
        return kinds.pop() if len(kinds) == 1 else "any"

    def js_function(self, i, statement):
        k = i + 1
        if self.text(k) == "*":
            k += 1
        name_tok = self.tok(k) if self.tok(k).kind == "IDENTIFIER" else None
        if name_tok:
            k += 1
        if self.text(k) != "(":
            return i + 1
        close = self.match_close(k)
        if close is None:
            return i + 1
        params = self.parse_params(k + 1, close)
        if name_tok and statement:
            self.add_symbol(name_tok, "function", "function", self.blocks[-1],
                            value=self.source(i + 1, close), initialized=True)
        self.pending_block = {"kind": "function", "name": name_tok.text if name_tok else "(anonymous)",
                              "params": params, "cls": self.blocks[-1].cls, "statement": statement}
        self.stmt_start = False
        return close + 1

    def js_class_member(self, i):
        k = i
        while self.text(k) in ("static", "async", "get", "set") and self.text(k + 1) not in ("(", "=", ";"):
            k += 1
        t = self.tok(k)
        if t.kind != "IDENTIFIER":
            return None
        cls = self.blocks[-1].cls
        if self.text(k + 1) == "(":
            close = self.match_close(k + 1)
            if close is None or self.text(close + 1) != "{":
                return None
            kind = "constructor" if t.text == "constructor" else "method"
            sym = self.add_symbol(t, kind, "function", self.blocks[-1], value=self.source(k, close), initialized=True)
            if sym:
                sym["body"] = True
            self.pending_block = {"kind": "function", "name": t.text, "params": self.parse_params(k + 2, close),
                                  "cls": cls, "statement": True}
            self.stmt_start = False
            return close + 1
        if self.text(k + 1) in ("=", ";") or self.tok(k + 1).line > t.line:
            value, vtype = "", "undefined"
            if self.text(k + 1) == "=":
                end = self.expr_end(k + 2)
                value, vtype = self.source(k + 2, end - 1), self.js_infer(k + 2, end)
            self.add_symbol(t, "field", vtype, self.blocks[-1], value=value, initialized=True)
            self.stmt_start = False
            return k + 1
        return None

    # ------------------------------------------------------------ token by token
    def scan(self, i):
        t, x = self.toks[i], self.toks[i].text
        if t.kind == "SEPARATOR":
            if x == "{":
                self.open_brace(i)
            elif x == "}":
                self.close_brace(i)
            elif x == ";":
                self.semicolon()
            elif x == "(":
                return self.open_paren(i)
            elif x == ")":
                self.close_paren()
            elif x == ",":
                return self.comma(i)
            return i + 1
        if t.kind == "KEYWORD":
            if x in ("else", "do", "try", "finally"):
                self.stmt_start = self.after_control = True
            elif x == "function" and self.js:
                return self.js_function(i, statement=False)
            elif x == "goto" or (x in ("break", "continue") and self.tok(i + 1).kind == "IDENTIFIER"):
                return i + 2                                 # goto label;  break outer;
            return i + 1
        if t.kind == "IDENTIFIER":
            return self.identifier(i)
        if t.kind == "OPERATOR":
            self.operator(i)
        if t.kind == "STRING" and x.startswith("`"):
            self.template_uses(t)
        return i + 1

    def open_brace(self, i):
        prev = self.text(i - 1) if i > 0 else ""
        pb, parent = self.pending_block, self.blocks[-1]
        self.pending_block = None
        if pb and pb["kind"] == "function":
            blk = Block("function", parent, func=pb["name"], cls=pb.get("cls") or parent.cls)
            blk.statement = pb.get("statement", True)
        elif pb and pb["kind"] in ("class", "enum"):
            blk = Block(pb["kind"], parent, func=None, cls=pb["name"])
            blk.word, blk.typedef = pb.get("word", ""), pb.get("typedef", False)
        elif pb and pb["kind"] == "namespace":
            blk = Block("block", parent, func=None, cls=None)
        elif parent.kind in ("init", "object") and prev != ")":
            blk = Block(parent.kind, parent)                 # nested  {{1, 2}, {3, 4}}
        elif prev in ("=", "(", ",", ":", "[", "return", "?", "||", "&&", "??", "]") \
                and not (prev == ":" and self.stmt_first in ("case", "default")) \
                or (self.cpp and self.tok(i - 1).kind == "IDENTIFIER" and self.decl):
            blk = Block("object" if self.js else "init", parent)
        else:
            blk = Block("block", parent)
        blk.extra_pops, self.pending_headers = self.pending_headers, 0
        blk.saved = (self.parens, self.decl, self.stmt_first)
        self.parens, self.decl = [], None
        self.blocks.append(blk)
        if pb and pb["kind"] == "function":
            for ptok, ptype, pconst in pb["params"]:
                self.add_symbol(ptok, "parameter", ptype, blk, const=pconst, initialized=True)
        self.stmt_start = blk.kind not in ("init", "object")

    def close_brace(self, i):
        if len(self.blocks) == 1:
            return
        b = self.blocks.pop()
        for _ in range(b.extra_pops):
            if len(self.blocks) > 1 and self.blocks[-1].kind == "header":
                self.blocks.pop()
        if b.saved is not None:
            self.parens, self.decl, self.stmt_first = b.saved
        if b.kind in ("init", "object") or (b.kind == "function" and not b.statement):
            self.stmt_start = False
        elif b.kind in ("class", "enum") and (self.c or self.cpp):
            self.after_type_body = {"type": f"{b.word} {b.cls}" if b.cls != "(anonymous)" else b.word,
                                    "typedef": b.typedef}
            self.stmt_start = False
        else:
            self.stmt_start = True

    def semicolon(self):
        while self.parens and self.parens[-1] != "header":   # recover from an unclosed (
            self.parens.pop()
        if self.parens:                                      # ; inside for( ; ; )
            self.decl = None
            self.stmt_start = False
            return
        self.end_statement()

    def open_paren(self, i):
        prev = self.tok(i - 1) if i > 0 else Token("", "", 0, 0, 0)
        kind = "plain"
        if prev.text in ("if", "while", "switch"):
            kind = "control"
        elif prev.text in ("for", "catch") or (prev.text == "try" and self.java):
            kind = "header"
            self.blocks.append(Block("header", self.blocks[-1]))
            self.stmt_start = True
            if self.js and prev.text == "catch" and self.tok(i + 1).kind == "IDENTIFIER":
                self.add_symbol(self.tok(i + 1), "parameter", "error", self.blocks[-1], initialized=True)
                self.parens.append(kind)
                return i + 2
        elif self.cpp and prev.text == "]":                  # C++ lambda  [](int x) { ... }
            close = self.match_close(i)
            if close is not None and self.text(close + 1) in ("{", "->", "mutable"):
                self.pending_block = {"kind": "function", "name": "(lambda)", "cls": self.blocks[-1].cls,
                                      "params": self.parse_params(i + 1, close), "statement": False}
                return close + 1
        elif prev.kind == "IDENTIFIER" or prev.text in (")", "]"):
            kind = "call"
        self.parens.append(kind)
        return i + 1

    def close_paren(self):
        if not self.parens:
            return
        kind = self.parens.pop()
        if self.decl and len(self.parens) < self.decl["depth"]:
            self.decl = None
        if kind in ("control", "header"):
            self.after_control = self.stmt_start = True
            if kind == "header":
                self.pending_headers += 1

    def comma(self, i):
        d = self.decl
        if d and d["block"] is self.blocks[-1] and len(self.parens) == d["depth"]:
            k = i + 1
            while self.text(k) in ("*", "&"):
                k += 1
            if self.js:
                if self.text(k) in ("{", "["):
                    return self.js_destructure(k, d["word"])
                if self.tok(k).kind == "IDENTIFIER":
                    return self.js_declare_name(k, d["word"])
            elif self.tok(k).kind == "IDENTIFIER" and d["type"]:
                return self.declare_variable(d["type"], k, d["const"])
        return i + 1

    def operator(self, i):
        x, line = self.text(i), self.tok(i).line
        if x == "=" and self.parens and self.parens[-1] == "control":
            self.warn(line, "Assignment In Condition", "'=' is used inside a condition; did you mean '=='?")
        elif x in ("==", "!=") and self.js:
            self.warn(line, "Loose Equality", f"Use '{x}=' instead of '{x}' ({x} converts types before comparing)")
        elif x in ("==", "!=") and self.java:
            sides = []
            for k in (i - 1, i + 1):
                t = self.tok(k)
                sym = self.lookup(t.text) if t.kind == "IDENTIFIER" else None
                sides.append(t.kind == "STRING" or (sym is not None and sym["type"] == "String"))
            if all(sides):
                self.warn(line, "String Comparison", "Strings are compared with '=='; use .equals() to compare their text")
        elif x in ("/", "%") and self.tok(i + 1).kind in ("INT", "FLOAT"):
            try:
                if float(self.text(i + 1).rstrip("uUlLfFdDn")) == 0:
                    self.warn(line, "Division By Zero", "Division by zero")
            except ValueError:
                pass
        elif x == ":" and self.stmt_first in ("case", "default") and not self.parens:
            self.stmt_start = True
        elif (x == "=>" and self.js) or (x == "->" and self.java):
            params = [(t, "any", False) for t in self.arrow_buffer]
            self.arrow_buffer = []
            if self.text(i + 1) == "{":
                self.pending_block = {"kind": "function", "name": "(lambda)", "params": params,
                                      "cls": self.blocks[-1].cls, "statement": False}
            else:
                blk = Block("header", self.blocks[-1])
                self.blocks.append(blk)
                for ptok, ptype, _ in params:
                    self.add_symbol(ptok, "parameter", ptype, blk, initialized=True)
                self.pending_headers += 1

    def role(self, i):
        """How a name is used: write (x = ...), readwrite (x++), element (a[i] = ...),
        input (&x, cin >> x) or read."""
        prev, nxt = self.text(i - 1), self.text(i + 1)
        if nxt == "=":
            return "write"
        if nxt in COMPOUND_ASSIGN or nxt in ("++", "--") or prev in ("++", "--"):
            return "readwrite"
        if nxt == "[":
            close = self.match_close(i + 1)
            if close is not None and self.text(close + 1) == "=":
                return "element"
        before = self.tok(i - 2)
        if (self.c or self.cpp) and prev == "&" and before.kind not in END_KINDS and before.text not in (")", "]"):
            return "input"                                   # &x  (address of x, e.g. scanf)
        if self.cpp and prev == ">>" and self.reads_cin(i):
            return "input"                                   # cin >> x
        return "read"

    def reads_cin(self, i):
        k = i - 1
        while k >= 0 and self.text(k) not in (";", "{", "}"):
            if self.text(k) == "cin":
                return True
            k -= 1
        return False

    def identifier(self, i):
        t, name = self.toks[i], self.toks[i].text
        prev, nxt = self.text(i - 1), self.text(i + 1)
        blk = self.blocks[-1]
        if i in self.arrow_params:
            self.arrow_buffer.append(t)
            return i + 1
        if self.after_type_body and prev in ("}", ",", "*"):  # struct P {...} p1;   typedef ... Name;
            info = self.after_type_body
            if info["typedef"]:
                self.user_types.add(name)
                self.add_symbol(t, "typedef", info["type"], blk, initialized=True)
                return i + 1
            self.after_type_body = None
            return self.declare_variable(info["type"], i, False)
        if prev in (".", "->", "?."):                       # obj.name  -> a class member
            sym = self.member_lookup(name)
            if sym:
                sym["uses"] += 1
            return i + 1
        if prev == "::" or nxt == "::":
            return i + 1
        if blk.kind == "object" and nxt == ":" and prev in ("{", ","):
            return i + 1                                     # JavaScript object key  {name: ...}
        if blk.kind == "object" and nxt == "(" and prev in ("{", ","):
            close = self.match_close(i + 1)                  # object method  { greet() { ... } }
            if close is not None and self.text(close + 1) == "{":
                self.pending_block = {"kind": "function", "name": name, "cls": blk.cls,
                                      "params": self.parse_params(i + 2, close), "statement": False}
                return close + 1
        if blk.kind == "enum" and prev in ("{", ","):
            self.add_symbol(t, "constant", f"enum {blk.cls}", blk, const=True, value="(enum value)", initialized=True)
            return i + 1
        if self.c and name == "scanf" and nxt == "(":
            self.check_scanf(i + 1)
        sym = self.lookup(name)
        role = self.role(i)
        if sym is None and (name in self.cfg["builtins"] or name in self.user_types
                            or name in self.cfg["library_types"]):
            return i + 1
        if sym is None:
            is_call = nxt == "("
            if name[0].isupper() or (is_call and not (self.js or self.java)):
                return i + 1                                 # class names, library functions
            self.unresolved.append({"name": name, "line": t.line, "chain": list(self.blocks), "cls": blk.cls,
                                    "func": blk.func, "role": role, "call": is_call})
            return i + 1
        self.use_symbol(sym, role, i)
        return i + 1

    def use_symbol(self, sym, role, i):
        line, name = self.tok(i).line, sym["name"]
        if role in ("write", "readwrite") and sym["const"]:
            if sym.get("macro"):
                msg = f"'{name}' is a #define constant and cannot be changed"
            elif self.java:
                msg = f"cannot assign a value to final variable {name}"
            elif self.js:
                msg = f"Assignment to constant variable '{name}' (TypeError)"
            else:
                msg = f"assignment of read-only variable '{name}'"
            self.error(line, "Constant", msg)
        if role == "write":
            if self.parens and self.parens[-1] == "control":
                sym["uses"] += 1                             # if (x = 10) also uses the value
            if sym["kind"] in ("variable", "constant", "field", "parameter"):
                self.check_types(sym, i + 2, self.expr_end(i + 2), line, is_init=False)
            sym["initialized"] = True
            return
        if role in ("element", "input"):
            sym["initialized"] = True
            sym["uses"] += 1
            return
        sym["uses"] += 1
        if not sym["initialized"] and sym["kind"] == "variable" and sym["local"] and sym["scalar"] or \
                (not sym["initialized"] and self.js and sym["kind"] == "variable"):
            sym["initialized"] = True                        # report only once
            if self.java:
                self.error(line, "Uninitialized", f"variable {name} might not have been initialized")
            elif self.js:
                self.warn(line, "Uninitialized", f"'{name}' is used before it is given a value (it is undefined)")
            else:
                self.warn(line, "Uninitialized", f"'{name}' is used before it is given a value")
        if role == "readwrite":
            sym["initialized"] = True

    def template_uses(self, t):
        """Count names used inside JavaScript template strings: `Hi ${name}`."""
        for part in re.findall(r"\$\{([^}]*)\}", t.text):
            for m in re.finditer(r"(?<![.\w$])[A-Za-z_$][\w$]*", part):
                sym = self.lookup(m.group())
                if sym:
                    sym["uses"] += 1

    def check_scanf(self, open_i):
        close = self.match_close(open_i)
        if close is None:
            return
        for s, e in self.split_args(open_i + 1, close)[1:]:
            if e - s == 1 and self.tok(s).kind == "IDENTIFIER":
                sym = self.lookup(self.text(s))
                if sym and sym["scalar"] and category(sym["type"]) != "cstring":
                    self.warn(self.tok(s).line, "Missing &",
                              f"scanf() needs the address of '{sym['name']}': write &{sym['name']}")
                    sym["initialized"] = True

    # ------------------------------------------------------------ after the scan
    def resolve_later_uses(self):
        """Names that were not found when they were used: maybe declared later
        (class members, functions, JavaScript hoisting) or really undeclared."""
        seen = set()
        for u in self.unresolved:
            name, line = u["name"], u["line"]
            sym = self.class_members.get(u["cls"], {}).get(name) if u["cls"] else None
            later = None
            if sym is None:
                for b in reversed(u["chain"]):
                    if name in b.names:
                        later = b.names[name]
                        break
            if sym is None and later is not None and later["kind"] in (
                    "function", "method", "constructor", "function (prototype)", "class", "import"):
                sym = later
            if sym is not None:
                sym["uses"] += 1
                continue
            if later is not None:
                later["uses"] += 1
                if self.js and later.get("word") == "var":
                    self.warn(line, "Hoisting", f"'{name}' is used before its declaration on line {later['line']} (value is undefined)")
                elif self.js:
                    self.error(line, "Use Before Declaration", f"Cannot access '{name}' before initialization (ReferenceError)")
                else:
                    self.error(line, "Use Before Declaration", f"'{name}' is used before it is declared on line {later['line']}")
                continue
            if self.js and u["role"] == "write":
                self.warn(line, "Implicit Global", f"'{name}' is assigned without let, const or var (creates a global variable)")
                continue
            key = (name, u["func"])
            if key in seen:
                continue
            seen.add(key)
            if self.java:
                msg = f"cannot find symbol: {'method' if u['call'] else 'variable'} {name}"
            elif self.js:
                msg = f"{name} is not defined (ReferenceError)"
            elif self.cpp:
                msg = f"'{name}' was not declared in this scope"
            else:
                msg = f"'{name}' undeclared (first use in this function)"
            self.error(line, "Undeclared Variable", msg)

    def unused_warnings(self):
        for s in self.symbols:
            if s["kind"] in ("variable", "constant") and s["uses"] == 0 and s["local"] \
                    and not s.get("macro") and s["name"] != "_":
                self.warn(s["line"], "Unused Variable", f"'{s['name']}' is declared but never used")

    def result(self):
        return {
            "symbols": self.symbols,
            "errors": self.errors,
            "warnings": self.warnings,
            "tokens": [{"Line": t.line, "Token Type": t.kind, "Lexeme": t.text} for t in self.toks],
        }


def analyze_clike(code, language):
    return CLikeAnalyzer(code, language).run()
