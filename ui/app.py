"""Engram receipt viewer — a clean, dark, Ledger-class demo UI.

    streamlit run ui/app.py

Pick a question, ingest its history into HydraDB, ask it, and see the answer
WITH its receipt: the exact source message for every fact used and the earlier
value it superseded. When the graph holds no supporting fact, Engram abstains.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import streamlit as st
from dotenv import find_dotenv, load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(find_dotenv(usecwd=True))

from engram.answer import answer_question  # noqa: E402
from engram.graph import Hydra  # noqa: E402
from engram.ingest import ingest_instance, load_dataset  # noqa: E402

st.set_page_config(page_title="Engram", page_icon="◆", layout="wide")

# --------------------------------------------------------------------------- #
# Design system — dark, minimal, premium. Injected once.
# --------------------------------------------------------------------------- #
CSS = """
<style>
:root{
  --bg:#0a0a0b; --panel:#111113; --panel2:#17171a; --line:#242428;
  --text:#f4f4f5; --muted:#8a8a92; --faint:#5c5c64;
  --accent:#4cd6a0; --accent-dim:rgba(76,214,160,.10);
  --warn:#e0a458; --warn-dim:rgba(224,164,88,.10);
}
html,body,.stApp{background:var(--bg);color:var(--text);
  font-family:-apple-system,"SF Pro Display","Segoe UI",Inter,Roboto,sans-serif;
  -webkit-font-smoothing:antialiased;}
#MainMenu,header[data-testid="stHeader"],footer{display:none!important;}
.stDeployButton,[data-testid="stToolbar"]{display:none!important;}
.block-container{padding-top:2.2rem;max-width:1080px;}
[data-testid="stSidebar"]{background:var(--panel);border-right:1px solid var(--line);}
[data-testid="stSidebar"] .block-container{padding-top:1.4rem;}

/* Brand */
.eg-brand{display:flex;align-items:baseline;gap:.55rem;}
.eg-mark{color:var(--accent);font-size:1.5rem;line-height:1;}
.eg-word{font-weight:700;font-size:1.5rem;letter-spacing:.32em;}
.eg-tag{color:var(--muted);font-size:.9rem;margin:.35rem 0 0;letter-spacing:.01em;}
.eg-rule{height:1px;background:var(--line);margin:1.3rem 0 1.6rem;}

/* Question */
.eg-qlabel{color:var(--faint);font-size:.72rem;letter-spacing:.18em;
  text-transform:uppercase;margin-bottom:.5rem;}
.eg-question{font-size:1.6rem;font-weight:600;line-height:1.32;margin:0 0 .3rem;}
.eg-gold{color:var(--muted);font-size:.85rem;margin-top:.4rem;}
.eg-gold b{color:var(--faint);font-weight:600;letter-spacing:.06em;}

/* Answer hero */
.eg-answer{background:linear-gradient(180deg,var(--panel2),var(--panel));
  border:1px solid var(--line);border-radius:16px;padding:1.5rem 1.7rem;margin:1.3rem 0;}
.eg-pill{display:inline-flex;align-items:center;gap:.45rem;font-size:.7rem;
  letter-spacing:.16em;text-transform:uppercase;font-weight:600;
  padding:.28rem .6rem;border-radius:999px;}
.eg-pill.ok{color:var(--accent);background:var(--accent-dim);
  border:1px solid rgba(76,214,160,.25);}
.eg-pill.no{color:var(--warn);background:var(--warn-dim);
  border:1px solid rgba(224,164,88,.25);}
.eg-dot{width:6px;height:6px;border-radius:50%;background:currentColor;}
.eg-atext{font-size:1.9rem;font-weight:650;line-height:1.25;margin:.85rem 0 0;
  letter-spacing:-.01em;}
.eg-atext.abst{color:var(--warn);font-size:1.25rem;font-weight:600;}
.eg-meta{color:var(--faint);font-size:.82rem;margin-top:.9rem;
  border-top:1px solid var(--line);padding-top:.8rem;}
.eg-meta code{color:var(--muted);background:transparent;}

/* Receipt */
.eg-sec{color:var(--faint);font-size:.72rem;letter-spacing:.18em;
  text-transform:uppercase;margin:1.9rem 0 .8rem;}
.eg-card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:1.15rem 1.3rem;margin-bottom:.9rem;}
.eg-fact{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap;
  font-family:"SF Mono","JetBrains Mono",ui-monospace,monospace;font-size:.95rem;}
.eg-pred{color:var(--muted);}
.eg-eq{color:var(--faint);}
.eg-val{color:var(--accent);font-weight:600;}
.eg-status{margin-left:auto;font-size:.66rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--faint);border:1px solid var(--line);
  border-radius:999px;padding:.16rem .5rem;font-family:inherit;}
.eg-srclabel{color:var(--faint);font-size:.68rem;letter-spacing:.16em;
  text-transform:uppercase;margin:1rem 0 .4rem;}
.eg-quote{border-left:2px solid var(--accent);background:var(--panel2);
  border-radius:0 8px 8px 0;padding:.7rem .9rem;color:#d7d7db;font-size:.92rem;
  line-height:1.5;}
.eg-super{display:flex;align-items:center;gap:.7rem;margin-top:.9rem;
  padding-top:.85rem;border-top:1px solid var(--line);
  font-family:"SF Mono","JetBrains Mono",ui-monospace,monospace;font-size:.9rem;}
