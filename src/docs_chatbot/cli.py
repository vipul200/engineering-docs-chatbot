"""Command-line entry point.

    python -m docs_chatbot.cli chat        # interactive chatbot
    python -m docs_chatbot.cli chat-eval   # golden-set eval (retrieval always; answers if LLM on)
"""

from __future__ import annotations

import argparse
import json

from docs_chatbot import llm
from docs_chatbot.bot import DocsChatbot
from docs_chatbot.config import get_settings
from docs_chatbot.ingest import load_corpus
from docs_chatbot.metrics import wilson_interval
from docs_chatbot.retriever import Retriever


def cmd_chat(_: argparse.Namespace) -> int:
    bot, history = DocsChatbot.from_settings(), []
    print(f"Docs chatbot (LLM {'on' if llm.llm_enabled() else 'off'}). Ctrl-D to exit.")
    while True:
        try:
            q = input("\nyou> ").strip()
        except EOFError:
            return 0
        if not q:
            continue
        ans = bot.ask(q, history)
        print(f"\nbot [{ans.status}, grounding={ans.grounding}]> {ans.answer}")
        for src in ans.sources:
            print(f"   - {src.citation} (score {src.score})" + (f': "{src.quote}"' if src.quote else ""))
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": ans.answer}]


def cmd_chat_eval(_: argparse.Namespace) -> int:
    s = get_settings()
    bot = DocsChatbot.from_settings()
    retriever = Retriever(load_corpus(s.docs_dir))
    cases = [json.loads(l) for l in (s.data_dir / "chatbot_eval.jsonl").read_text().splitlines() if l]
    use_llm = llm.llm_enabled()
    hit, ans_ok, refuse_ok, n_ans, n_unans = 0, 0, 0, 0, 0
    for c in cases:
        retrieved = {h.chunk.source for h in retriever.search(c["question"], s.top_k)}
        res = bot.ask(c["question"])
        if c["answerable"]:
            n_ans += 1
            hit += c["source"] in retrieved
            if use_llm:
                ok = res.status == "answered" and all(
                    k.lower() in res.answer.lower() for k in c["must_contain"])
                ans_ok += ok
                if not ok:
                    print(f"  MISS: {c['question']!r} -> {res.status}: {res.answer[:120]!r}")
        else:
            n_unans += 1
            if use_llm:
                ok = res.status in {"not_found", "ungrounded", "rejected"}
                refuse_ok += ok
                if not ok:
                    print(f"  SHOULD REFUSE: {c['question']!r} -> {res.answer[:120]!r}")

    def rate(k: int, n: int) -> str:
        lo, hi = wilson_interval(k, n)
        return f"{k}/{n} = {k / n:.2f} (95% CI {lo}-{hi})" if n else "n/a"

    print(f"retrieval hit@{s.top_k}: {rate(hit, n_ans)}")
    if use_llm:
        print(f"answer correctness (keyword + cited): {rate(ans_ok, n_ans)}")
        print(f"correct refusals on unanswerable: {rate(refuse_ok, n_unans)}")
    else:
        print("LLM disabled: answer/refusal metrics skipped (set ANTHROPIC_API_KEY to run them).")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="docs_chatbot")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("chat").set_defaults(fn=cmd_chat)
    sub.add_parser("chat-eval").set_defaults(fn=cmd_chat_eval)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
