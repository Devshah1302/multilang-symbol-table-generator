# Interactive Compiler Symbol Table Generator (Multi-Language)

A Compiler Design mini-project in **Python + Streamlit**. Choose a language from the dropdown (**C, C++, Java, Python or JavaScript**), type or load a program, and click **Analyze**. The tool performs **lexical, syntax and semantic analysis** and shows the **symbol table**, errors, warnings, an analysis summary and the token stream.

> This is a simplified *educational* analyzer, not a full compiler. It does not generate machine code, and a real compiler may report some extra errors.

## Project Structure

```
multilang-symbol-table/
├── app.py              # Streamlit user interface (language dropdown, buttons, results)
├── analyzer.py         # Entry point: analyze(code, language) -> one common result format
├── languages.py        # Settings per language: keywords, types, built-ins, rules
├── lexer.py            # Lexical analysis for C, C++, Java, JavaScript (regular expressions)
├── clike_analyzer.py   # Syntax + semantic analysis and symbol table for C, C++, Java, JavaScript
├── python_analyzer.py  # Python analysis using Python's own tokenize and ast modules
├── samples.py          # Built-in sample programs (a valid one and one with errors per language)
├── test_analyzer.py    # 21 automated tests
├── requirements.txt    # Only dependency: streamlit
└── README.md
```

## Installation and Run

Requires Python 3.9 or newer. If a `venv` folder was copied from another computer, delete it first.

**macOS / Linux**
```bash
cd multilang-symbol-table
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

**Windows**
```bash
cd multilang-symbol-table
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at **http://localhost:8501**. Press **Ctrl + C** to stop it.

Run the tests: `python3 -m unittest -v test_analyzer.py`

## Symbol Table Columns

| Column | Meaning |
|---|---|
| Name | Identifier name |
| Kind | variable, constant, function, method, constructor, parameter, class, field, import, macro, ... |
| Type | Declared type (C, C++, Java) or inferred type (Python, JavaScript) |
| Line | Line where it is declared |
| Value / Details | Initial value, or the function signature / class header |
| Times Used | How many times the name is used |

## What Is Checked

| Check | C | C++ | Java | Python | JavaScript |
|---|---|---|---|---|---|
| Invalid characters, unclosed strings | ✓ | ✓ | ✓ | ✓ | ✓ |
| Missing `;`, unmatched brackets | ✓ | ✓ | ✓ | syntax error | brackets |
| Undeclared / undefined names | ✓ | ✓ | ✓ | ✓ | ✓ |
| Duplicate declaration | ✓ | ✓ | ✓ | – | let/const |
| Type mismatch | ✓ | ✓ | ✓ (strict) | str + int | – |
| Changing a constant | const, #define | const | final | – | const |
| Used before a value is given | warning | warning | error | – | warning |
| Unused variables | ✓ | ✓ | ✓ | ✓ | ✓ |
| Special | scanf without & | `=` in if | String `==` | type change | `==` vs `===` |

## Sample Input and Expected Output

**Java, "Program with errors" sample:** 19 lines, 11 symbols, **9 errors**, 3 warnings.

| Line | Error |
|---|---|
| 4 | incompatible types: possible lossy conversion from double to int |
| 5 | incompatible types: possible lossy conversion from double to float |
| 6 | incompatible types: int cannot be converted to String |
| 7 | incompatible types: int cannot be converted to boolean |
| 9 | variable score is already defined in method main |
| 10 | cannot assign a value to final variable MAX_USERS |
| 11 | variable level might not have been initialized |
| 12 | cannot find symbol: variable bonus |
| 16 | Missing ';' at end of line 16 |

Every valid sample gives **0 errors and 0 warnings**. All valid samples were compiled or run with gcc 13, g++ 13, javac 21, Node 22 and Python 3.13, and the error messages were compared with theirs.

## Demo Steps

1. Run `streamlit run app.py`. C is selected. Click **Analyze** to see the symbol table of a correct C program.
2. Choose **Program with errors**, click **Load Sample** and then **Analyze**. Show the errors and match their line numbers in the numbered code.
3. Change the **Language** to Java, Python and JavaScript and repeat. Point out the language-specific rules: Java is strict about types, Python and JavaScript infer types, and JavaScript has `const`, `let` and `===` rules.
4. Open **Token stream** to show the lexical analysis output.
5. Click **Reset / Clear**, type your own code and analyze it.

## How It Works

1. **Lexical analysis:** `lexer.py` uses one regular expression per language to split code into tokens. Python uses its built-in `tokenize` module.
2. **Syntax analysis:** `clike_analyzer.py` reads the tokens statement by statement and recognises declarations, functions, classes and blocks. It checks brackets and semicolons. Python uses its built-in `ast` parser.
3. **Semantic analysis:** every declaration is stored in the symbol table, which uses hash tables (Python dictionaries). Every use of a name is looked up there and checked: is it declared, is it a constant, does the type match?
