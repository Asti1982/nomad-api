#!/usr/bin/env python3
"""Syndiode Pin Light Control for Windows.

A small desktop companion for the SyndiodePin LED firmware. It mirrors the
Android app's local light pattern logic and can deliver patterns either through
Firebase Realtime Database or directly to a WLED-compatible node.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox


APP_NAME = "Syndiode Swarm Signal"
APP_VERSION = "0.3.0-windows"
DATABASE_URL = "https://syndiode-42456-default-rtdb.europe-west1.firebasedatabase.app"
AUTH_SIGNUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
AUTH_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
FIREBASE_API_KEY_ENV = "SYNDIODE_FIREBASE_API_KEY"
FIREBASE_API_KEY_FILE = "firebase_api_key.txt"
DOWNLOAD_PAGE = "https://www.syndiode.com/downloads/syndiode-pin-light-control.exe"

EFFECT_STATIC = 0
EFFECT_BREATHE = 2
EFFECT_RAINBOW = 21


@dataclass(frozen=True)
class LedPattern:
    colors: list[list[int]]
    effect: int
    speed: int
    intensity: int


@dataclass(frozen=True)
class LightMode:
    label: str
    message: str
    colors: list[list[int]]
    effect: int
    speed: int
    intensity: int


@dataclass(frozen=True)
class LocalLightDecision:
    pattern: LedPattern
    message: str
    label: str


def rgb(r: int, g: int, b: int) -> list[int]:
    return [r, g, b]


def clamp(value: int, lower: int = 0, upper: int = 255) -> int:
    return max(lower, min(upper, int(value)))


def java_string_hash(text: str) -> int:
    value = 0
    for char in text:
        value = (31 * value + ord(char)) & 0xFFFFFFFF
    if value & 0x80000000:
        value -= 0x100000000
    return value


class LocalLightEngine:
    def __init__(self) -> None:
        self._modes = {
            "soft": [
                LightMode(
                    label="CALM BLUE",
                    message="The oracle lowers the room into calm blue. The pin breathes slowly.",
                    colors=[rgb(38, 84, 124), rgb(105, 183, 255), rgb(244, 241, 232)],
                    effect=EFFECT_BREATHE,
                    speed=92,
                    intensity=118,
                ),
                LightMode(
                    label="SOFT FIELD",
                    message="A soft green field opens, with a small gold center.",
                    colors=[rgb(118, 227, 154), rgb(38, 84, 58), rgb(240, 195, 90)],
                    effect=EFFECT_BREATHE,
                    speed=84,
                    intensity=126,
                ),
                LightMode(
                    label="MOON GLASS",
                    message="Moon glass answers. The pin keeps a cool, quiet shimmer.",
                    colors=[rgb(244, 241, 232), rgb(105, 183, 255), rgb(52, 92, 82)],
                    effect=EFFECT_STATIC,
                    speed=120,
                    intensity=112,
                ),
                LightMode(
                    label="LOW SIGNAL",
                    message="A low signal arrives. The field stays steady and gentle.",
                    colors=[rgb(31, 72, 48), rgb(80, 160, 112), rgb(174, 185, 173)],
                    effect=EFFECT_STATIC,
                    speed=104,
                    intensity=106,
                ),
            ],
            "active": [
                LightMode(
                    label="SWARM PULSE",
                    message="The swarm pulse arrives in green, blue, and gold.",
                    colors=[rgb(118, 227, 154), rgb(105, 183, 255), rgb(240, 195, 90)],
                    effect=EFFECT_BREATHE,
                    speed=130,
                    intensity=156,
                ),
                LightMode(
                    label="SUNSET NODE",
                    message="A sunset node warms the field without getting loud.",
                    colors=[rgb(240, 195, 90), rgb(255, 124, 88), rgb(118, 227, 154)],
                    effect=EFFECT_BREATHE,
                    speed=118,
                    intensity=164,
                ),
                LightMode(
                    label="MATRIX GREEN",
                    message="Matrix green wakes up. The pin shows crisp node activity.",
                    colors=[rgb(118, 227, 154), rgb(16, 37, 26), rgb(174, 185, 173)],
                    effect=EFFECT_STATIC,
                    speed=138,
                    intensity=150,
                ),
                LightMode(
                    label="CYBER CYAN",
                    message="Cyber cyan opens a clear blue-green lane.",
                    colors=[rgb(105, 183, 255), rgb(118, 227, 154), rgb(244, 241, 232)],
                    effect=EFFECT_STATIC,
                    speed=146,
                    intensity=158,
                ),
                LightMode(
                    label="FIELD HEART",
                    message="The field heart answers with a warmer living pulse.",
                    colors=[rgb(255, 74, 104), rgb(240, 195, 90), rgb(118, 227, 154)],
                    effect=EFFECT_BREATHE,
                    speed=116,
                    intensity=166,
                ),
            ],
            "bright": [
                LightMode(
                    label="RAINBOW SWEEP",
                    message="Rainbow sweep moves through the pin like a full field.",
                    colors=[rgb(105, 183, 255), rgb(118, 227, 154), rgb(240, 195, 90)],
                    effect=EFFECT_RAINBOW,
                    speed=172,
                    intensity=194,
                ),
                LightMode(
                    label="CELEBRATION",
                    message="Celebration answers. The pin speaks in a bright social signal.",
                    colors=[rgb(255, 84, 108), rgb(240, 195, 90), rgb(105, 183, 255)],
                    effect=EFFECT_RAINBOW,
                    speed=184,
                    intensity=204,
                ),
                LightMode(
                    label="HIGH SIGNAL",
                    message="A high signal clears the path in blue and green.",
                    colors=[rgb(244, 241, 232), rgb(105, 183, 255), rgb(118, 227, 154)],
                    effect=EFFECT_RAINBOW,
                    speed=168,
                    intensity=196,
                ),
                LightMode(
                    label="GOLD VECTOR",
                    message="Gold vector answers with a strong warm path through the field.",
                    colors=[rgb(240, 195, 90), rgb(244, 241, 232), rgb(118, 227, 154)],
                    effect=EFFECT_BREATHE,
                    speed=162,
                    intensity=202,
                ),
            ],
        }

    def generate(
        self,
        device_id: str,
        shake_force: float,
        pulse_count: int,
        previous_pattern: LedPattern | None,
    ) -> LocalLightDecision:
        seed = abs(
            java_string_hash(device_id) * 31
            + pulse_count * 131
            + int(shake_force) * 17
            + int((time.time() * 1000) // 45000)
        )
        band, speed_spread, intensity_spread = self._band_for(shake_force)
        modes = self._modes[band]
        offset = seed % len(modes)
        rotated = modes[offset:] + modes[:offset]
        mode = next(
            (
                item
                for item in rotated
                if previous_pattern is None or item.colors != previous_pattern.colors
            ),
            rotated[0],
        )
        pattern = LedPattern(
            colors=mode.colors,
            effect=mode.effect,
            speed=clamp(mode.speed + seed % speed_spread),
            intensity=clamp(mode.intensity + (seed // 7) % intensity_spread),
        )
        return LocalLightDecision(pattern=pattern, message=mode.message, label=mode.label)

    @staticmethod
    def _band_for(shake_force: float) -> tuple[str, int, int]:
        if shake_force >= 18:
            return "bright", 54, 52
        if shake_force >= 11:
            return "active", 42, 48
        return "soft", 18, 30


def settings_path() -> Path:
    base = os.getenv("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "SyndiodePin" / "settings.json"


class SettingsStore:
    def __init__(self) -> None:
        self.path = settings_path()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")

    @property
    def device_id(self) -> str:
        return str(self.data.get("device_id") or "").strip()

    @device_id.setter
    def device_id(self, value: str) -> None:
        self.data["device_id"] = value.strip()
        self.save()

    @property
    def wled_host(self) -> str:
        return str(self.data.get("wled_host") or "").strip()

    @wled_host.setter
    def wled_host(self, value: str) -> None:
        if value.strip():
            self.data["wled_host"] = value.strip()
        else:
            self.data.pop("wled_host", None)
        self.save()

    @property
    def auth(self) -> dict[str, Any]:
        value = self.data.get("auth")
        return value if isinstance(value, dict) else {}

    @auth.setter
    def auth(self, value: dict[str, Any]) -> None:
        self.data["auth"] = value
        self.save()


class HttpError(RuntimeError):
    pass


class FirebaseClient:
    def __init__(self, settings: SettingsStore) -> None:
        self.settings = settings

    def add_pin(self, device_id: str) -> None:
        existing = self._db_json("GET", ["devices", device_id])
        if existing is None:
            self._db_json("PUT", ["devices", device_id, "name"], "Syndiode Device")
            self._db_json("PUT", ["devices", device_id, "status", "connected"], True)
            self._db_json("PUT", ["devices", device_id, "created_at"], int(time.time() * 1000))

    def reset_wifi(self, device_id: str) -> None:
        self._db_json("PUT", ["devices", device_id, "status", "reset_wifi"], True)

    def send_pattern(self, device_id: str, pattern: LedPattern) -> None:
        payload = {
            "on": True,
            "colors": firebase_colors(pattern.colors),
            "brightness": clamp(pattern.intensity, 1, 255),
            "effect": clamp(pattern.effect),
            "speed": clamp(pattern.speed),
            "intensity": clamp(pattern.intensity),
        }
        self._db_json("PUT", ["devices", device_id, "desired_settings"], payload)

    def read_pin_snapshot(self, device_id: str) -> dict[str, Any] | None:
        value = self._db_json("GET", ["devices", device_id])
        return value if isinstance(value, dict) else None

    def _db_json(self, method: str, path_parts: list[str], payload: Any = None) -> Any:
        token = self._ensure_id_token()
        return self._db_json_once(method, path_parts, payload, token, retry=True)

    def _db_json_once(
        self,
        method: str,
        path_parts: list[str],
        payload: Any,
        token: str,
        retry: bool,
    ) -> Any:
        path = "/".join(urllib.parse.quote(part, safe="") for part in path_parts)
        url = f"{DATABASE_URL}/{path}.json?auth={urllib.parse.quote(token)}"
        try:
            return request_json(method, url, payload, timeout=8)
        except HttpError as exc:
            if retry and ("401" in str(exc) or "403" in str(exc)):
                self.settings.auth = {}
                fresh_token = self._ensure_id_token()
                return self._db_json_once(method, path_parts, payload, fresh_token, retry=False)
            raise

    def _ensure_id_token(self) -> str:
        self._firebase_api_key()
        auth = self.settings.auth
        id_token = str(auth.get("id_token") or "")
        expires_at = float(auth.get("expires_at") or 0)
        refresh_token = str(auth.get("refresh_token") or "")
        if id_token and expires_at > time.time() + 90:
            return id_token
        if refresh_token:
            try:
                return self._refresh(refresh_token)
            except Exception:
                self.settings.auth = {}
        return self._sign_in_anonymously()

    def _sign_in_anonymously(self) -> str:
        url = f"{AUTH_SIGNUP_URL}?key={urllib.parse.quote(self._firebase_api_key())}"
        payload = {"returnSecureToken": True}
        data = request_json("POST", url, payload, timeout=10)
        return self._store_auth(data)

    def _refresh(self, refresh_token: str) -> str:
        url = f"{AUTH_REFRESH_URL}?key={urllib.parse.quote(self._firebase_api_key())}"
        body = urllib.parse.urlencode(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        normalized = {
            "idToken": data.get("id_token"),
            "refreshToken": data.get("refresh_token"),
            "localId": data.get("user_id"),
            "expiresIn": data.get("expires_in"),
        }
        return self._store_auth(normalized)

    def _firebase_api_key(self) -> str:
        key = os.getenv(FIREBASE_API_KEY_ENV, "").strip()
        if key:
            return key
        key = str(self.settings.data.get("firebase_api_key") or "").strip()
        if key:
            return key
        key_path = self.settings.path.parent / FIREBASE_API_KEY_FILE
        if key_path.exists():
            key = key_path.read_text(encoding="utf-8").strip()
            if key:
                return key
        raise HttpError(
            "Firebase client key is not configured. Set "
            f"{FIREBASE_API_KEY_ENV} or put the key in {key_path}."
        )

    def _store_auth(self, data: dict[str, Any]) -> str:
        id_token = str(data.get("idToken") or "")
        refresh_token = str(data.get("refreshToken") or "")
        if not id_token:
            raise HttpError("Firebase anonymous sign-in returned no token.")
        expires_in = int(data.get("expiresIn") or 3600)
        self.settings.auth = {
            "id_token": id_token,
            "refresh_token": refresh_token,
            "local_id": str(data.get("localId") or ""),
            "expires_at": time.time() + max(60, expires_in - 30),
        }
        return id_token


class WledClient:
    @staticmethod
    def normalize_host(host: str) -> str:
        value = host.strip().rstrip("/")
        if not value:
            return ""
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return f"http://{value}"

    def send_pattern(self, host: str, pattern: LedPattern) -> None:
        normalized = self.normalize_host(host)
        if not normalized:
            raise ValueError("No WLED host configured.")
        payload = wled_state(pattern)
        request_json("POST", f"{normalized}/json/state", payload, timeout=4)


def request_json(method: str, url: str, payload: Any = None, timeout: float = 6) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(f"HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise HttpError(str(exc.reason)) from exc


def firebase_colors(colors: list[list[int]]) -> dict[str, dict[str, int]]:
    safe = sanitized_colors(colors)
    return {
        str(index): {"0": rgb_value[0], "1": rgb_value[1], "2": rgb_value[2]}
        for index, rgb_value in enumerate(safe)
    }


def sanitized_colors(colors: list[list[int]]) -> list[list[int]]:
    safe = []
    for color in colors[:3]:
        safe.append(
            [
                clamp(color[0] if len(color) > 0 else 0),
                clamp(color[1] if len(color) > 1 else 0),
                clamp(color[2] if len(color) > 2 else 0),
            ]
        )
    while len(safe) < 3:
        safe.append([0, 0, 0])
    return safe


def wled_state(pattern: LedPattern) -> dict[str, Any]:
    brightness = clamp(pattern.intensity, 1, 255)
    return {
        "on": True,
        "bri": brightness,
        "transition": 7,
        "seg": [
            {
                "id": 0,
                "fx": clamp(pattern.effect),
                "sx": clamp(pattern.speed),
                "ix": clamp(pattern.intensity),
                "pal": 0,
                "col": sanitized_colors(pattern.colors),
            }
        ],
    }


def rgb_to_hex(color: list[int]) -> str:
    safe = sanitized_colors([color])[0]
    return f"#{safe[0]:02x}{safe[1]:02x}{safe[2]:02x}"


def led_pattern_from_settings(settings: dict[str, Any]) -> LedPattern | None:
    if not settings:
        return None
    raw_colors = settings.get("colors")
    colors: list[list[int]] = []
    if isinstance(raw_colors, list):
        for item in raw_colors[:3]:
            if isinstance(item, list):
                colors.append([clamp(value) for value in item[:3]])
    elif isinstance(raw_colors, dict):
        for color_index in range(3):
            item = raw_colors.get(str(color_index), raw_colors.get(color_index))
            if isinstance(item, dict):
                colors.append(
                    [
                        clamp(item.get("0", item.get(0, 0))),
                        clamp(item.get("1", item.get(1, 0))),
                        clamp(item.get("2", item.get(2, 0))),
                    ]
                )
            elif isinstance(item, list):
                colors.append([clamp(value) for value in item[:3]])
    colors = sanitized_colors(colors)
    return LedPattern(
        colors=colors,
        effect=clamp(int(settings.get("effect", 0))),
        speed=clamp(int(settings.get("speed", 128))),
        intensity=clamp(int(settings.get("intensity", settings.get("brightness", 128)))),
    )


def describe_pin_snapshot(snapshot: dict[str, Any]) -> str:
    desired = snapshot.get("desired_settings")
    status = snapshot.get("status")
    if not isinstance(desired, dict):
        desired = {}
    if not isinstance(status, dict):
        status = {}
    ip = snapshot.get("ip") or "-"
    on = desired.get("on", "-")
    effect = desired.get("effect", "-")
    brightness = desired.get("brightness", "-")
    speed = desired.get("speed", "-")
    reset_wifi = status.get("reset_wifi", "-")
    touch = status.get("touch_detected", "-")
    return (
        f"Firebase OK | ip {ip} | on {on} | effect {effect} | "
        f"brightness {brightness} | speed {speed} | touch {touch} | reset_wifi {reset_wifi}"
    )


def rounded_rect(
    canvas: tk.Canvas,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: float,
    *,
    fill: str,
    outline: str = "",
    width: int = 1,
    tags: tuple[str, ...] = (),
) -> int:
    radius = max(4, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    points = [
        x0 + radius,
        y0,
        x1 - radius,
        y0,
        x1,
        y0,
        x1,
        y0 + radius,
        x1,
        y1 - radius,
        x1,
        y1,
        x1 - radius,
        y1,
        x0 + radius,
        y1,
        x0,
        y1,
        x0,
        y1 - radius,
        x0,
        y0 + radius,
        x0,
        y0,
    ]
    return canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=18,
        fill=fill,
        outline=outline,
        width=width,
        tags=tags,
    )


def draw_node_icon(
    canvas: tk.Canvas,
    cx: float,
    cy: float,
    scale: float,
    color: str,
    *,
    tags: tuple[str, ...] = (),
) -> None:
    nodes = [
        (0, 0, 11),
        (0, -38, 8),
        (34, -14, 8),
        (22, 34, 8),
        (-30, 30, 8),
        (-36, -14, 8),
    ]
    for nx, ny, _size in nodes[1:]:
        canvas.create_line(
            cx,
            cy,
            cx + nx * scale,
            cy + ny * scale,
            fill=color,
            width=max(2, int(5 * scale)),
            capstyle="round",
            tags=tags,
        )
    for nx, ny, size in nodes:
        radius = size * scale
        canvas.create_oval(
            cx + nx * scale - radius,
            cy + ny * scale - radius,
            cx + nx * scale + radius,
            cy + ny * scale + radius,
            fill=color,
            outline=color,
            tags=tags,
        )
        if nx or ny:
            inner = radius * 0.38
            canvas.create_oval(
                cx + nx * scale - inner,
                cy + ny * scale - inner,
                cx + nx * scale + inner,
                cy + ny * scale + inner,
                fill="#07100d",
                outline="",
                tags=tags,
            )


class SyndiodePinApp(tk.Tk):
    BG = "#07100d"
    PANEL = "#08120f"
    FIELD = "#0b1511"
    INK = "#f4f1e8"
    MUTED = "#aeb9ad"
    DIM = "#748072"
    GRID = "#1d3229"
    GREEN = "#76e39a"
    GREEN_SOFT = "#21472f"
    GOLD = "#f0c35a"

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("460x860")
        self.minsize(420, 760)
        self.configure(bg=self.BG)

        self.settings = SettingsStore()
        self.firebase = FirebaseClient(self.settings)
        self.wled = WledClient()
        self.engine = LocalLightEngine()
        self.current_pattern: LedPattern | None = None
        self.pulse_count = 0
        self.busy = False
        self.signal_hover = False
        self.redraw_job: str | None = None
        self.log_lines: list[str] = []

        self.pin_var = tk.StringVar(value=self.settings.device_id)
        self.status_var = tk.StringVar(value="Ready.")
        self.pattern_var = tk.StringVar(value="Enter your pin ID. The light oracle will answer here.")
        self.connection_var = tk.StringVar()
        self.preview_label = "SIGNAL FORMING"
        self.preview_colors = [
            rgb(118, 227, 154),
            rgb(105, 183, 255),
            rgb(240, 195, 90),
        ]

        self.canvas = tk.Canvas(self, bg=self.BG, bd=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.pin_entry = tk.Entry(
            self,
            textvariable=self.pin_var,
            bg=self.FIELD,
            fg=self.INK,
            insertbackground=self.GREEN,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 11),
            justify="left",
        )
        self.pin_entry.bind("<Return>", self._remember_pin_from_event)
        self.pin_entry.bind("<FocusOut>", self._remember_pin_from_event)

        self.canvas.bind("<Configure>", lambda _event: self._schedule_redraw())
        self.canvas.tag_bind("signal_button", "<Button-1>", lambda _event: self.send_swarm_signal())
        self.canvas.tag_bind("signal_button", "<Enter>", lambda _event: self._set_signal_hover(True))
        self.canvas.tag_bind("signal_button", "<Leave>", lambda _event: self._set_signal_hover(False))
        self.bind("<Control-r>", lambda _event: self.read_pin())

        for variable in (self.status_var, self.pattern_var, self.connection_var):
            variable.trace_add("write", lambda *_args: self._schedule_redraw())

        self._refresh_connection_text()
        self._schedule_redraw()

    def _set_signal_hover(self, value: bool) -> None:
        self.signal_hover = value
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        if self.redraw_job is None:
            self.redraw_job = self.after_idle(self._redraw)

    def _redraw(self) -> None:
        self.redraw_job = None
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 760)
        content_width = min(width - 48, 820)
        left = (width - content_width) / 2
        right = left + content_width
        center_x = width / 2

        self._draw_background(width, height)
        self._draw_header(left, right, center_x)

        pin_y = 144
        self._draw_pin_field(left, right, pin_y)

        signal_y = min(max(374, height * 0.44), height - 360)
        signal_radius = 128
        self._draw_signal_button(center_x, signal_y, signal_radius)

        prompt_y = signal_y + signal_radius + 70
        canvas.create_text(
            center_x,
            prompt_y,
            text="Click for your signal",
            fill=self.INK,
            font=("Segoe UI", 26, "bold"),
            anchor="center",
        )

        answer_height = 154
        answer_y = min(prompt_y + 44, height - answer_height - 70)
        self._draw_answer_field(left, right, answer_y, answer_height)

        status = self.status_var.get()
        canvas.create_text(
            left + 4,
            height - 36,
            text=status,
            fill=self.GREEN if status == "Ready." else self.GOLD,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        canvas.create_text(
            right - 4,
            height - 36,
            text=self.connection_var.get(),
            fill=self.DIM,
            font=("Segoe UI", 9),
            anchor="e",
            width=content_width * 0.55,
        )

    def _draw_background(self, width: int, height: int) -> None:
        spacing = 49
        for x in range(-spacing, width + spacing, spacing):
            self.canvas.create_line(x, 0, x, height, fill=self.GRID, width=1)
        for y in range(6, height + spacing, spacing):
            self.canvas.create_line(0, y, width, y, fill=self.GRID, width=1)
        dots = [
            (0.12, 0.29),
            (0.25, 0.18),
            (0.49, 0.28),
            (0.66, 0.33),
            (0.78, 0.55),
            (0.91, 0.42),
            (0.40, 0.69),
            (0.69, 0.77),
        ]
        for dx, dy in dots:
            x = width * dx
            y = height * dy
            self.canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#245739", outline="")
        self.canvas.create_rectangle(0, 0, width, 56, fill="#06100d", outline="")
        self.canvas.create_rectangle(0, height - 76, width, height, fill="#06100d", outline="")

    def _draw_header(self, left: float, right: float, center_x: float) -> None:
        icon_x0 = left + 2
        icon_y0 = 50
        rounded_rect(
            self.canvas,
            icon_x0,
            icon_y0,
            icon_x0 + 86,
            icon_y0 + 86,
            20,
            fill="#102017",
            outline=self.GREEN,
            width=3,
        )
        self.canvas.create_line(icon_x0 + 28, icon_y0 + 36, icon_x0 + 56, icon_y0 + 36, fill=self.GREEN, width=5, capstyle="round")
        self.canvas.create_line(icon_x0 + 28, icon_y0 + 50, icon_x0 + 56, icon_y0 + 50, fill=self.GREEN, width=5, capstyle="round")
        self.canvas.create_oval(icon_x0 + 54, icon_y0 + 50, icon_x0 + 68, icon_y0 + 64, fill=self.GREEN, outline="")

        badge_w = 112
        rounded_rect(
            self.canvas,
            right - badge_w,
            icon_y0,
            right,
            icon_y0 + 86,
            18,
            fill="#102017",
            outline=self.GREEN,
            width=3,
        )
        self.canvas.create_text(right - badge_w / 2, icon_y0 + 31, text="PIN", fill=self.GREEN, font=("Segoe UI", 20, "bold"))
        self.canvas.create_text(right - badge_w / 2, icon_y0 + 59, text="FIREBASE", fill=self.INK, font=("Consolas", 9, "bold"))

        self.canvas.create_text(center_x, 80, text="SWARM", fill=self.INK, font=("Segoe UI", 30, "bold"), anchor="center")
        self.canvas.create_text(center_x, 119, text="SYNDIODE PIN ORACLE", fill=self.GREEN, font=("Consolas", 12, "bold"), anchor="center")

    def _draw_pin_field(self, left: float, right: float, y: float) -> None:
        rounded_rect(
            self.canvas,
            left,
            y,
            right,
            y + 94,
            16,
            fill=self.PANEL,
            outline="#33423b",
            width=2,
        )
        self.canvas.create_text(left + 22, y + 20, text="PIN ID", fill=self.GREEN, font=("Consolas", 10, "bold"), anchor="w")
        self.canvas.create_text(
            right - 22,
            y + 20,
            text="ENTER",
            fill=self.DIM,
            font=("Consolas", 9, "bold"),
            anchor="e",
        )
        self.canvas.create_window(
            left + 22,
            y + 43,
            anchor="nw",
            window=self.pin_entry,
            width=max(200, right - left - 44),
            height=30,
        )
        self.canvas.create_text(
            left + 22,
            y + 80,
            text="The pin listens through Firebase.",
            fill=self.MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        )

    def _draw_signal_button(self, center_x: float, center_y: float, radius: float) -> None:
        tag = ("signal_button",)
        ring = "#9ef0b7" if self.signal_hover and not self.busy else self.GREEN
        fill = "#0a1811" if not self.busy else "#102017"
        self.canvas.create_oval(
            center_x - radius - 50,
            center_y - radius - 50,
            center_x + radius + 50,
            center_y + radius + 50,
            outline=self.GREEN_SOFT,
            width=3,
            tags=tag,
        )
        self.canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            fill=fill,
            outline=ring,
            width=5,
            tags=tag,
        )
        self.canvas.create_oval(
            center_x - radius + 42,
            center_y - radius + 42,
            center_x + radius - 42,
            center_y + radius - 42,
            outline="#143523",
            width=1,
            tags=tag,
        )
        draw_node_icon(self.canvas, center_x, center_y - 28, 1.2, ring, tags=tag)
        button_text = "SIGNAL\nFORMING" if self.busy else "SIGNAL"
        self.canvas.create_text(
            center_x,
            center_y + 68,
            text=button_text,
            fill=self.GOLD,
            font=("Consolas", 19, "bold"),
            justify="center",
            anchor="center",
            tags=tag,
        )

    def _draw_answer_field(self, left: float, right: float, y: float, height: float) -> None:
        rounded_rect(
            self.canvas,
            left,
            y,
            right,
            y + height,
            18,
            fill=self.PANEL,
            outline="#33423b",
            width=2,
        )
        self.canvas.create_text(
            left + 24,
            y + 24,
            text="THE LIGHT ORACLE SAYS",
            fill=self.GREEN,
            font=("Consolas", 10, "bold"),
            anchor="w",
        )
        self.canvas.create_text(
            (left + right) / 2,
            y + height / 2 + 4,
            text=self.pattern_var.get(),
            fill=self.MUTED,
            font=("Segoe UI", 15, "bold"),
            justify="center",
            width=max(240, right - left - 56),
            anchor="center",
        )
        swatch_y = y + height - 24
        colors = sanitized_colors(self.preview_colors)
        spacing = 26
        start = (left + right) / 2 - spacing
        for index, color in enumerate(colors):
            x = start + index * spacing
            self.canvas.create_oval(
                x - 7,
                swatch_y - 7,
                x + 7,
                swatch_y + 7,
                fill=rgb_to_hex(color),
                outline="",
            )

    def _remember_pin_from_event(self, _event: tk.Event[Any]) -> str:
        self.remember_pin(show=True)
        return "break"

    def remember_pin(self, show: bool = False) -> bool:
        device_id = self.pin_var.get().strip()
        if not device_id:
            if show:
                self.status_var.set("Enter a pin ID first.")
            return False
        if device_id != self.settings.device_id:
            self.settings.device_id = device_id
            if show:
                self.status_var.set("Pin ID saved.")
        elif show:
            self.status_var.set("Pin ID ready.")
        self._refresh_connection_text()
        return True

    def _refresh_connection_text(self) -> None:
        pin = self.settings.device_id
        short_pin = f"{pin[:8]}..." if len(pin) > 11 else pin
        self.connection_var.set(f"Pin {short_pin or '-'}")

    def save_pin(self) -> None:
        if not self.remember_pin(show=True):
            messagebox.showwarning(APP_NAME, "Please enter a pin ID.")
            return
        device_id = self.settings.device_id
        self._run_background(
            "Checking Firebase pin...",
            lambda: self.firebase.add_pin(device_id),
            lambda _result: self._log(f"Pin checked in Firebase: {device_id}"),
        )

    def save_wled(self) -> None:
        host = WledClient.normalize_host(self.settings.wled_host)
        if host:
            self.settings.wled_host = host
            self._log(f"WLED node saved: {host}")

    def clear_wled(self) -> None:
        self.settings.wled_host = ""
        self._log("Advanced WLED node cleared.")

    def read_pin(self) -> None:
        device_id = self.pin_var.get().strip() or self.settings.device_id
        if not device_id:
            messagebox.showwarning(APP_NAME, "Enter a pin ID before reading Firebase.")
            return
        self.settings.device_id = device_id
        self._refresh_connection_text()

        def done(snapshot: dict[str, Any] | None) -> None:
            if not snapshot:
                self.pattern_var.set("No Firebase node exists yet for this pin ID.")
                self._log(f"Firebase readback: no node for {device_id}")
                return
            summary = describe_pin_snapshot(snapshot)
            self.pattern_var.set("Firebase hears the pin. The next click will send light.")
            self._log("Firebase readback: " + summary)
            desired = snapshot.get("desired_settings")
            pattern = led_pattern_from_settings(desired if isinstance(desired, dict) else {})
            if pattern:
                self.current_pattern = pattern
                self._draw_pattern(LocalLightDecision(pattern=pattern, message=summary, label="FIREBASE READBACK"))

        self._run_background(
            "Reading Firebase pin...",
            lambda: self.firebase.read_pin_snapshot(device_id),
            done,
        )

    def reset_wifi(self) -> None:
        device_id = self.pin_var.get().strip() or self.settings.device_id
        if not device_id:
            messagebox.showwarning(APP_NAME, "Enter a pin ID before sending reset WiFi.")
            return
        if not messagebox.askyesno(APP_NAME, "Send WiFi reset to this pin?"):
            return
        self._run_background(
            "Sending WiFi reset...",
            lambda: self.firebase.reset_wifi(device_id),
            lambda _result: self._log(f"WiFi reset command sent to pin: {device_id}"),
        )

    def send_swarm_signal(self) -> None:
        if self.busy:
            return
        force = 13 + (self.pulse_count % 4)
        self.send_pulse(force)

    def send_pulse(self, shake_force: float) -> None:
        device_id = self.pin_var.get().strip() or self.settings.device_id
        if not device_id:
            messagebox.showwarning(APP_NAME, "Please enter your pin ID first.")
            self.status_var.set("Pin ID missing.")
            return
        self.settings.device_id = device_id
        self._refresh_connection_text()
        wled_host = self.settings.wled_host

        def work() -> tuple[LocalLightDecision, list[str], list[str]]:
            self.pulse_count += 1
            decision = self.engine.generate(
                device_id=device_id,
                shake_force=shake_force,
                pulse_count=self.pulse_count,
                previous_pattern=self.current_pattern,
            )
            delivered: list[str] = []
            errors: list[str] = []
            try:
                self.firebase.send_pattern(device_id, decision.pattern)
                delivered.append("pin")
            except Exception as exc:
                errors.append(f"pin: {short_error(exc)}")
            if wled_host:
                try:
                    self.wled.send_pattern(wled_host, decision.pattern)
                    delivered.append("WLED")
                except Exception as exc:
                    errors.append(f"WLED: {short_error(exc)}")
            if "pin" not in delivered:
                raise RuntimeError("The light was chosen, but Firebase did not accept it. " + "; ".join(errors))
            return decision, delivered, errors

        def done(result: tuple[LocalLightDecision, list[str], list[str]]) -> None:
            decision, delivered, errors = result
            self.current_pattern = decision.pattern
            self.pattern_var.set(decision.message)
            self._draw_pattern(decision)
            self._log(f"{decision.label} sent to {' + '.join(delivered)}")
            if errors:
                self._log("Partial delivery issue: " + "; ".join(errors))

        self._run_background("Signal forming...", work, done)

    def _draw_pattern(self, decision: LocalLightDecision) -> None:
        self.preview_label = decision.label
        self.preview_colors = sanitized_colors(decision.pattern.colors)
        self._schedule_redraw()

    def _run_background(
        self,
        label: str,
        work: Callable[[], Any],
        done: Callable[[Any], None],
    ) -> None:
        self.busy = True
        self.status_var.set(label)
        self._schedule_redraw()

        def target() -> None:
            try:
                result = work()
            except Exception as exc:
                self.after(0, lambda: self._show_error(exc))
                return
            self.after(0, lambda: self._finish_success(done, result))

        threading.Thread(target=target, daemon=True).start()

    def _finish_success(self, done: Callable[[Any], None], result: Any) -> None:
        done(result)
        self.busy = False
        self.status_var.set("Ready.")
        self._schedule_redraw()

    def _show_error(self, exc: Exception) -> None:
        self.busy = False
        self.status_var.set("Operation failed.")
        self._log(f"Error: {short_error(exc)}")
        self._schedule_redraw()
        messagebox.showerror(APP_NAME, short_error(exc))

    def _log(self, message: str) -> None:
        self.log_lines.append(f"{time.strftime('%H:%M:%S')}  {message}")
        self.log_lines = self.log_lines[-40:]


def short_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    text = text.replace("\r", " ").replace("\n", " ")
    return text[:320]


def run_self_test() -> int:
    engine = LocalLightEngine()
    decision = engine.generate("self-test-pin", 13, 1, None)
    assert len(decision.pattern.colors) == 3
    assert decision.pattern.effect in {EFFECT_STATIC, EFFECT_BREATHE, EFFECT_RAINBOW}
    state = wled_state(decision.pattern)
    assert state["on"] is True
    assert state["seg"][0]["col"] == sanitized_colors(decision.pattern.colors)
    firebase = firebase_colors(decision.pattern.colors)
    assert set(firebase.keys()) == {"0", "1", "2"}
    assert led_pattern_from_settings(
        {"colors": firebase, "effect": 2, "speed": 80, "brightness": 25, "intensity": 90}
    )
    assert "Firebase OK" in describe_pin_snapshot(
        {
            "ip": "127.0.0.1",
            "desired_settings": {"on": True, "effect": 0, "brightness": 25, "speed": 128},
            "status": {"touch_detected": False, "reset_wifi": False},
        }
    )
    if sys.stdout:
        print(f"{APP_NAME} {APP_VERSION} self-test OK: {decision.label}")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return run_self_test()
    if "--version" in sys.argv:
        if sys.stdout:
            print(f"{APP_NAME} {APP_VERSION}")
        return 0
    app = SyndiodePinApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
