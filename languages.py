"""
languages.py - Settings for every supported language.

Each language is described by a dictionary: its keywords, its data types,
built-in names (that need no declaration) and which rules apply to it.
The analyzers read these settings, so adding a language mostly means
adding one more dictionary here.
"""

C_KEYWORDS = [
    "auto", "break", "case", "const", "continue", "default", "do", "else", "enum",
    "extern", "for", "goto", "if", "inline", "register", "restrict", "return",
    "sizeof", "static", "struct", "switch", "typedef", "union", "volatile", "while",
    "true", "false",
]

CPP_EXTRA_KEYWORDS = [
    "class", "public", "private", "protected", "virtual", "friend", "new", "delete",
    "this", "namespace", "using", "template", "typename", "try", "catch", "throw",
    "operator", "nullptr", "explicit", "mutable", "constexpr", "static_cast",
    "dynamic_cast", "const_cast", "reinterpret_cast", "override", "final",
    "noexcept", "decltype",
]

LANGUAGES = {
    "C": {
        "highlight": "c",
        "file_ext": ".c",
        "keywords": C_KEYWORDS,
        "types": ["int", "float", "double", "char", "long", "short", "void",
                  "signed", "unsigned", "bool", "_Bool", "size_t"],
        "library_types": ["FILE"],
        "modifiers": ["const", "static", "extern", "volatile", "register", "inline"],
        "builtins": ["stdin", "stdout", "stderr", "errno"],
        "null_words": ["NULL"],
        "semicolons": True,          # every statement must end with ;
        "preprocessor": True,        # #include, #define
        "char_literals": True,       # 'A' is a char
        "single_quote_strings": False,
        "template_strings": False,
        "dollar_in_names": False,
        "generics": False,
        "invalid_chars": "@`$",
        "checks": [
            "Missing semicolon, unmatched ( ) [ ] { }",
            "Invalid characters, unterminated strings and comments",
            "Undeclared variables and duplicate declarations",
            "Type mismatch (e.g. a string stored in an int)",
            "Warning: float/double stored in an int (data loss)",
            "Changing a const variable or a #define constant",
            "Warning: variable used before it is given a value",
            "Warning: scanf() argument missing &",
            "Warning: unused variables, = inside if/while, division by zero",
        ],
    },
    "C++": {
        "highlight": "cpp",
        "file_ext": ".cpp",
        "keywords": C_KEYWORDS + CPP_EXTRA_KEYWORDS,
        "types": ["int", "float", "double", "char", "long", "short", "void",
                  "signed", "unsigned", "bool", "size_t", "string", "auto"],
        "library_types": ["vector", "map", "set", "unordered_map", "unordered_set",
                          "pair", "queue", "stack", "list", "deque", "array",
                          "priority_queue"],
        "modifiers": ["const", "static", "extern", "volatile", "register", "inline",
                      "virtual", "constexpr", "mutable", "explicit", "friend"],
        "builtins": ["cout", "cin", "cerr", "clog", "endl", "std"],
        "null_words": ["NULL", "nullptr"],
        "semicolons": True,
        "preprocessor": True,
        "char_literals": True,
        "single_quote_strings": False,
        "template_strings": False,
        "dollar_in_names": False,
        "generics": True,
        "invalid_chars": "@`$",
        "checks": [
            "Missing semicolon, unmatched ( ) [ ] { }",
            "Invalid characters, unterminated strings and comments",
            "Undeclared variables and duplicate declarations",
            "Type mismatch (e.g. a number stored in a string)",
            "Warning: float/double stored in an int (data loss)",
            "Changing a const variable",
            "Classes: data members, methods, constructors, objects",
            "Warning: variable used before it is given a value",
            "Warning: unused variables, = inside if/while, division by zero",
        ],
    },
    "Java": {
        "highlight": "java",
        "file_ext": ".java",
        "keywords": [
            "abstract", "assert", "break", "case", "catch", "class", "continue",
            "default", "do", "else", "enum", "extends", "final", "finally", "for",
            "if", "implements", "import", "instanceof", "interface", "native", "new",
            "package", "private", "protected", "public", "return", "static",
            "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
            "transient", "try", "volatile", "while", "true", "false", "null", "record",
        ],
        "types": ["int", "float", "double", "char", "long", "short", "byte",
                  "boolean", "void", "var", "String"],
        "library_types": [],
        "modifiers": ["public", "private", "protected", "static", "final", "abstract",
                      "synchronized", "transient", "volatile", "native", "strictfp"],
        "builtins": [],
        "null_words": ["null"],
        "semicolons": True,
        "preprocessor": False,
        "char_literals": True,
        "single_quote_strings": False,
        "template_strings": False,
        "dollar_in_names": True,
        "generics": True,
        "invalid_chars": "`#",
        "checks": [
            "Missing semicolon, unmatched ( ) [ ] { }",
            "Invalid characters, unterminated strings and comments",
            "Undeclared variables (cannot find symbol) and duplicates",
            "Strict types: double to int is an error (lossy conversion)",
            "Type mismatch between int, double, boolean, char and String",
            "Changing a final variable",
            "Error: local variable used before it is initialized",
            "Warning: comparing Strings with == instead of .equals()",
            "Warning: unused variables, = inside if/while, division by zero",
        ],
    },
    "JavaScript": {
        "highlight": "javascript",
        "file_ext": ".js",
        "keywords": [
            "break", "case", "catch", "class", "const", "continue", "debugger",
            "default", "delete", "do", "else", "export", "extends", "finally", "for",
            "function", "if", "import", "in", "instanceof", "let", "new", "return",
            "super", "switch", "this", "throw", "try", "typeof", "var", "void",
            "while", "with", "yield", "async", "await", "of", "static", "true",
            "false", "null", "from", "as",
        ],
        "types": [],
        "library_types": [],
        "modifiers": ["export", "default", "static", "async"],
        "builtins": ["console", "document", "window", "undefined", "NaN", "Infinity",
                     "require", "module", "exports", "process", "globalThis",
                     "arguments", "localStorage", "navigator", "alert", "prompt",
                     "parseInt", "parseFloat", "isNaN", "setTimeout", "setInterval",
                     "fetch"],
        "null_words": ["null"],
        "semicolons": False,         # JavaScript inserts missing ; automatically
        "preprocessor": False,
        "char_literals": False,      # 'A' is a string in JavaScript
        "single_quote_strings": True,
        "template_strings": True,    # `Hello ${name}`
        "dollar_in_names": True,
        "generics": False,
        "invalid_chars": "@",
        "checks": [
            "Unmatched ( ) [ ] { }, invalid characters, unterminated strings",
            "ReferenceError: variable is not defined",
            "let / const declared twice in the same block",
            "Changing a const variable (TypeError)",
            "const declared without a value",
            "Using a let / const variable before its declaration",
            "Types are inferred (number, string, boolean, array, object, function)",
            "Warning: == instead of ===, implicit globals, unused variables",
        ],
    },
    "Python": {
        "highlight": "python",
        "file_ext": ".py",
        "checks": [
            "Syntax and indentation errors (from Python's own parser)",
            "NameError: name is not defined (variables and functions)",
            "TypeError: str + int and other invalid operations",
            "Types are inferred (int, float, str, bool, list, dict, ...)",
            "Functions, parameters, classes, attributes and imports",
            "Warning: variable changes its type",
            "Warning: unused variables and imports, division by zero",
        ],
    },
}

LANGUAGE_NAMES = ["C", "C++", "Java", "Python", "JavaScript"]
