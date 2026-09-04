import os
import json
import secrets
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path.cwd()
ENV = ROOT / ".env"

def load_env(path):
    data = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    return data

env = load_env(ENV)

client_id = env.get("YOUTUBE_CLIENT_ID", "")
client_secret = env.get("YOUTUBE_CLIENT_SECRET", "")

if not client_id or not client_secret:
    raise RuntimeError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET missing in .env")

redirect_uri = "http://localhost:8765"
state = secrets.token_urlsafe(24)

scopes = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

params = {
    "client_id": client_id,
    "redirect_uri": redirect_uri,
    "response_type": "code",
    "scope": " ".join(scopes),
    "access_type": "offline",
    "prompt": "consent",
    "state": state,
}

auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

result = {}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if query.get("state", [""])[0] != state:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid OAuth state")
            return

        result["code"] = query.get("code", [""])[0]
        result["error"] = query.get("error", [""])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<h2>ATLAS ZERO YouTube authorization received.</h2>"
            b"<p>You can close this browser tab and return to PowerShell.</p>"
        )

    def log_message(self, format, *args):
        pass

server = HTTPServer(("localhost", 8765), Handler)

print("Opening Google authorization page...")
webbrowser.open(auth_url)

server.handle_request()
server.server_close()

if result.get("error"):
    raise RuntimeError("OAuth authorization failed: " + result["error"])

code = result.get("code", "")
if not code:
    raise RuntimeError("Authorization code was not returned")

token_data = urllib.parse.urlencode({
    "client_id": client_id,
    "client_secret": client_secret,
    "code": code,
    "grant_type": "authorization_code",
    "redirect_uri": redirect_uri,
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=token_data,
    method="POST",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)

with urllib.request.urlopen(req, timeout=30) as response:
    payload = json.loads(response.read().decode("utf-8"))

refresh_token = payload.get("refresh_token", "")

if not refresh_token:
    raise RuntimeError(
        "Google returned no refresh_token. Revoke the app grant and repeat with prompt=consent."
    )

lines = []
if ENV.exists():
    lines = ENV.read_text(encoding="utf-8-sig").splitlines()

lines = [
    line for line in lines
    if not line.startswith("YOUTUBE_REFRESH_TOKEN=")
]

lines.append("YOUTUBE_REFRESH_TOKEN=" + refresh_token)

ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("YOUTUBE_REFRESH_TOKEN = PRESENT")
print("OAuth bootstrap complete.")
