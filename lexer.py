"""
lexer.py - Phase 1: Lexical analysis for C, C++, Java and JavaScript.

The lexer reads the source code character by character (using regular
expressions) and groups the characters into tokens such as
KEYWORD, TYPE, IDENTIFIER, INT, FLOAT, STRING, OPERATOR and SEPARATOR.
It also reports lexical errors: invalid characters and unclosed
strings or comments.

(Python is tokenized by Python's own `tokenize` module, see python_analyzer.py.)
"""
import re
from collections import namedtuple

# kind = token type, text = the lexeme, line = line number,
# start/end = position in the source (used to show initial values)
Token = namedtuple("Token", ["kind", "text", "line", "start", "end"])

OPERATORS = [
    ">>>=", "<<=", ">>=", ">>>", "===", "!==", "...", "->", "::", "++", "--",
    "<<", ">>", "<=", ">=", "==", "!=", "&&", "||", "+=", "-=", "*=", "/=", "%=",
    "&=", "|=", "^=", "=>", "?.", "??",
    "+", "-", "*", "/", "%", "=", "<", ">", "!", "&", "|", "^", "~", "?", ":", ".",
]
SEPARATORS = "(){}[];,"


def build_pattern(cfg):
    """Build one big regular expression for the chosen language."""
    rules = []
    if cfg["preprocessor"]:
        rules.append(("PREPROCESSOR", r"\#[^\n]*"))
    rules += [
        ("COMMENT", r"//[^\n]*"),
        ("BLOCK_COMMENT", r"/\*[\s\S]*?\*/"),
        ("BAD_COMMENT", r"/\*[\s\S]*"),
    ]
    if cfg["template_strings"]:
        rules += [("TEMPLATE", r"`(?:[^`\\]|\\[\s\S])*`"), ("BAD_TEMPLATE", r"`[\s\S]*")]
    rules += [
        ("STRING", r'"(?:[^"\\\n]|\\.)*"'),
        ("BAD_STRING", r'"(?:[^"\\\n]|\\.)*'),
    ]
    if cfg["char_literals"]:
        rules += [("CHAR", r"'(?:[^'\\\n]|\\.)+'"), ("BAD_CHAR", r"'(?:[^'\\\n]|\\.)*")]
    if cfg["single_quote_strings"]:
        rules += [("SQ_STRING", r"'(?:[^'\\\n]|\\.)*'"), ("BAD_SQ_STRING", r"'(?:[^'\\\n]|\\.)*")]
    if cfg.get("highlight") == "java":
        rules.append(("ANNOTATION", r"@[A-Za-z_]\w*"))
    rules.append(("NUMBER", r"0[xX][0-9a-fA-F]+[uUlL]*"
                            r"|(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?[fFdDlL]?"
                            r"|\d+[eE][+-]?\d+[fFdD]?"
                            r"|\d+[uUlLfFdDn]*"))
    ident = r"[A-Za-z_$][A-Za-z0-9_$]*" if cfg["dollar_in_names"] else r"[A-Za-z_][A-Za-z0-9_]*"
    rules.append(("WORD", ident))
    rules.append(("OPERATOR", "|".join(re.escape(op) for op in OPERATORS)))
    rules.append(("SEPARATOR", "[" + re.escape(SEPARATORS) + "]"))
    rules += [("NEWLINE", r"\n"), ("SPACE", r"[ \t\r\f\v]+"), ("INVALID", r".")]
    return re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in rules))


def word_kind(text, cfg):
    """Decide whether a word is a type, keyword, boolean, null or identifier."""
    if text in cfg["types"]:
        return "TYPE"
    if text in ("true", "false"):
        return "BOOL"
    if text in cfg["null_words"]:
        return "NULL"
    if text in cfg["keywords"] or text in cfg["modifiers"]:
        return "KEYWORD"
    return "IDENTIFIER"


def number_kind(text):
    if text[:2].lower() == "0x":
        return "INT"
    if "." in text or "e" in text.lower() or text[-1] in "fFdD":
        return "FLOAT"
    return "INT"


def tokenize(code, cfg):
    """Return (tokens, errors) for C, C++, Java or JavaScript code."""
    tokens, errors = [], []
    line = 1
    for m in build_pattern(cfg).finditer(code):
        kind, text, start = m.lastgroup, m.group(), m.start()
        if kind == "NEWLINE":
            line += 1
            continue
        if kind in ("SPACE", "COMMENT"):
            continue
        if kind == "BLOCK_COMMENT":
            line += text.count("\n")
            continue
        if kind == "PREPROCESSOR":
            line_start = code.rfind("\n", 0, start) + 1
            if code[line_start:start].strip():          # '#' in the middle of a line
                errors.append({"line": line, "type": "Lexical", "message": "Invalid character '#'"})
                continue
            tokens.append(Token("PREPROCESSOR", text.strip(), line, start, m.end()))
            continue
        if kind == "BAD_COMMENT":
            errors.append({"line": line, "type": "Lexical", "message": "Unterminated comment (missing */)"})
            line += text.count("\n")
            continue
        if kind in ("BAD_STRING", "BAD_SQ_STRING", "BAD_TEMPLATE"):
            errors.append({"line": line, "type": "Lexical", "message": "Unterminated string (missing closing quote)"})
            line += text.count("\n")
            continue
        if kind == "BAD_CHAR":
            errors.append({"line": line, "type": "Lexical",
                           "message": "Empty or unterminated character literal"})
            continue
        if kind == "INVALID" or (kind == "OPERATOR" and text in cfg["invalid_chars"]):
            errors.append({"line": line, "type": "Lexical", "message": f"Invalid character '{text}'"})
            continue

        if kind == "WORD":
            kind = word_kind(text, cfg)
        elif kind == "NUMBER":
            kind = number_kind(text)
        elif kind in ("SQ_STRING", "TEMPLATE"):
            kind = "STRING"
        tokens.append(Token(kind, text, line, start, m.end()))
        if kind == "STRING":
            line += text.count("\n")                     # template strings can span lines
    return tokens, errors
