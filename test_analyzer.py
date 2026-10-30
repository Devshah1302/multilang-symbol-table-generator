"""
test_analyzer.py - Automated tests for the Multi-Language Symbol Table Generator.

Core idea of every test:
    1. Give a small program (input) to analyze(code, language)
    2. Get the result back
    3. Compare it with what we EXPECT  ->  match = PASS, no match = FAIL

Run with:   python3 -m unittest -v test_analyzer.py
"""
import unittest

from analyzer import analyze
from samples import SAMPLES


def error_types(result):
    return [e["type"] for e in result["errors"]]


def error_lines(result):
    return [e["line"] for e in result["errors"]]


def symbol(result, name):
    return next((s for s in result["symbols"] if s["Name"] == name), None)


class TestSamples(unittest.TestCase):
    """Every built-in valid sample must have no errors; every error sample must have errors."""

    def test_valid_samples_have_no_errors(self):
        for lang, programs in SAMPLES.items():
            for title, code in programs.items():
                if title.startswith("Valid"):
                    with self.subTest(language=lang):
                        r = analyze(code, lang)
                        self.assertEqual(r["errors"], [])
                        self.assertEqual(r["warnings"], [])

    def test_error_samples_have_errors(self):
        for lang, programs in SAMPLES.items():
            for title, code in programs.items():
                if not title.startswith("Valid"):
                    with self.subTest(language=lang, sample=title):
                        self.assertGreater(analyze(code, lang)["summary"]["errors"], 0)


class TestC(unittest.TestCase):
    def test_symbol_table(self):
        r = analyze('#define MAX 5\nint add(int a, int b) { return a + b; }\nint main() { int x = add(1, 2); return x; }', "C")
        self.assertEqual(symbol(r, "MAX")["Kind"], "macro")
        self.assertEqual(symbol(r, "add")["Kind"], "function")
        self.assertEqual(symbol(r, "a")["Kind"], "parameter")
        self.assertEqual(symbol(r, "x")["Type"], "int")

    def test_errors(self):
        r = analyze('int main() {\n int a = 1;\n int a = 2;\n int b = "x";\n c = 3;\n return 0\n}', "C")
        self.assertEqual(error_types(r), ["Duplicate Declaration", "Type Mismatch", "Undeclared Variable", "Syntax"])

    def test_scanf_warning(self):
        r = analyze('#include <stdio.h>\nint main() { int age; scanf("%d", age); return age; }', "C")
        self.assertIn("Missing &", [w["type"] for w in r["warnings"]])


class TestCpp(unittest.TestCase):
    def test_class_members(self):
        r = analyze("class Box {\npublic:\n  int w;\n  int area() { return w * w; }\n};\nint main() { Box b; return b.area(); }", "C++")
        self.assertEqual(symbol(r, "Box")["Kind"], "class")
        self.assertEqual(symbol(r, "w")["Kind"], "field")
        self.assertEqual(symbol(r, "area")["Kind"], "method")
        self.assertEqual(r["errors"], [])

    def test_const_and_string(self):
        r = analyze('#include <string>\nusing namespace std;\nint main() {\n const int L = 5;\n L = 6;\n string s = 10;\n return L + s.size();\n}', "C++")
        self.assertEqual(error_types(r), ["Constant", "Type Mismatch"])


class TestJava(unittest.TestCase):
    def test_strict_types(self):
        r = analyze("class A {\n void f() {\n  int x = 2.5;\n  float y = 1.5;\n  long z = 3;\n  System.out.println(x + y + z);\n }\n}", "Java")
        self.assertEqual(error_lines(r), [3, 4])                 # long z = 3 is fine (widening)

    def test_uninitialized_is_error(self):
        r = analyze("class A {\n void f() {\n  int n;\n  System.out.println(n);\n }\n}", "Java")
        self.assertEqual(error_types(r), ["Uninitialized"])

    def test_field_used_before_its_declaration_is_fine(self):
        r = analyze("class A {\n void f() { count++; }\n int count = 0;\n}", "Java")
        self.assertEqual(r["errors"], [])


class TestPython(unittest.TestCase):
    def test_types_are_inferred(self):
        r = analyze("a = 5\nb = 2.5\nc = 'hi'\nd = [1, 2]\nprint(a, b, c, d)", "Python")
        self.assertEqual([symbol(r, n)["Type"] for n in "abcd"], ["int", "float", "str", "list"])

    def test_name_and_type_errors(self):
        r = analyze("age = 20\nmsg = 'Age ' + age\nprint(msg, total)", "Python")
        self.assertEqual(error_types(r), ["Type Error", "Name Error"])

    def test_syntax_error(self):
        r = analyze("def f(:\n  pass", "Python")
        self.assertEqual(error_types(r), ["Syntax Error"])

    def test_function_can_use_global_defined_later(self):
        r = analyze("def show():\n    print(total)\n\ntotal = 5\nshow()", "Python")
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["warnings"], [])


class TestJavaScript(unittest.TestCase):
    def test_const_and_let_rules(self):
        r = analyze("const PI = 3.14;\nPI = 3;\nlet a = 1;\nlet a = 2;\nconsole.log(PI, a, b);", "JavaScript")
        self.assertEqual(error_types(r), ["Constant", "Duplicate Declaration", "Undeclared Variable"])

    def test_no_semicolons_needed(self):
        r = analyze("let x = 1\nconst y = x * 2\nconsole.log(y)", "JavaScript")
        self.assertEqual(r["errors"], [])

    def test_inferred_types(self):
        r = analyze("const n = 5;\nconst s = 'a';\nconst f = (v) => v;\nconsole.log(n, s, f(1));", "JavaScript")
        self.assertEqual([symbol(r, x)["Type"] for x in "nsf"], ["number", "string", "function"])


class TestRobustness(unittest.TestCase):
    def test_empty_and_broken_code_never_crash(self):
        broken = ["", "   ", "{{{", ")))", "int x = ", '"unclosed', "class {", "def (", "/* never closed"]
        for lang in SAMPLES:
            for code in broken:
                with self.subTest(language=lang, code=code):
                    analyze(code, lang)


class TestUserInterface(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        self.at = AppTest.from_file("app.py", default_timeout=30).run()

    def click(self, label):
        [b for b in self.at.button if label in b.label][0].click()
        self.at.run()

    def metrics(self):
        return {m.label: m.value for m in self.at.metric}

    def test_every_language_analyzes(self):
        for lang in ["C", "C++", "Java", "Python", "JavaScript"]:
            self.at.selectbox[0].select(lang)
            self.at.run()
            self.click("Analyze")
            self.assertEqual(self.metrics()["Errors"], "0", lang)

    def test_load_error_sample(self):
        self.at.selectbox[0].select("Java")
        self.at.run()
        self.at.selectbox[1].select("Program with errors")
        self.at.run()
        self.click("Load Sample")
        self.click("Analyze")
        self.assertEqual(self.metrics()["Errors"], "9")

    def test_reset_button(self):
        self.click("Analyze")
        self.click("Reset")
        self.assertEqual(self.at.text_area[0].value, "")
        self.assertEqual(len(self.at.metric), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
