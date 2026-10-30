"""
python_analyzer.py - Lexical, syntax and semantic analysis for Python.

Python ships with its own compiler front end, so we use it:
  * tokenize  -> lexical analysis (the token stream)
  * ast       -> syntax analysis (the parse tree / abstract syntax tree)
Then we walk the tree ourselves to build the symbol table and to find
semantic problems: undefined names (NameError), wrong operand types
(TypeError), unused variables and variables that change type.
"""
import ast
import builtins
import io
import keyword
import tokenize
import warnings

BUILTIN_NAMES = set(dir(builtins)) | {"__name__", "__file__", "__doc__", "__spec__", "__package__"}
NUMERIC = {"int", "float", "bool", "complex"}
SEQUENCES = {"str", "list", "tuple"}
OP_SYMBOL = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//",
             ast.Mod: "%", ast.Pow: "**", ast.MatMult: "@", ast.BitAnd: "&", ast.BitOr: "|",
             ast.BitXor: "^", ast.LShift: "<<", ast.RShift: ">>"}
ORDER_OPS = {ast.Lt: "<", ast.Gt: ">", ast.LtE: "<=", ast.GtE: ">="}
CALL_TYPES = {"int": "int", "float": "float", "str": "str", "bool": "bool", "list": "list",
              "dict": "dict", "set": "set", "tuple": "tuple", "len": "int", "input": "str",
              "range": "range", "sorted": "list", "round": "int", "abs": None, "type": "type"}


def python_tokens(code):
    """Token stream from Python's tokenize module (stops quietly at the first problem)."""
    tokens = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            name = tokenize.tok_name[tok.type]
            text, line = tok.string, tok.start[0]
            if name in ("NEWLINE", "NL", "COMMENT", "ENDMARKER"):
                continue
            if name == "NAME":
                if text in ("True", "False"):
                    kind = "BOOL"
                elif text == "None":
                    kind = "NULL"
                else:
                    kind = "KEYWORD" if keyword.iskeyword(text) else "IDENTIFIER"
            elif name == "NUMBER":
                kind = "FLOAT" if ("." in text or "e" in text.lower()) and not text.lower().startswith("0x") else "INT"
            elif name.startswith("FSTRING") or name == "STRING":
                kind = "STRING"
            elif name == "OP":
                kind = "SEPARATOR" if text in "()[]{},:;" else "OPERATOR"
            elif name in ("INDENT", "DEDENT"):
                kind, text = name, "(indent)" if name == "INDENT" else "(dedent)"
            else:
                kind = name
            tokens.append({"Line": line, "Token Type": kind, "Lexeme": text})
    except (tokenize.TokenError, SyntaxError):
        pass
    return tokens


class Scope:
    def __init__(self, kind, name, parent):
        self.kind, self.name, self.parent = kind, name, parent   # module, function, class, lambda, comprehension
        self.bound = set()        # every name assigned anywhere in this scope
        self.defined = set()      # names assigned so far (module and class scopes run top to bottom)
        self.symbols = {}
        self.global_names = set()


