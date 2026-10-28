#!/usr/bin/env python3
"""Make the Home button open the launcher instead of LG's home.

webOS does not let an app replace Home, or even see which app is in front, so this runs on
another always-on device on the same network (a Mac, a Raspberry Pi, a phone in Termux). It
watches the foreground app over the TV's remote-control service and, the moment LG's home
appears, launches the launcher on top. LG's home shows for about half a second.

Press Home twice within ESCAPE_SECONDS to stay on LG's home (for its menus).

    python3 home-watch.py 192.168.1.50

Needs: pip install websockets. Pair once first (sync-apps.py does it).
"""
import asyncio
import json
import os
import sys
import time

import lgtv

LAUNCHER = "com.gathin.tvhome"
LG_HOME = {"com.webos.app.home", "com.webos.app.fullhome"}   # fullhome: webOS 5's overlay home bar
ESCAPE_SECONDS = 3.0


def log(*args):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *args, flush=True)


async def watch(host):
    ws = await lgtv.session(host, ping_interval=10, ping_timeout=10)
    log("connected to", host)
    last_redirect = float("-inf")
    try:
        await ws.send(json.dumps({"type": "subscribe", "id": "fg",
                                  "uri": "ssap://com.webos.applicationManager/getForegroundAppInfo",
                                  "payload": {"extraInfo": True}}))
        home_open = False
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("id") != "fg":
                continue
            # extraInfo lists every foreground window: on webOS 5 the home bar opens over the app
            # instead of replacing it, so the plain appId never changes.
            payload = msg.get("payload", {})
            windows = payload.get("foregroundAppInfo") or [payload]
            was_open, home_open = home_open, any(
                w.get("appId") in LG_HOME or w.get("windowType") == "_WEBOS_WINDOW_TYPE_HOME" for w in windows)
            if not home_open or was_open:
                continue
            now = time.monotonic()
            if now - last_redirect < ESCAPE_SECONDS:
                log("Home pressed twice: staying on LG home")
                last_redirect = float("-inf")
                continue
            last_redirect = now
            await ws.send(json.dumps({"type": "request", "id": "launch", "uri": "ssap://system.launcher/launch",
                                      "payload": {"id": LAUNCHER}}))
            log("LG home -> launcher")
    finally:
        await ws.close()


async def main(host):
    delay = 5
    while True:
        try:
            await watch(host)
            delay = 5
        except (OSError, asyncio.TimeoutError, lgtv.websockets.WebSocketException) as e:
            # TV off, in standby or off the network: keep trying, but back off.
            log("not connected:", type(e).__name__, e)
            delay = min(delay * 2, 20)
        await asyncio.sleep(delay)


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TV_HOST")
    if not host:
        sys.exit("usage: home-watch.py <TV IP>")
    try:
        asyncio.run(main(host))
    except KeyboardInterrupt:
        pass
