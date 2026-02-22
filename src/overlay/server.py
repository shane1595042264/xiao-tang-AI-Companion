"""OBS Overlay Server - WebSocket server for streaming subtitles."""

from __future__ import annotations

import asyncio
import json
from typing import Set

from aiohttp import web


class OverlayServer:
    """WebSocket server for OBS browser source overlay."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self._host = host
        self._port = port
        self._clients: Set[web.WebSocketResponse] = set()
        self._app = web.Application()
        self._app.router.add_get("/ws", self._websocket_handler)
        self._app.router.add_get("/", self._serve_overlay)
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        """Start the overlay server."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        print(f"[overlay] Server running at http://{self._host}:{self._port}/")

    async def stop(self) -> None:
        """Stop the overlay server."""
        if self._runner:
            await self._runner.cleanup()

    async def broadcast(self, username: str, message: str, response: str) -> None:
        """Broadcast a message to all connected clients (shows the overlay)."""
        data = json.dumps({
            "type": "response",
            "username": username,
            "message": message,
            "response": response,
        })
        await self._send_all(data)

    async def update_subtitle(self, text: str) -> None:
        """Update just the subtitle text (no re-show animation)."""
        data = json.dumps({"type": "subtitle", "text": text})
        await self._send_all(data)

    async def hide(self) -> None:
        """Tell all clients to hide the overlay."""
        await self._send_all(json.dumps({"type": "hide"}))

    async def _send_all(self, data: str) -> None:
        """Send a JSON string to every connected client."""
        dead_clients = set()
        for client in self._clients:
            try:
                await client.send_str(data)
            except Exception:
                dead_clients.add(client)
        self._clients -= dead_clients

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        print(f"[overlay] Client connected ({len(self._clients)} total)")

        try:
            async for msg in ws:
                pass  # We don't expect messages from clients
        finally:
            self._clients.discard(ws)
            print(f"[overlay] Client disconnected ({len(self._clients)} total)")

        return ws

    async def _serve_overlay(self, request: web.Request) -> web.Response:
        """Serve the overlay HTML page."""
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XiaoTang Overlay</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: transparent;
            font-family: 'ZCOOL KuaiLe', 'Comic Sans MS', 'Microsoft YaHei', sans-serif;
            overflow: hidden;
        }

        .container {
            position: fixed;
            bottom: 40px;
            left: 50%;
            transform: translateX(-50%);
            width: 95%;
            max-width: 1000px;
            text-align: center;
        }

        .message-box {
            padding: 10px 20px;
            opacity: 0;
            transform: translateY(30px);
            transition: all 0.4s ease-out;
        }

        .message-box.visible {
            opacity: 1;
            transform: translateY(0);
        }

        .message-box.hiding {
            opacity: 0;
            transform: translateY(-20px);
        }

        /* Shared stroke style for all text */
        .stroked {
            paint-order: stroke fill;
            -webkit-text-stroke: 0px;
        }

        .name {
            font-size: 28px;
            font-weight: bold;
            color: #ff5ca2;
            text-shadow:
                -2px -2px 0 #fff, 2px -2px 0 #fff,
                -2px  2px 0 #fff, 2px  2px 0 #fff,
                0 -2px 0 #fff, 0 2px 0 #fff,
                -2px 0 0 #fff, 2px 0 0 #fff;
            margin-bottom: 4px;
        }

        .user-message {
            font-size: 18px;
            color: #a0e8ff;
            text-shadow:
                -1.5px -1.5px 0 rgba(0,0,0,0.5), 1.5px -1.5px 0 rgba(0,0,0,0.5),
                -1.5px  1.5px 0 rgba(0,0,0,0.5), 1.5px  1.5px 0 rgba(0,0,0,0.5),
                0 -1.5px 0 rgba(0,0,0,0.5), 0 1.5px 0 rgba(0,0,0,0.5),
                -1.5px 0 0 rgba(0,0,0,0.5), 1.5px 0 0 rgba(0,0,0,0.5);
            margin-bottom: 6px;
        }

        .response {
            font-size: 38px;
            color: #ff4d94;
            line-height: 1.4;
            text-shadow:
                -3px -3px 0 #fff, 3px -3px 0 #fff,
                -3px  3px 0 #fff, 3px  3px 0 #fff,
                0 -3px 0 #fff, 0 3px 0 #fff,
                -3px 0 0 #fff, 3px 0 0 #fff;
            transition: opacity 0.2s ease;
        }

        @keyframes pop-in {
            0% { transform: scale(0.8); opacity: 0; }
            60% { transform: scale(1.05); }
            100% { transform: scale(1); opacity: 1; }
        }

        .message-box.visible .response {
            animation: pop-in 0.35s ease-out;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="message-box" id="messageBox">
            <div class="name">XiaoTang</div>
            <div class="user-message" id="userMessage"></div>
            <div class="response" id="response"></div>
        </div>
    </div>

    <script>
        const messageBox = document.getElementById('messageBox');
        const userMessage = document.getElementById('userMessage');
        const response = document.getElementById('response');

        let ws = null;

        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);

            ws.onopen = () => {
                console.log('Connected to XiaoTang overlay server');
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'response') {
                    showMessage(data.username, data.message, data.response);
                } else if (data.type === 'subtitle') {
                    swapSubtitle(data.text);
                } else if (data.type === 'hide') {
                    hideMessage();
                }
            };

            ws.onclose = () => {
                console.log('Disconnected, reconnecting in 3s...');
                setTimeout(connect, 3000);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                ws.close();
            };
        }

        function showMessage(username, message, responseText) {
            userMessage.textContent = username + ': ' + message;
            response.textContent = responseText;

            messageBox.classList.remove('hiding');
            messageBox.classList.add('visible');
        }

        function swapSubtitle(text) {
            // Quick fade-out, swap text, fade-in
            response.style.opacity = '0';
            setTimeout(() => {
                response.textContent = text;
                response.style.opacity = '1';
            }, 150);
        }

        function hideMessage() {
            messageBox.classList.add('hiding');
            setTimeout(() => {
                messageBox.classList.remove('visible', 'hiding');
            }, 400);
        }

        connect();
    </script>
</body>
</html>'''
        return web.Response(text=html, content_type='text/html')
