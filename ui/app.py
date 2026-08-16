"""Engram receipt viewer — the demo UI.

    streamlit run ui/app.py

Pick a question, ingest its history into HydraDB, ask it, and see the answer
WITH its receipt: the exact source message for every fact used and the earlier
value it superseded. When the graph holds no supporting fact, Engram abstains
instead of guessing — shown side by side with what a vector-RAG baseline says.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import find_dotenv, load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(find_dotenv(usecwd=True))

from engram.answer import answer_question  # noqa: E402
from engram.graph import Hydra  # noqa: E402
from engram.ingest import ingest_instance, load_dataset  # noqa: E402

st.set_page_config(page_title="Engram — graph memory that shows its work", page_icon="🧾", layout="wide")


@st.cache_resource
def hydra() -> Hydra:
    h = Hydra()
    h.verify()
    return h


@st.cache_data(show_spinner=False)
def dataset() -> list[dict]:
    return load_dataset()


CATS = ["knowledge-update", "multi-session", "temporal-reasoning", "abstention"]


def pick(data: list[dict], cat: str, n: int) -> dict:
    matches = [
        d
        for d in data
        if (str(d["question_id"]).endswith("_abs") if cat == "abstention"
            else d["question_type"] == cat and not str(d["question_id"]).endswith("_abs"))
    ]
    return matches[n % len(matches)] if matches else data[0]


st.title("🧾 Engram")
st.caption("Graph-native agent memory on HydraDB — every recalled fact comes with a receipt, and it abstains when the answer isn't in memory.")

data = dataset()
with st.sidebar:
    st.header("Question")
    cat = st.selectbox("Category", CATS, index=0)
    idx = st.number_input("Which one", min_value=0, max_value=50, value=0, step=1)
    inst = pick(data, cat, int(idx))
    st.markdown(f"**id:** `{inst['question_id']}`")
    st.markdown(f"**sessions:** {len(inst['haystack_sessions'])}")
    go = st.button("Ingest + Ask", type="primary", use_container_width=True)

st.subheader(inst["question"])
st.caption(f"gold answer: {inst['answer']}")

if go:
    h = hydra()
    with st.status("Ingesting history into HydraDB…", expanded=False) as status:
        info = ingest_instance(h, inst)
        c = info["counts"]
        status.update(
            label=f"Ingested {c['sessions']} sessions → {c['facts']} facts, "
            f"{c['supersedes']} supersessions",
            state="complete",
        )
    res = answer_question(h, info["database"], inst["question"])

    if res["abstained"]:
        st.error("**ABSTAINED** — no supporting fact in memory. Engram declines instead of guessing.")
    else:
        st.success(f"**{res['answer']}**")
    st.caption(f"traversed {res['entities']} · {res['evidence_count']} current facts in scope")

    if res["receipt"]:
        st.markdown("### Receipt")
        for item in res["receipt"]:
            f = item["fact"]
            with st.expander(f"📌 {f['predicate']} = **{f['object']}**  ·  status={f['status']}", expanded=True):
                st.markdown(f"**Source message** — session `{f['source_session']}`:")
                st.info(f["source_text"])
                if item["superseded"]:
                    s = item["superseded"]
                    st.markdown(
                        f"⏮️ **Superseded** an earlier value: `{s['object']}` "
                        f"— replaced at valid_from `{f['valid_from']}`."
                    )
                    st.caption("A vector search over chunks would surface both values with no way to tell which is current. The graph followed SUPERSEDES to the live one.")
    elif not res["abstained"]:
        st.caption("(answer used no single fact id — see facts in scope)")
else:
    st.info("Pick a question in the sidebar and hit **Ingest + Ask**.")
