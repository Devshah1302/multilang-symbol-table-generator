"""
app.py - Streamlit user interface for the Multi-Language Symbol Table Generator.
Run with:  streamlit run app.py
"""
import streamlit as st

from analyzer import analyze
from languages import LANGUAGES, LANGUAGE_NAMES
from samples import SAMPLES

ALL_SAMPLE_CODES = {code for programs in SAMPLES.values() for code in programs.values()}

st.set_page_config(page_title="Symbol Table Generator", page_icon="🧮", layout="wide")
st.markdown("""
<style>
.app-header {padding: 1.1rem 1.4rem; border-radius: 10px; margin-bottom: 1rem;
             background: linear-gradient(90deg, #7A1C1F, #C42527);}
.app-header h1 {color: #ffffff; margin: 0; padding: 0; font-size: 1.8rem;}
.app-header p {color: #fde3e3; margin: 0.3rem 0 0 0;}
textarea {font-family: 'Courier New', monospace !important; font-size: 0.92rem !important;}
</style>
<div class="app-header">
  <h1>🧮 Interactive Compiler Symbol Table Generator</h1>
  <p>Lexical, syntax and semantic analysis for C · C++ · Java · Python · JavaScript</p>
</div>
""", unsafe_allow_html=True)

st.info("**Note:** This is a simplified *educational* analyzer, not a full compiler. It builds the "
        "symbol table and finds common lexical, syntax and semantic errors, but it does not generate "
        "machine code, and a real compiler may report some extra errors.")

# ---------- session state + button callbacks
if "language" not in st.session_state:
    st.session_state.language = LANGUAGE_NAMES[0]
    st.session_state.sample_choice = list(SAMPLES[LANGUAGE_NAMES[0]])[0]
    st.session_state.code = SAMPLES[LANGUAGE_NAMES[0]][st.session_state.sample_choice]
    st.session_state.result = None


def change_language():
    """New language chosen: show its first sample (unless the user typed their own code)."""
    lang = st.session_state.language
    first = list(SAMPLES[lang])[0]
    st.session_state.sample_choice = first
    if not st.session_state.code.strip() or st.session_state.code in ALL_SAMPLE_CODES:
        st.session_state.code = SAMPLES[lang][first]
    st.session_state.result = None


def load_sample():
    st.session_state.code = SAMPLES[st.session_state.language][st.session_state.sample_choice]
    st.session_state.result = None


def run_analysis():
    st.session_state.result = analyze(st.session_state.code, st.session_state.language)


def clear_all():
    st.session_state.code = ""
    st.session_state.result = None


# ---------- sidebar
language = st.session_state.language
with st.sidebar:
    st.header("How it works")
    st.markdown("""
1. **Lexical analysis**: the code is split into tokens.
2. **Syntax analysis**: the order of tokens is checked.
3. **Semantic analysis**: names and types are checked and the **symbol table** is built.
""")
    st.subheader(f"Checks for {language}")
    st.markdown("\n".join(f"- {c}" for c in LANGUAGES[language]["checks"]))
    st.caption("Python is analysed with Python's built-in tokenize and ast modules; "
               "C, C++, Java and JavaScript with this project's own lexer and parser.")

# ---------- input area
st.subheader("Source Code")
col_lang, col_sample, col_load = st.columns([1.2, 2.3, 1])
with col_lang:
    st.selectbox("Language", LANGUAGE_NAMES, key="language", on_change=change_language)
with col_sample:
    st.selectbox("Built-in sample programs", list(SAMPLES[language]), key="sample_choice")
with col_load:
    st.write("")
    st.write("")
    st.button("📂 Load Sample", on_click=load_sample, width="stretch")

st.text_area(f"Type or paste your {language} program here", key="code", height=360)

col_analyze, col_clear, _ = st.columns([1, 1, 1])
with col_analyze:
    st.button("▶ Analyze", type="primary", on_click=run_analysis, width="stretch")
with col_clear:
    st.button("🗑 Reset / Clear", on_click=clear_all, width="stretch")

# ---------- results
result = st.session_state.result
if result is not None:
    st.divider()
    summary = result["summary"]
    if summary["tokens"] == 0 and summary["errors"] == 0:
        st.warning("Nothing to analyze. Please type some code or load a sample program.")
    else:
        st.subheader(f"Analysis Summary ({result['language']})")
        m = st.columns(6)
        m[0].metric("Lines", summary["lines"])
        m[1].metric("Tokens", summary["tokens"])
        m[2].metric("Symbols", summary["symbols"])
        m[3].metric("Functions", summary["functions"])
        m[4].metric("Errors", summary["errors"])
        m[5].metric("Warnings", summary["warnings"])

        if summary["errors"] == 0:
            st.success(f"✅ Analysis passed: no errors found. {summary['symbols']} symbol(s), "
                       f"{summary['warnings']} warning(s).")
        else:
            st.error(f"❌ Analysis failed: {summary['errors']} error(s) and {summary['warnings']} warning(s) found.")
        if result["note"]:
            st.warning(result["note"])

        st.subheader("Symbol Table")
        if result["symbols"]:
            st.dataframe(result["symbols"], hide_index=True, width="stretch")
            st.caption("Kind = what the name is (variable, function, class, ...). "
                       "Times Used = how many times the name is used after it is declared.")
        else:
            st.write("No symbols to show.")

        col_err, col_src = st.columns([3, 2])
        with col_err:
            st.subheader("Errors and Warnings")
            if not result["errors"] and not result["warnings"]:
                st.write("No errors or warnings. 🎉")
            for e in result["errors"]:
                st.error(f"**Line {e['line']} · {e['type']}:** {e['message']}")
            for w in result["warnings"]:
                st.warning(f"**Line {w['line']} · Warning ({w['type']}):** {w['message']}")
        with col_src:
            st.subheader("Analyzed Code")
            st.code(result["code"], language=LANGUAGES[result["language"]]["highlight"], line_numbers=True)

        with st.expander("Token stream (output of lexical analysis)"):
            st.dataframe(result["tokens"], hide_index=True, width="stretch")