def bound_names(body_nodes):
    """All names bound directly in a function/class/module body (not inside nested functions)."""
    names, global_names = set(), set()
    stack = list(body_nodes)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            stack.extend(node.decorator_list)
            continue
        if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            continue
        if isinstance(node, ast.Global):
            global_names.update(node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            names.add(node.target.id)
        stack.extend(ast.iter_child_nodes(node))
    return names - global_names, global_names


class PythonAnalyzer(ast.NodeVisitor):
    def __init__(self, code):
        self.code = code
        self.errors, self.warnings, self.symbols = [], [], []
        self.scope = None
        self.module = None
        self.star_import = False
        self.reported = set()
        self.deferred = []        # names used inside functions before the global is created

    # ------------------------------------------------------------ helpers
    def error(self, line, kind, message):
        if ("E", line, message) not in self.reported:
            self.reported.add(("E", line, message))
            self.errors.append({"line": line, "type": kind, "message": message})

    def warn(self, line, kind, message):
        if ("W", line, message) not in self.reported:
            self.reported.add(("W", line, message))
            self.warnings.append({"line": line, "type": kind, "message": message})

    def segment(self, node):
        text = ast.get_source_segment(self.code, node) or ""
        text = " ".join(text.split())
        return text if len(text) <= 45 else text[:42] + "..."

    def add_symbol(self, name, kind, vtype, line, value="", scope=None):
        scope = scope or self.scope
        sym = {"name": name, "kind": kind, "type": vtype or "unknown", "line": line,
               "value": value, "uses": 0, "current": vtype}
        scope.symbols[name] = sym
        self.symbols.append(sym)
        return sym

    def find(self, name):
        """Find the symbol a name refers to, following Python's scope rules."""
        scope = self.scope
        if name in scope.global_names:
            return self.module.symbols.get(name)
        if name in scope.symbols:
            return scope.symbols[name]
        s = scope.parent
        while s is not None:
            if s.kind != "class" and name in s.symbols:
                return s.symbols[name]
            s = s.parent
        return None

    def is_defined(self, name):
        if name in BUILTIN_NAMES or self.star_import:
            return True
        scope = self.scope
        if scope.kind in ("module", "class"):
            if name in scope.defined:
                return True
            return scope.kind == "class" and name in self.module.defined
        s = scope
        while s is not None:
            if s.kind == "module":
                return name in s.bound
            if s.kind != "class" and name in s.bound:
                return True
            s = s.parent
        return False

    # ------------------------------------------------------------ type inference
    def infer(self, node, report=False):
        if node is None:
            return None
        if isinstance(node, ast.Constant):
            return "None" if node.value is None else type(node.value).__name__
        if isinstance(node, (ast.List, ast.ListComp)):
            return "list"
        if isinstance(node, (ast.Dict, ast.DictComp)):
            return "dict"
        if isinstance(node, (ast.Set, ast.SetComp)):
            return "set"
        if isinstance(node, ast.Tuple):
            return "tuple"
        if isinstance(node, ast.JoinedStr):
            return "str"
        if isinstance(node, ast.Lambda):
            return "function"
        if isinstance(node, ast.Compare):
            return "bool"
        if isinstance(node, ast.Name):
            sym = self.find(node.id)
            return sym["current"] if sym and sym["kind"] in ("variable", "constant", "loop variable") else None
        if isinstance(node, ast.BinOp):
            return self.binop_type(node, report)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return "bool"
            inner = self.infer(node.operand)
            if inner == "str" and isinstance(node.op, (ast.USub, ast.UAdd)):
                if report:
                    sym = "-" if isinstance(node.op, ast.USub) else "+"
                    self.error(node.lineno, "Type Error", f"bad operand type for unary {sym}: 'str'")
                return None
            return inner if inner in NUMERIC else None
        if isinstance(node, ast.BoolOp):
            kinds = {self.infer(v) for v in node.values}
            return kinds.pop() if len(kinds) == 1 else None
        if isinstance(node, ast.IfExp):
            a, b = self.infer(node.body), self.infer(node.orelse)
            return a if a == b else None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in CALL_TYPES and node.func.id not in self.module.symbols:
                return CALL_TYPES[node.func.id]
            sym = self.find(node.func.id)
            if sym and sym["kind"] == "class":
                return node.func.id
        return None

    def binop_type(self, node, report):
        left, right = self.infer(node.left, report), self.infer(node.right, report)
        if left is None or right is None:
            return None
        op = type(node.op)
        if left in NUMERIC and right in NUMERIC:
            if op is ast.Div:
                return "float"
            return "float" if "float" in (left, right) else "int"
        if op is ast.Add and left == right and left in SEQUENCES:
            return left
        if op is ast.Mult and left in SEQUENCES and right in ("int", "bool"):
            return left
        if op is ast.Mult and right in SEQUENCES and left in ("int", "bool"):
            return right
        if op is ast.Mod and left == "str":
            return "str"
        if report:
            if op is ast.Add and left in ("str", "list"):
                msg = f'can only concatenate {left} (not "{right}") to {left}'
            elif op is ast.Mult and (left in SEQUENCES or right in SEQUENCES):
                other = right if left in SEQUENCES else left
                msg = f"can't multiply sequence by non-int of type '{other}'"
            else:
                msg = f"unsupported operand type(s) for {OP_SYMBOL.get(op, '?')}: '{left}' and '{right}'"
            self.error(node.lineno, "Type Error", msg)
        return None

    # ------------------------------------------------------------ binding names
    def bind(self, target, value_node, line, kind="variable", value_text=None):
        """Record an assignment to a name, a tuple of names or self.attribute."""
        if isinstance(target, (ast.Tuple, ast.List)):
            values = value_node.elts if isinstance(value_node, (ast.Tuple, ast.List)) \
                and len(value_node.elts) == len(target.elts) else [None] * len(target.elts)
            for t, v in zip(target.elts, values):
                self.bind(t, v, line, kind)
            return
        if isinstance(target, ast.Starred):
            self.bind(target.value, None, line, kind)
            return
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
            cls_scope = self.scope.parent
            if cls_scope is not None and cls_scope.kind == "class":
                key = "self." + target.attr
                if key not in cls_scope.symbols:
                    self.add_symbol(key, "attribute", self.infer(value_node), line,
                                    self.segment(value_node) if value_node is not None else "", scope=cls_scope)
            return
        if not isinstance(target, ast.Name):
            return
        name = target.id
        vtype = self.infer(value_node) if value_node is not None else None
        scope = self.module if name in self.scope.global_names else self.scope
        scope.defined.add(name)
        sym = scope.symbols.get(name)
        if sym is None:
            if kind == "variable" and name.isupper() and scope.kind == "module":
                kind = "constant"
            elif kind == "variable" and scope.kind == "class":
                kind = "class attribute"
            text = value_text if value_text is not None else (self.segment(value_node) if value_node is not None else "")
            self.add_symbol(name, kind, vtype, line, text, scope=scope)
        else:
            if vtype and sym["current"] and vtype != sym["current"] and sym["kind"] in ("variable", "constant"):
                self.warn(line, "Type Change",
                          f"'{name}' changed type from {sym['current']} to {vtype} (allowed in Python, but easy to get wrong)")
            if vtype:
                sym["current"] = vtype
                if sym["type"] == "unknown":
                    sym["type"] = vtype

    # ------------------------------------------------------------ scopes
    def run_scope(self, scope, body, params=()):
        old = self.scope
        self.scope = scope
        scope.bound, scope.global_names = bound_names(body)
        for p in params:
            scope.bound.add(p)
        for stmt in body:
            self.visit(stmt)
        self.scope = old

    def visit_Module(self, node):
        self.module = Scope("module", "<module>", None)
        self.run_scope(self.module, node.body)

    def function_params(self, args):
        all_args = args.posonlyargs + args.args + args.kwonlyargs
        defaults = [None] * (len(args.posonlyargs + args.args) - len(args.defaults)) + list(args.defaults) \
            + list(args.kw_defaults)
        result = []
        for a, d in zip(all_args, defaults):
            result.append((a, d))
        if args.vararg:
            result.append((args.vararg, None))
        if args.kwarg:
            result.append((args.kwarg, None))
        return result

    def visit_FunctionDef(self, node):
        for d in node.decorator_list:
            self.visit(d)
        params = self.function_params(node.args)
        for _, default in params:
            if default is not None:
                self.visit(default)
        in_class = self.scope.kind == "class"
        old = self.scope.symbols.get(node.name)
        if old and old["kind"] in ("function", "method"):
            self.warn(node.lineno, "Redefined", f"function '{node.name}' is defined again (first at line {old['line']})")
        signature = f"def {node.name}({', '.join(a.arg for a, _ in params)})"
        self.scope.defined.add(node.name)
        self.add_symbol(node.name, "method" if in_class else "function", "function", node.lineno, signature)
        scope = Scope("function", node.name, self.scope)
        old_scope = self.scope
        self.scope = scope
        for a, default in params:
            if a.annotation is not None:
                ptype = ast.unparse(a.annotation)
            else:
                ptype = self.infer(default) if default is not None else "any"
            self.add_symbol(a.arg, "parameter", ptype, a.lineno, self.segment(default) if default else "")
            scope.defined.add(a.arg)
        self.scope = old_scope
        self.run_scope(scope, node.body, [a.arg for a, _ in params])

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        params = self.function_params(node.args)
        scope = Scope("lambda", "lambda", self.scope)
        scope.bound = {a.arg for a, _ in params}
        old = self.scope
        self.scope = scope
        self.visit(node.body)
        self.scope = old

    def visit_ClassDef(self, node):
        for item in node.bases + node.decorator_list:
            self.visit(item)
        bases = ", ".join(self.segment(b) for b in node.bases)
        self.scope.defined.add(node.name)
        self.add_symbol(node.name, "class", "class", node.lineno, f"class {node.name}" + (f"({bases})" if bases else ""))
        self.run_scope(Scope("class", node.name, self.scope), node.body)

    def comprehension(self, node, parts):
        for i, gen in enumerate(node.generators):
            if i == 0:
                self.visit(gen.iter)                         # the first iterable belongs to the outer scope
        scope = Scope("comprehension", "comprehension", self.scope)
        old = self.scope
        self.scope = scope
        for i, gen in enumerate(node.generators):
            if i > 0:
                self.visit(gen.iter)
            for n in ast.walk(gen.target):
                if isinstance(n, ast.Name):
                    scope.bound.add(n.id)
                    scope.defined.add(n.id)
            for cond in gen.ifs:
                self.visit(cond)
        for p in parts:
            self.visit(p)
        self.scope = old

    def visit_ListComp(self, node):
        self.comprehension(node, [node.elt])

    visit_SetComp = visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node):
        self.comprehension(node, [node.key, node.value])

    # ------------------------------------------------------------ statements
    def visit_Import(self, node):
        for alias in node.names:
            name = (alias.asname or alias.name).split(".")[0]
            self.scope.defined.add(name)
            self.add_symbol(name, "import", "module", node.lineno, f"import {alias.name}")

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == "*":
                self.star_import = True
                self.warn(node.lineno, "Star Import", f"'from {node.module} import *' hides which names exist; name checks are switched off")
                continue
            name = alias.asname or alias.name
            self.scope.defined.add(name)
            self.add_symbol(name, "import", "imported name", node.lineno, f"from {node.module} import {alias.name}")

    def visit_Global(self, node):
        self.scope.global_names.update(node.names)

    def visit_Assign(self, node):
        self.visit(node.value)
        self.infer(node.value, report=False)
        for target in node.targets:
            self.visit_target(target)
            self.bind(target, node.value, node.lineno)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit(node.value)
        self.visit_target(node.target)
        if isinstance(node.target, ast.Name):
            self.bind(node.target, node.value, node.lineno)
            sym = self.find(node.target.id)
            if sym and sym["line"] == node.lineno:
                sym["type"] = ast.unparse(node.annotation)

    def visit_AugAssign(self, node):
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            fake = ast.BinOp(left=ast.Name(id=node.target.id, ctx=ast.Load()), op=node.op, right=node.value)
            ast.copy_location(fake, node)
            self.visit_Name(fake.left, line=node.lineno)
            self.binop_type(fake, report=True)
        else:
            self.visit(node.target)

    def visit_target(self, target):
        """Visit parts of an assignment target that are read, e.g. the list in a[i] = 5."""
        if isinstance(target, (ast.Attribute, ast.Subscript)):
            self.visit(target.value)
            if isinstance(target, ast.Subscript):
                self.visit(target.slice)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for t in target.elts:
                self.visit_target(t)

    def visit_For(self, node):
        self.visit(node.iter)
        iter_type = self.infer(node.iter)
        item = "int" if iter_type == "range" else "str" if iter_type == "str" else None
        self.visit_target(node.target)
        if isinstance(node.target, ast.Name):
            self.bind(node.target, ast.Constant(value=0) if item == "int" else ast.Constant(value="") if item == "str" else None,
                      node.lineno, kind="loop variable", value_text=f"from {self.segment(node.iter)}")
        else:
            self.bind(node.target, None, node.lineno, kind="loop variable")
        for stmt in node.body + node.orelse:
            self.visit(stmt)

    visit_AsyncFor = visit_For

    def visit_With(self, node):
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self.bind(item.optional_vars, None, node.lineno)
        for stmt in node.body:
            self.visit(stmt)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node):
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.scope.defined.add(node.name)
            if node.name not in self.scope.symbols:
                self.add_symbol(node.name, "variable", "exception", node.lineno, self.segment(node.type) if node.type else "")
            self.scope.symbols[node.name]["uses"] += 1
        for stmt in node.body:
            self.visit(stmt)

    def visit_NamedExpr(self, node):
        self.visit(node.value)
        self.bind(node.target, node.value, node.lineno)

    # ------------------------------------------------------------ expressions
    def visit_Name(self, node, line=None):
        if not isinstance(node.ctx, ast.Load):
            return
        line = line or node.lineno
        name = node.id
        sym = self.find(name)
        if sym is not None and (self.scope.kind not in ("module", "class") or name in self.scope.defined
                                or sym not in self.scope.symbols.values()):
            sym["uses"] += 1
            return
        if sym is None and self.scope.kind not in ("module", "class"):
            self.deferred.append(name)
        if not self.is_defined(name):
            key = ("undef", name, id(self.scope))
            if key not in self.reported:
                self.reported.add(key)
                self.error(line, "Name Error", f"name '{name}' is not defined")
        elif sym is not None:
            sym["uses"] += 1

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == "self" and isinstance(node.ctx, ast.Load):
            s = self.scope
            while s is not None and s.kind != "class":
                s = s.parent
            if s is not None and ("self." + node.attr) in s.symbols:
                s.symbols["self." + node.attr]["uses"] += 1
            elif s is not None and node.attr in s.symbols:
                s.symbols[node.attr]["uses"] += 1           # class attribute read through self
        self.visit(node.value)

    def visit_BinOp(self, node):
        self.generic_visit(node)
        self.binop_type(node, report=True)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and isinstance(node.right, ast.Constant) \
                and node.right.value == 0 and not isinstance(node.right.value, bool):
            self.warn(node.lineno, "Division By Zero", "Division by zero (ZeroDivisionError when this line runs)")

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        self.infer(node, report=True)

    def visit_Compare(self, node):
        self.generic_visit(node)
        left = self.infer(node.left)
        for op, right_node in zip(node.ops, node.comparators):
            right = self.infer(right_node)
            if type(op) in ORDER_OPS and left and right and left != right \
                    and not (left in NUMERIC and right in NUMERIC):
                self.error(node.lineno, "Type Error",
                           f"'{ORDER_OPS[type(op)]}' not supported between instances of '{left}' and '{right}'")
            left = right

    # ------------------------------------------------------------ run
    def run(self):
        tokens = python_tokens(self.code)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tree = ast.parse(self.code)
        except SyntaxError as e:
            kind = "Indentation Error" if isinstance(e, IndentationError) else "Syntax Error"
            self.errors.append({"line": e.lineno or 1, "type": kind, "message": e.msg})
            return {"symbols": [], "errors": self.errors, "warnings": self.warnings, "tokens": tokens,
                    "note": "Python stops at the first syntax error, so fix it to see the symbol table."}
        self.visit(tree)
        for name in self.deferred:                           # e.g. a global created after the function
            if name in self.module.symbols:
                self.module.symbols[name]["uses"] += 1
        for s in self.symbols:
            if s["uses"] == 0 and not s["name"].startswith("_"):
                if s["kind"] in ("variable", "constant", "loop variable"):
                    self.warn(s["line"], "Unused Variable", f"'{s['name']}' is assigned but never used")
                elif s["kind"] == "import":
                    self.warn(s["line"], "Unused Import", f"'{s['name']}' is imported but never used")
            if s["type"] in (None, "None") and s["kind"] != "variable":
                s["type"] = "unknown"
        return {"symbols": self.symbols, "errors": self.errors, "warnings": self.warnings, "tokens": tokens}


def analyze_python(code):
    return PythonAnalyzer(code).run()
