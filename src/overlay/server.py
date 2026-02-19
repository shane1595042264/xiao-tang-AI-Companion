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
        """Broadcast a message to all connected clients."""
        data = json.dumps({
            "type": "response",
            "username": username,
            "message": message,
            "response": response,
        })

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
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: transparent;
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            overflow: hidden;
        }

        .container {
            position: fixed;
            bottom: 50px;
            left: 50%;
            transform: translateX(-50%);
            width: 90%;
            max-width: 800px;
        }

        .message-box {
            background: linear-gradient(135deg, rgba(255, 182, 193, 0.95), rgba(255, 218, 233, 0.95));
            border-radius: 20px;
            padding: 20px 30px;
            box-shadow: 0 8px 32px rgba(255, 105, 180, 0.3);
            border: 2px solid rgba(255, 255, 255, 0.5);
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

        .header {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }

        .avatar {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #ff69b4, #ff1493);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 18px;
            margin-right: 12px;
            box-shadow: 0 2px 8px rgba(255, 105, 180, 0.4);
        }

        .name {
            font-size: 18px;
            font-weight: bold;
            color: #d63384;
        }

        .user-message {
            font-size: 14px;
            color: #666;
            margin-bottom: 8px;
            padding-left: 52px;
        }

        .user-message .username {
            color: #888;
            font-weight: 500;
        }

        .response {
            font-size: 22px;
            color: #333;
            line-height: 1.5;
            padding-left: 52px;
        }

        .response.typing::after {
            content: '|';
            animation: blink 0.7s infinite;
        }

        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0; }
        }

        .sparkle {
            position: absolute;
            width: 10px;
            height: 10px;
            background: #ff69b4;
            border-radius: 50%;
            opacity: 0;
            animation: sparkle 1.5s ease-in-out infinite;
        }

        @keyframes sparkle {
            0%, 100% { opacity: 0; transform: scale(0); }
            50% { opacity: 1; transform: scale(1); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="message-box" id="messageBox">
            <div class="header">
                <div class="avatar">糖</div>
                <div class="name">XiaoTang</div>
            </div>
            <div class="user-message" id="userMessage"></div>
            <div class="response" id="response"></div>
        </div>
    </div>

    <script>
        const messageBox = document.getElementById('messageBox');
        const userMessage = document.getElementById('userMessage');
        const response = document.getElementById('response');

        let hideTimeout = null;
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
            if (hideTimeout) {
                clearTimeout(hideTimeout);
            }

            userMessage.innerHTML = `<span class="username">${username}:</span> ${message}`;
            response.textContent = responseText;

            messageBox.classList.remove('hiding');
            messageBox.classList.add('visible');

            const displayTime = Math.min(Math.max(responseText.length * 100, 5000), 15000);

            hideTimeout = setTimeout(() => {
                messageBox.classList.add('hiding');
                setTimeout(() => {
                    messageBox.classList.remove('visible', 'hiding');
                }, 400);
            }, displayTime);
        }

        connect();
    </script>
</body>
</html>'''
        return web.Response(text=html, content_type='text/html')