.eg-old{color:var(--warn);text-decoration:line-through;opacity:.8;}
.eg-arrow{color:var(--faint);}
.eg-new{color:var(--accent);font-weight:600;}
.eg-supnote{color:var(--faint);font-size:.8rem;margin-top:.55rem;line-height:1.5;
  font-family:-apple-system,"Segoe UI",sans-serif;}

/* Buttons + inputs */
.stButton>button{background:var(--accent);color:#08120d;border:none;
  border-radius:10px;font-weight:650;letter-spacing:.02em;padding:.55rem 1rem;
  width:100%;transition:filter .15s ease;}
.stButton>button:hover{filter:brightness(1.08);}
[data-testid="stSidebar"] label{color:var(--muted)!important;font-size:.78rem;
  letter-spacing:.04em;}
.eg-empty{color:var(--faint);font-size:.95rem;border:1px dashed var(--line);
  border-radius:12px;padding:2rem;text-align:center;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def hydra() -> Hydra:
    h = Hydra()
    h.verify()
    return h


@st.cache_data(show_spinner=False)
def dataset() -> list[dict]:
    return load_dataset()


CATS = ["knowledge-update", "abstention", "multi-session", "temporal-reasoning"]


def pick(data: list[dict], cat: str, n: int) -> dict:
    m = [
        d for d in data
        if (str(d["question_id"]).endswith("_abs") if cat == "abstention"
            else d["question_type"] == cat and not str(d["question_id"]).endswith("_abs"))
    ]
    return m[n % len(m)] if m else data[0]


def esc(x) -> str:
    return html.escape(str(x))


# --- header ---------------------------------------------------------------- #
st.markdown(
    '<div class="eg-brand"><span class="eg-mark">◆</span>'
    '<span class="eg-word">ENGRAM</span></div>'
    '<div class="eg-tag">Graph memory on HydraDB — every answer carries a receipt.</div>'
    '<div class="eg-rule"></div>',
    unsafe_allow_html=True,
)

data = dataset()
with st.sidebar:
    st.markdown('<div class="eg-tag" style="margin:0 0 1rem">Query</div>', unsafe_allow_html=True)
    cat = st.selectbox("Category", CATS, index=0)
    idx = st.number_input("Sample #", min_value=0, max_value=50, value=0, step=1)
    inst = pick(data, cat, int(idx))
    st.markdown(
        f'<div class="eg-meta">id <code>{esc(inst["question_id"])}</code> · '
        f'{len(inst["haystack_sessions"])} sessions</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    go = st.button("Ingest + Ask")

# --- question -------------------------------------------------------------- #
st.markdown(
    f'<div class="eg-qlabel">Question</div>'
    f'<div class="eg-question">{esc(inst["question"])}</div>'
    f'<div class="eg-gold"><b>GOLD</b> &nbsp;{esc(inst["answer"])}</div>',
    unsafe_allow_html=True,
)

if not go:
    st.markdown(
        '<div style="margin-top:1.6rem"></div>'
        '<div class="eg-empty">Pick a question and press <b>Ingest + Ask</b> '
        'to traverse the graph.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

h = hydra()
with st.spinner("Ingesting history into HydraDB…"):
    info = ingest_instance(h, inst)
    res = answer_question(h, info["database"], inst["question"])
c = info["counts"]

# --- answer hero ----------------------------------------------------------- #
if res["abstained"]:
    pill = '<span class="eg-pill no"><span class="eg-dot"></span>Abstained</span>'
    body = '<div class="eg-atext abst">Not supported by memory — declined instead of guessing.</div>'
else:
    pill = '<span class="eg-pill ok"><span class="eg-dot"></span>Answered</span>'
    body = f'<div class="eg-atext">{esc(res["answer"])}</div>'

st.markdown(
    f'<div class="eg-answer">{pill}{body}'
    f'<div class="eg-meta">traversed <code>{esc(res["entities"])}</code> · '
    f'{res["evidence_count"]} current facts in scope · '
    f'ingested <code>{c["facts"]}</code> facts, <code>{c["supersedes"]}</code> supersessions '
    f'across <code>{c["sessions"]}</code> sessions</div></div>',
    unsafe_allow_html=True,
)

# --- receipt --------------------------------------------------------------- #
if res["receipt"]:
    st.markdown('<div class="eg-sec">Receipt · the graph shows its work</div>', unsafe_allow_html=True)
    for item in res["receipt"]:
        f = item["fact"]
        card = (
            f'<div class="eg-card">'
            f'<div class="eg-fact"><span class="eg-pred">{esc(f["predicate"])}</span>'
            f'<span class="eg-eq">=</span><span class="eg-val">{esc(f["object"])}</span>'
            f'<span class="eg-status">{esc(f["status"])}</span></div>'
            f'<div class="eg-srclabel">Source message · session {esc(f["source_session"])}</div>'
            f'<div class="eg-quote">{esc(f["source_text"])}</div>'
        )
        if item["superseded"]:
            s = item["superseded"]
            card += (
                f'<div class="eg-super"><span class="eg-old">{esc(s["object"])}</span>'
                f'<span class="eg-arrow">→ superseded by →</span>'
                f'<span class="eg-new">{esc(f["object"])}</span></div>'
                f'<div class="eg-supnote">A vector search would surface both values by '
                f'similarity with no way to tell which is current. Engram followed the '
                f'<b>SUPERSEDES</b> edge to the live one.</div>'
            )
        card += "</div>"
        st.markdown(card, unsafe_allow_html=True)
elif not res["abstained"]:
    st.markdown('<div class="eg-supnote">Answer used no single fact id.</div>', unsafe_allow_html=True)
