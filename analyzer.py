"""
analyzer.py - The single entry point used by the user interface.

    analyze(code, language)  ->  result dictionary

It sends the code to the right analyzer:
    C, C++, Java, JavaScript  ->  clike_analyzer.py  (our own lexer + parser)
    Python                    ->  python_analyzer.py (Python's tokenize + ast)
and puts the answer into one common format, so app.py can show every
language in exactly the same way.
"""
from clike_analyzer import analyze_clike
from languages import LANGUAGE_NAMES
from python_analyzer import analyze_python

FUNCTION_KINDS = ("function", "method", "constructor")


def analyze(code, language):
    if language not in LANGUAGE_NAMES:
        raise ValueError(f"Unsupported language: {language}")
    raw = analyze_python(code) if language == "Python" else analyze_clike(code, language)

    symbols = sorted(raw["symbols"], key=lambda s: s["line"])
    rows = [{
        "Name": s["name"],
        "Kind": s["kind"],
        "Type": s["type"] or "-",
        "Line": s["line"],
        "Value / Details": s["value"] or "-",
        "Times Used": s["uses"],
    } for s in symbols]
    errors = sorted(raw["errors"], key=lambda e: e["line"])
    warnings = sorted(raw["warnings"], key=lambda w: w["line"])
    return {
        "language": language,
        "code": code,
        "symbols": rows,
        "errors": errors,
        "warnings": warnings,
        "tokens": raw["tokens"],
        "note": raw.get("note"),
        "summary": {
            "lines": len(code.splitlines()),
            "tokens": len(raw["tokens"]),
            "symbols": len(rows),
            "functions": sum(1 for s in symbols if s["kind"] in FUNCTION_KINDS),
            "errors": len(errors),
            "warnings": len(warnings),
        },
    }
