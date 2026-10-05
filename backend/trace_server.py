#!/usr/bin/env python3
"""
Chat inspector for /chat requests.  →  http://localhost:8099

Per turn, the things you actually want to see:
  • the message sent + the response generated  (real text)
  • tokens in/out
  • tools the agent called
  • context-window %  (input_tokens / window)

Reads Hermes's own session store (:9119). Stdlib only, no Docker. Auto-refreshes.
Run:  python3 trace_server.py
"""
import html
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = "the01dev-local"
BASE = "http://localhost:9119"
# The context budget ctx% is measured against — the same MODEL_CONTEXT_LIMIT
# (and default) the backend's context builder uses.
CTX = int(os.getenv("MODEL_CONTEXT_LIMIT", "8192"))
N = 8  # sessions to show


def _get(path: str):
    req = urllib.request.Request(BASE + path, headers={"X-Hermes-Session-Token": TOKEN})
    return json.load(urllib.request.urlopen(req, timeout=6))


def _card(s: dict) -> str:
    sid = s.get("id", "")
    it, ot = s.get("input_tokens", 0), s.get("output_tokens", 0)
    pct = round(100 * it / CTX) if CTX else 0
    pcolor = "#e53935" if pct >= 90 else "#fb8c00" if pct >= 70 else "#43a047"
    tools = s.get("tool_call_count", 0)
    started, ended = s.get("started_at"), s.get("ended_at")
    secs = f"{ended - started:.0f}s" if started and ended else "live"
    when = str(sid)[9:15]

    try:
        msgs = _get(f"/api/sessions/{sid}/messages").get("messages", [])
    except Exception:
        msgs = []
    rows = []
    for m in msgs:
        role = m.get("role", "")
        content = html.escape(str(m.get("content", "") or ""))[:1200]
        tool = m.get("tool_name")
        if role == "user":
            rows.append(f"<div class='msg u'><b>🧑 you</b><br>{content}</div>")
        elif role == "assistant":
            rows.append(f"<div class='msg a'><b>🤖 tutor</b><br>{content}</div>")
        elif role == "tool" or tool:
            rows.append(f"<div class='msg t'><b>🔧 tool: {html.escape(str(tool or ''))}</b><br>{content}</div>")
        else:
            rows.append(f"<div class='msg'><b>{html.escape(role)}</b><br>{content}</div>")
    if not rows:
        rows = ["<div class='msg'><i>no messages captured</i></div>"]

    return f"""<div class="card">
      <div class="hdr">{when} · {s.get('model','')}
        · <span style="color:{'#43a047' if tools else '#888'}">tools: {tools}</span>
        · tokens {it}/{ot}
        · ctx <b style="color:{pcolor}">{pct}%</b>
        · {secs}</div>
      {''.join(rows)}
    </div>"""


def _page() -> str:
    try:
        sessions = _get(f"/api/sessions?limit={N}").get("sessions", [])
    except Exception as e:  # noqa: BLE001
        return f"<body style='background:#111;color:#eee;font-family:sans-serif;padding:24px'>" \
               f"<h2>Chat inspector</h2><p>Hermes gateway (:9119) not reachable: {html.escape(str(e))}</p>"
    cards = "".join(_card(s) for s in sessions) or "<p>no chats yet — send one from the app.</p>"
    return f"""<!doctype html><html><head><meta http-equiv="refresh" content="10">
<title>the01dev — chat inspector</title>
<style>
body{{font:14px -apple-system,system-ui,sans-serif;background:#0e0e0e;color:#eee;padding:24px;max-width:860px;margin:auto}}
h2{{margin:0}} .sub{{color:#888;margin:2px 0 18px}}
.card{{border:1px solid #2a2a2a;border-radius:10px;padding:14px 16px;margin-bottom:16px;background:#161616}}
.hdr{{color:#bbb;font-size:12px;margin-bottom:10px;font-family:ui-monospace,monospace}}
.msg{{padding:8px 12px;border-radius:8px;margin:6px 0;white-space:pre-wrap;line-height:1.4}}
.msg b{{color:#9ecbff;font-size:12px}}
.msg.u{{background:#1b2330}} .msg.a{{background:#18231b}} .msg.t{{background:#2a2416;font-size:13px}}
.msg.t b{{color:#e0b34a}}
</style></head>
<body><h2>Chat inspector</h2>
<div class="sub">message · response · tokens · tools · context% (window = {CTX} tok) · auto-refresh 10s</div>
{cards}</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_page().encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("chat inspector → http://localhost:8099")
    HTTPServer(("127.0.0.1", 8099), Handler).serve_forever()
