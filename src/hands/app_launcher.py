"""App Launcher - Launch and manage applications on the computer."""

from __future__ import annotations

import asyncio
import subprocess
import os
from typing import Optional


# Common application paths on Windows
COMMON_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "browser": "start chrome",
    "chrome": "start chrome",
    "firefox": "start firefox",
    "edge": "start msedge",
    "explorer": "explorer.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "cmd": "cmd.exe",
    "vscode": "code",
    "spotify": "start spotify:",
    "discord": "start discord:",
    "obs": "start obs64.exe",
}


class AppLauncher:
    """Launch and manage applications."""

    def __init__(self) -> None:
        self._running_processes: dict[str, subprocess.Popen] = {}

    async def launch(
        self,
        app_name: str,
        args: list[str] | None = None,
        wait: bool = False,
    ) -> dict:
        """
        Launch an application.
        
        Args:
            app_name: Name or path of the application
            args: Optional command line arguments
            wait: Whether to wait for the app to finish
            
        Returns:
            Dict with status and process info
        """
        # Check if it's a known app alias
        command = COMMON_APPS.get(app_name.lower(), app_name)
        
        if args:
            command = f"{command} {' '.join(args)}"

        try:
            if wait:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                )
                return {
                    "status": "completed",
                    "app": app_name,
                    "returncode": result.returncode,
                    "stdout": result.stdout[:500] if result.stdout else None,
                    "stderr": result.stderr[:500] if result.stderr else None,
                }
            else:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self._running_processes[app_name] = process
                return {
                    "status": "launched",
                    "app": app_name,
                    "pid": process.pid,
                }
        except Exception as e:
            return {
                "status": "error",
                "app": app_name,
                "error": str(e),
            }

    async def open_url(self, url: str, browser: str = "default") -> dict:
        """Open a URL in a browser."""
        import webbrowser
        
        try:
            if browser == "default":
                webbrowser.open(url)
            else:
                webbrowser.get(browser).open(url)
            return {"status": "opened", "url": url}
        except Exception as e:
            return {"status": "error", "url": url, "error": str(e)}

    async def open_file(self, path: str) -> dict:
        """Open a file with its default application."""
        try:
            os.startfile(path)
            return {"status": "opened", "path": path}
        except Exception as e:
            return {"status": "error", "path": path, "error": str(e)}

    def list_known_apps(self) -> list[str]:
        """Return list of known application aliases."""
        return list(COMMON_APPS.keys())

    def get_running_processes(self) -> dict[str, int]:
        """Get currently tracked running processes."""
        return {name: proc.pid for name, proc in self._running_processes.items() if proc.poll() is None}
