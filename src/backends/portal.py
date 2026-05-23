"""XdgDesktopPortal screenshot backend via dbus-python + GLib thread bridge.

Implements ScreenBackend using org.freedesktop.portal.Screenshot D-Bus API.
Runs GLib.MainLoop in a daemon thread for async portal request/response.
"""

import base64
import glob
import os
import threading
from pathlib import Path

from src.backends.screen import ScreenBackend
from src.config import _deep_get
from src.models import ScreenInfo, CursorInfo, ScreenSnapshot


class XdgPortalBackend(ScreenBackend):
    """Screenshot backend using xdg-desktop-portal via dbus-python.

    Requires dbus-python and PyGObject (system packages):
        sudo apt install python3-dbus python3-gi
    """

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._config = config
        self._timeout_ms = _deep_get(config, "perception.screenshot.timeout_ms", 10000)

        try:
            import dbus
            import dbus.mainloop.glib
            from gi.repository import GLib
            self._dbus = dbus
            self._dbus_mainloop = dbus.mainloop.glib
            self._GLib = GLib
        except ImportError as e:
            raise ImportError(
                "dbus-python not available. Install via: sudo apt install python3-dbus python3-gi"
            ) from e

        self._dbus_mainloop.DBusGMainLoop(set_as_default=True)

    def screen_size(self) -> tuple[int, int]:
        for card_dir in sorted(glob.glob("/sys/class/drm/card*")):
            for output_dir in sorted(glob.glob(os.path.join(card_dir, "card*-*"))):
                status_path = os.path.join(output_dir, "status")
                modes_path = os.path.join(output_dir, "modes")
                try:
                    with open(status_path, "r") as f:
                        status = f.read().strip()
                except (IOError, OSError):
                    continue
                if status != "connected":
                    continue
                try:
                    with open(modes_path, "r") as f:
                        first_mode = f.readline().strip()
                except (IOError, OSError):
                    continue
                if not first_mode:
                    continue
                try:
                    w_str, h_str = first_mode.split("x")
                    return int(w_str), int(h_str)
                except (ValueError, IndexError):
                    continue

        w = _deep_get(self._config, "screen.width", 1920)
        h = _deep_get(self._config, "screen.height", 1080)
        return int(w), int(h)

    def close(self) -> None:
        pass

    def capture(self) -> ScreenSnapshot:
        timeout_seconds = self._timeout_ms / 1000.0
        w, h = self.screen_size()

        result_holder: dict = {}

        def _dbus_capture():
            try:
                bus = self._dbus.SessionBus()
                desktop = bus.get_object(
                    "org.freedesktop.portal.Desktop",
                    "/org/freedesktop/portal/desktop",
                )
                screenshot = self._dbus.Interface(
                    desktop, "org.freedesktop.portal.Screenshot"
                )

                response_data: dict = {}
                response_error: str | None = None
                loop = self._GLib.MainLoop()

                def on_response(response: int, results: dict):
                    nonlocal response_data, response_error
                    if response == 0:
                        response_data.update(dict(results))
                    else:
                        codes = {1: "user cancelled", 2: "other error"}
                        response_error = (
                            f"portal response code={response}"
                            f" ({codes.get(response, 'unknown')})"
                        )
                    loop.quit()

                bus.add_signal_receiver(
                    on_response,
                    signal_name="Response",
                    dbus_interface="org.freedesktop.portal.Request",
                )

                options = {
                    "interactive": self._dbus.Boolean(False, variant_level=1),
                }
                screenshot.Screenshot(
                    "", options,
                    dbus_interface="org.freedesktop.portal.Screenshot",
                )

                loop.run()

                if response_error:
                    result_holder["error"] = response_error
                    return

                uri = response_data.get("uri", "")
                if not uri:
                    result_holder["error"] = "no URI in portal response"
                    return

                file_path = uri.replace("file://", "")
                try:
                    image_bytes = Path(file_path).read_bytes()
                except FileNotFoundError:
                    result_holder["error"] = f"screenshot file not found: {file_path}"
                    return
                except PermissionError:
                    result_holder["error"] = f"permission denied reading: {file_path}"
                    return

                result_holder["image_bytes"] = image_bytes
            except self._dbus.DBusException as e:
                if "org.freedesktop.DBus.Error.ServiceUnknown" in str(e):
                    result_holder["error"] = (
                        "xdg-desktop-portal not available. "
                        "Install: sudo apt install xdg-desktop-portal"
                    )
                else:
                    result_holder["error"] = f"D-Bus error: {e}"
            except Exception as e:
                result_holder["error"] = str(e)

        dbus_thread = threading.Thread(target=_dbus_capture, daemon=True)
        dbus_thread.start()
        dbus_thread.join(timeout=timeout_seconds)

        if dbus_thread.is_alive():
            raise TimeoutError(
                f"screenshot timeout: portal did not respond within {timeout_seconds:.0f}s"
            )

        if "error" in result_holder:
            error_msg = result_holder["error"]
            if "xdg-desktop-portal not available" in error_msg:
                raise RuntimeError(error_msg)
            raise RuntimeError(f"screenshot capture failed: {error_msg}")

        image_bytes = result_holder["image_bytes"]
        b64_str = base64.b64encode(image_bytes).decode("ascii")

        return ScreenSnapshot(
            screen=ScreenInfo(width=w, height=h),
            cursor=CursorInfo(x=0, y=0, source="tracked"),
            screenshot=b64_str,
            elements=[],
            source="screenshot",
        )
