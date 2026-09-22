"""Local fictional target. Automation never imports or calls its data layer."""

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from html import escape

STYLE = """body{font:16px Georgia;background:#edf1f5;color:#173047;margin:40px}main{background:white;padding:32px;max-width:760px;margin:auto;border-top:6px solid #147d78}h1{margin:0 0 8px}table{width:100%;border-collapse:collapse}td{padding:16px;border-bottom:1px solid #ddd}button,input{font:inherit;padding:10px}button{background:#147d78;color:white;border:0;cursor:pointer}small{color:#627686}a{color:#086f80}"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Request URLs can contain identifiers.

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        scenario = q.get("scenario", ["normal"])[0]
        member = q.get("member", [""])[0]
        safe_member = escape(member, quote=True)
        scenario = (
            scenario
            if scenario in ("normal", "slow", "blocked", "denied")
            else "normal"
        )
        if p.path == "/":
            body = f'<h2>Member search</h2><form action="/member"><input type="hidden" name="scenario" value="{scenario}"><table><tr><td><table><tr><td><label for="lookup">Member ID</label></td><td><input id="lookup" name="member" autocomplete="off"></td></tr></table></td></tr></table><button>Search</button></form>'
        elif p.path in ("/member", "/savings"):
            if not member.isascii() or not member.isdigit() or len(member) != 5:
                body = "<h2>Validation error</h2>"
            elif member not in ("12345", "67890"):
                body = "<h2>Member not found</h2>"
            elif scenario == "denied":
                body = "<h2>Permission denied</h2>"
            elif scenario == "blocked":
                body = f'<h2>Session locked</h2><p>An operator must acknowledge this demonstration lock.</p><a href="{p.path}?member={safe_member}&scenario=normal">Unlock session</a>'
            elif p.path == "/member":
                body = f'<h2>Member detail</h2><table><tr><td>Fictional member</td><td>{safe_member}</td></tr><tr><td>Accounts</td><td><a href="/savings?member={safe_member}&scenario=normal">Savings</a></td></tr></table>'
            else:
                amount = "1520.25" if member == "12345" else "9876.54"
                body = f'<h2>Savings account</h2><table><tr><td>Available balance</td><td><output aria-label="Balance">{amount}</output></td></tr><tr><td>Currency</td><td><output aria-label="Currency">USD</output></td></tr></table>'
        else:
            self.send_error(404)
            return
        if scenario == "slow" and p.path == "/member":
            body = (
                '<h2 id="loading">Loading</h2><section hidden id="content">'
                + body
                + '</section><script>setTimeout(()=>{document.getElementById("loading").remove();document.getElementById("content").hidden=false},1200)</script>'
            )
        html = f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Ledger Demo</title><style>{STYLE}</style><main><h1>Ledger / Member Services</h1><small>Fictional data · training environment · app version 1</small>{body}</main></html>'
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port=8765):
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
