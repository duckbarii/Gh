#!/usr/bin/env python3
# webterm.py
# Usage: python3 webterm.py
# Requires: aiohttp, aiohttp-basicauth not needed. Install: pip3 install aiohttp

import asyncio
import os, pty, tty, fcntl, struct
from aiohttp import web, WSCloseCode

# CONFIG
HOST = "0.0.0.0"
PORT = 8000
WS_PATH = "/ws"
SHELL = "/bin/bash"   # change if needed
AUTH_TOKEN = "change_this_token_to_something_strong"

# Serve the HTML (xterm.js uses CDN)
INDEX_HTML = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Web Terminal</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css" />
  <style>body,html{{height:100%;margin:0;background:#111;color:#eee}}#terminal{{height:100vh;width:100%}}</style>
</head>
<body>
  <div id="terminal"></div>

  <script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script>
  <script>
    const term = new Terminal({cursorBlink: true});
    term.open(document.getElementById('terminal'));
    const token = prompt("Enter token:");
    if(!token) {{ term.writeln("No token provided. Refresh."); throw new Error("no token"); }}
    const wsProto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(wsProto + "://" + location.host + "{WS_PATH}?token=" + encodeURIComponent(token));
    ws.binaryType = "arraybuffer";
    term.onData(data => ws.send(JSON.stringify({type:"input", data:data})));
    window.addEventListener("resize", () => {{
      const cols = term.cols, rows = term.rows;
      ws.send(JSON.stringify({{type:"resize", cols:cols, rows:rows}}));
    }});
    ws.onopen = ()=> {{
      term.writeln("Connected to web shell.");
      // send initial resize
      ws.send(JSON.stringify({{type:"resize", cols:term.cols, rows:term.rows}}));
    }};
    ws.onmessage = (ev) => {{
      try {{
        const msg = JSON.parse(ev.data);
        if(msg.type === "output") term.write(msg.data);
      }} catch(e) {{
        // fallback
        term.write(ev.data);
      }}
    }};
    ws.onclose = ()=> term.writeln("\\r\n*** disconnected ***");
  </script>
</body>
</html>
"""

# PTY helpers
def set_winsize(fd, rows, cols):
    # struct winsize: rows, cols, xpix, ypix
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

# We need termios constant - import here to avoid error if not used earlier
import termios

async def websocket_handler(request):
    token = request.rel_url.query.get("token", "")
    if token != AUTH_TOKEN:
        return web.Response(status=401, text="Unauthorized")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Fork a pty
    pid, fd = pty.fork()
    if pid == 0:
        # child
        os.execv(SHELL, [SHELL])
    # parent:
    loop = asyncio.get_event_loop()

    async def read_pty_and_send():
        try:
            while True:
                await asyncio.sleep(0)
                r = await loop.run_in_executor(None, os.read, fd, 1024)
                if not r:
                    await ws.send_str('')  # maybe close
                    break
                await ws.send_str(web.json.dumps({"type":"output", "data": r.decode(errors="ignore")}))
        except Exception:
            pass
        finally:
            try:
                await ws.close()
            except: pass

    read_task = asyncio.create_task(read_pty_and_send())

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    import json
                    obj = json.loads(msg.data)
                    if obj.get("type") == "input":
                        os.write(fd, obj.get("data", "").encode())
                    elif obj.get("type") == "resize":
                        cols = int(obj.get("cols", 80))
                        rows = int(obj.get("rows", 24))
                        # set winsize
                        winsize = struct.pack("HHHH", rows, cols, 0, 0)
                        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
                except Exception:
                    pass
            elif msg.type == web.WSMsgType.ERROR:
                break
    finally:
        try:
            os.close(fd)
        except: pass
        read_task.cancel()
    return ws

async def index(request):
    return web.Response(text=INDEX_HTML, content_type='text/html')

app = web.Application()
app.router.add_get('/', index)
app.router.add_get(WS_PATH, websocket_handler)

if __name__ == '__main__':
    print(f"Starting web terminal on http://{HOST}:{PORT} (token={AUTH_TOKEN})")
    web.run_app(app, host=HOST, port=PORT)
