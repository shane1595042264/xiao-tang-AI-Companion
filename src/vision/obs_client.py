"""OBS Vision Client - Captures screenshots from OBS via WebSocket."""

from __future__ import annotations

from typing import Optional


class OBSVisionClient:
    """
    Connects to OBS WebSocket v5 to capture screenshots of the stream.

    Uses obsws-python to communicate with OBS Studio.
    Gracefully degrades if OBS is not running.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: str = "",
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._width = width
        self._height = height
        self._client = None
        self._connected = False

    def connect(self) -> bool:
        """Attempt to connect to OBS WebSocket. Returns True if successful."""
        try:
            import obsws_python as obs

            self._client = obs.ReqClient(
                host=self._host,
                port=self._port,
                password=self._password,
                timeout=5,
            )
            self._connected = True
            print(f"[obs] Connected to OBS at {self._host}:{self._port}")
            return True
        except Exception as e:
            self._connected = False
            self._client = None
            print(f"[obs] Could not connect to OBS: {e}")
            print("[obs] Vision disabled — running in text-only mode")
            return False

    def disconnect(self) -> None:
        """Disconnect from OBS."""
        if self._client:
            try:
                self._client.base_client.ws.close()
            except Exception:
                pass
            self._client = None
            self._connected = False

    def get_current_scene(self) -> Optional[str]:
        """Get the name of the current OBS program scene."""
        if not self._connected or not self._client:
            return None
        try:
            resp = self._client.get_current_program_scene()
            return resp.scene_name
        except Exception as e:
            print(f"[obs] Failed to get scene: {e}")
            return None

    def take_screenshot(self, source_name: str | None = None) -> Optional[str]:
        """
        Take a screenshot from OBS.

        Args:
            source_name: OBS source to screenshot. If None, uses current scene.

        Returns:
            Base64 PNG string (without data URI prefix), or None on failure.
        """
        if not self._connected or not self._client:
            return None

        try:
            # Default to current scene
            if not source_name:
                scene_resp = self._client.get_current_program_scene()
                source_name = scene_resp.scene_name

            resp = self._client.get_source_screenshot(
                name=source_name,
                img_format="png",
                width=self._width,
                height=self._height,
                quality=-1,
            )

            # OBS returns a data URI: "data:image/png;base64,<base64data>"
            # Anthropic API expects raw base64 without the prefix
            image_data = resp.image_data
            if image_data.startswith("data:"):
                image_data = image_data.split(",", 1)[1]

            return image_data

        except Exception as e:
            print(f"[obs] Screenshot failed: {e}")
            return None

    @property
    def is_connected(self) -> bool:
        return self._connected
