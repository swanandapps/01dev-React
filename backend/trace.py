#!/usr/bin/env python3
"""Readable per-turn trace of Hermes chat requests — one clean line per turn.

Usage:  python3 trace.py         (from backend/)
Reads Hermes's own session store via the :9119 gateway. No log-grepping.
"""
import json
import os
import urllib.request

TOKEN = "the01dev-local"
URL = "http://localhost:9119/api/sessions?limit=12"
# The model's context window (Ollama num_ctx). Default is 2048 unless you start
# Ollama with OLLAMA_CONTEXT_LENGTH — set the same value here so ctx% is accurate.
CONTEXT_WINDOW = int(os.getenv("MODEL_CONTEXT_LIMIT", "2048"))


def main() -> None:
    req = urllib.request.Request(URL, headers={"X-Hermes-Session-Token": TOKEN})
    sessions = json.load(urllib.request.urlopen(req, timeout=5)).get("sessions", [])
    if not sessions:
        print("no sessions yet — send a chat first")
        return
    print(f"context window = {CONTEXT_WINDOW} tokens\n")
    print(f"{'when':^8} {'model':10} {'tools':>5} {'tok in/out':>12} {'ctx%':>5} {'secs':>5}  end")
    print("-" * 74)
    for s in sessions:
        started, ended = s.get("started_at"), s.get("ended_at")
        secs = f"{ended - started:.0f}" if started and ended else "—"
        in_tok = s.get("input_tokens", 0)
        ctx = f"{100 * in_tok / CONTEXT_WINDOW:.0f}%" if CONTEXT_WINDOW else "?"
        when = str(s.get("id", ""))[9:15]  # HHMMSS from the id
        print(f"{when:^8} {str(s.get('model'))[:10]:10} "
              f"{s.get('tool_call_count', 0):>5} "
              f"{str(in_tok) + '/' + str(s.get('output_tokens', 0)):>12} "
              f"{ctx:>5} {secs:>5}  {s.get('end_reason', '') or 'active'}")


if __name__ == "__main__":
    main()
