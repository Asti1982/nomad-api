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
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "Syndiode Swarm Signal"
APP_VERSION = "0.2.0-windows"
DATABASE_URL = "https://syndiode-42456-default-rtdb.europe-west1.firebasedatabase.app"
AUTH_SIGNUP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
AUTH_REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
FIREBASE_API_KEY = os.getenv(
    "SYNDIODE_FIREBASE_API_KEY",
    "AIzaSyCrxrCVl0OcB0ko25mXRPPzRRmfeI5_QEU",
)
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
                    message="Calm blue selected. The pin settles into a slow breathable field.",
                    colors=[rgb(38, 84, 124), rgb(105, 183, 255), rgb(244, 241, 232)],
                    effect=EFFECT_BREATHE,
                    speed=92,
                    intensity=118,
                ),
                LightMode(
                    label="SOFT FIELD",
                    message="Soft field selected. The pin glows green with a small gold center.",
                    colors=[rgb(118, 227, 154), rgb(38, 84, 58), rgb(240, 195, 90)],
                    effect=EFFECT_BREATHE,
                    speed=84,
                    intensity=126,
                ),
                LightMode(
                    label="MOON GLASS",
                    message="Moon glass selected. The pin keeps a cool, quiet shimmer.",
                    colors=[rgb(244, 241, 232), rgb(105, 183, 255), rgb(52, 92, 82)],
                    effect=EFFECT_STATIC,
                    speed=120,
                    intensity=112,
                ),
                LightMode(
                    label="LOW SIGNAL",
                    message="Low signal selected. The pin shows a steady field for a softer room.",
                    colors=[rgb(31, 72, 48), rgb(80, 160, 112), rgb(174, 185, 173)],
                    effect=EFFECT_STATIC,
                    speed=104,
                    intensity=106,
                ),
            ],
            "active": [
                LightMode(
                    label="SWARM PULSE",
                    message="Swarm pulse selected. The pin shifts between green, blue, and gold.",
                    colors=[rgb(118, 227, 154), rgb(105, 183, 255), rgb(240, 195, 90)],
                    effect=EFFECT_BREATHE,
                    speed=130,
                    intensity=156,
                ),
                LightMode(
                    label="SUNSET NODE",
                    message="Sunset node selected. The pin warms the field without getting loud.",
                    colors=[rgb(240, 195, 90), rgb(255, 124, 88), rgb(118, 227, 154)],
                    effect=EFFECT_BREATHE,
                    speed=118,
                    intensity=164,
                ),
                LightMode(
                    label="MATRIX GREEN",
                    message="Matrix green selected. The pin shows crisp node activity.",
                    colors=[rgb(118, 227, 154), rgb(16, 37, 26), rgb(174, 185, 173)],
                    effect=EFFECT_STATIC,
                    speed=138,
                    intensity=150,
                ),
                LightMode(
                    label="CYBER CYAN",
                    message="Cyber cyan selected. The pin opens a clear blue-green lane.",
                    colors=[rgb(105, 183, 255), rgb(118, 227, 154), rgb(244, 241, 232)],
                    effect=EFFECT_STATIC,
                    speed=146,
                    intensity=158,
                ),
                LightMode(
                    label="FIELD HEART",
                    message="Field heart selected. The pin carries a warmer living pulse.",
                    colors=[rgb(255, 74, 104), rgb(240, 195, 90), rgb(118, 227, 154)],
                    effect=EFFECT_BREATHE,
                    speed=116,
                    intensity=166,
                ),
            ],
            "bright": [
                LightMode(
                    label="RAINBOW SWEEP",
                    message="Rainbow sweep selected. The pin runs a full moving field.",
                    colors=[rgb(105, 183, 255), rgb(118, 227, 154), rgb(240, 195, 90)],
                    effect=EFFECT_RAINBOW,
                    speed=172,
                    intensity=194,
                ),
                LightMode(
                    label="CELEBRATION",
                    message="Celebration selected. The pin answers with a bright social signal.",
                    colors=[rgb(255, 84, 108), rgb(240, 195, 90), rgb(105, 183, 255)],
                    effect=EFFECT_RAINBOW,
                    speed=184,
                    intensity=204,
                ),
                LightMode(
                    label="HIGH SIGNAL",
                    message="High signal selected. The pin shows a clean blue-green sweep.",
                    colors=[rgb(244, 241, 232), rgb(105, 183, 255), rgb(118, 227, 154)],
                    effect=EFFECT_RAINBOW,
                    speed=168,
                    intensity=196,
                ),
                LightMode(
                    label="GOLD VECTOR",
                    message="Gold vector selected. The pin sends a strong warm path through the field.",
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
        url = f"{AUTH_SIGNUP_URL}?key={urllib.parse.quote(FIREBASE_API_KEY)}"
        payload = {"returnSecureToken": True}
        data = request_json("POST", url, payload, timeout=10)
        return self._store_auth(data)

    def _refresh(self, refresh_token: str) -> str:
        url = f"{AUTH_REFRESH_URL}?key={urllib.parse.quote(FIREBASE_API_KEY)}"
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


class SyndiodePinApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("800x700")
        self.minsize(720, 620)
        self.configure(bg="#07100d")

        self.settings = SettingsStore()
        self.firebase = FirebaseClient(self.settings)
        self.wled = WledClient()
        self.engine = LocalLightEngine()
        self.current_pattern: LedPattern | None = None
        self.pulse_count = 0

        self.pin_var = tk.StringVar(value=self.settings.device_id)
        self.wled_var = tk.StringVar(value=self.settings.wled_host)
        self.status_var = tk.StringVar(value="Ready.")
        self.pattern_var = tk.StringVar(value="The next signal is forming around the pin.")
        self.connection_var = tk.StringVar()
        self.advanced_visible = bool(self.settings.wled_host)

        self._setup_style()
        self._build_ui()
        self._refresh_connection_text()

    def _setup_style(self) -> None:
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Root.TFrame", background="#07100d")
        self.style.configure("Panel.TFrame", background="#0b1511", relief="flat")
        self.style.configure("Title.TLabel", background="#07100d", foreground="#f4f1e8", font=("Segoe UI", 28, "bold"))
        self.style.configure("Subtitle.TLabel", background="#07100d", foreground="#aeb9ad", font=("Segoe UI", 10))
        self.style.configure("Swarm.TLabel", background="#07100d", foreground="#76e39a", font=("Consolas", 11, "bold"))
        self.style.configure("PanelTitle.TLabel", background="#0b1511", foreground="#f4f1e8", font=("Segoe UI", 12, "bold"))
        self.style.configure("PanelText.TLabel", background="#0b1511", foreground="#aeb9ad", font=("Segoe UI", 9))
        self.style.configure("Status.TLabel", background="#07100d", foreground="#76e39a", font=("Segoe UI", 10, "bold"))
        self.style.configure("TEntry", fieldbackground="#f7fbf8", foreground="#14231d")
        self.style.configure("TButton", font=("Segoe UI", 9), padding=(12, 7))
        self.style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(12, 8), background="#76e39a", foreground="#07100d")
        self.style.configure("Signal.TButton", font=("Segoe UI", 19, "bold"), padding=(18, 18), background="#76e39a", foreground="#07100d")
        self.style.map("Signal.TButton", background=[("active", "#9ef0b7"), ("disabled", "#748072")])
        self.style.map("Primary.TButton", background=[("active", "#9ef0b7")])

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=22)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="SWARM", style="Swarm.TLabel").pack(anchor="w")
        ttk.Label(root, text="Syndiode Pin", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="AI swarm signal for your physical pin. One click is enough.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))

        node = ttk.Frame(root, style="Panel.TFrame", padding=16)
        node.pack(fill="x", pady=(0, 14))
        ttk.Label(node, text="Pin connection", style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(node, text="Pin ID", style="PanelText.TLabel").grid(row=1, column=0, sticky="w", pady=(14, 4))
        ttk.Entry(node, textvariable=self.pin_var).grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 10))
        ttk.Button(node, text="Save pin", style="Primary.TButton", command=self.save_pin).grid(row=2, column=2, sticky="ew", padx=(0, 10))
        ttk.Button(node, text="Firebase test", command=self.read_pin).grid(row=2, column=3, sticky="ew")
        ttk.Label(node, textvariable=self.connection_var, style="PanelText.TLabel").grid(row=3, column=0, columnspan=4, sticky="w", pady=(12, 0))
        ttk.Button(node, text="Reset WiFi", command=self.reset_wifi).grid(row=4, column=0, sticky="w", pady=(12, 0))
        ttk.Button(node, text="Advanced WLED", command=self.toggle_advanced).grid(row=4, column=1, sticky="w", pady=(12, 0))
        ttk.Button(node, text="Open download", command=lambda: webbrowser.open(DOWNLOAD_PAGE)).grid(row=4, column=3, sticky="e", pady=(12, 0))
        node.columnconfigure(0, weight=1)
        node.columnconfigure(1, weight=1)
        node.columnconfigure(2, weight=0)
        node.columnconfigure(3, weight=0)

        pulse = ttk.Frame(root, style="Panel.TFrame", padding=16)
        pulse.pack(fill="x", pady=(0, 14))
        ttk.Label(pulse, text="AI SWARM ORACLE", style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            pulse,
            text="The signal forms locally, writes to Firebase, and the pin answers in light.",
            style="PanelText.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(7, 0))
        ttk.Button(
            pulse,
            text="SWARM SIGNAL",
            style="Signal.TButton",
            command=self.send_swarm_signal,
        ).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(14, 10))
        ttk.Button(pulse, text="Soft", command=lambda: self.send_pulse(7)).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(pulse, text="Active", command=lambda: self.send_pulse(13)).grid(row=3, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(pulse, text="Bright", command=lambda: self.send_pulse(20)).grid(row=3, column=2, sticky="ew", padx=(0, 8))
        ttk.Button(pulse, text="Readback", command=self.read_pin).grid(row=3, column=3, sticky="ew")
        pulse.columnconfigure(0, weight=1)
        pulse.columnconfigure(1, weight=1)
        pulse.columnconfigure(2, weight=1)
        pulse.columnconfigure(3, weight=1)

        self.advanced_frame = ttk.Frame(root, style="Panel.TFrame", padding=16)
        ttk.Label(self.advanced_frame, text="Advanced WLED", style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(self.advanced_frame, text="Optional direct local WLED host or IP", style="PanelText.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 4))
        ttk.Entry(self.advanced_frame, textvariable=self.wled_var).grid(row=2, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(self.advanced_frame, text="Save WLED", command=self.save_wled).grid(row=2, column=1, sticky="ew", padx=(0, 10))
        ttk.Button(self.advanced_frame, text="Clear WLED", command=self.clear_wled).grid(row=2, column=2, sticky="ew")
        self.advanced_frame.columnconfigure(0, weight=1)
        if self.advanced_visible:
            self.advanced_frame.pack(fill="x", pady=(0, 14))

        self.pattern_panel = ttk.Frame(root, style="Panel.TFrame", padding=16)
        pattern = self.pattern_panel
        pattern.pack(fill="both", expand=True, pady=(0, 14))
        ttk.Label(pattern, text="THE PIN ANSWERS", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(pattern, textvariable=self.pattern_var, style="PanelText.TLabel", wraplength=730).pack(anchor="w", pady=(8, 12))
        self.canvas = tk.Canvas(pattern, height=128, bg="#0a1210", bd=0, highlightthickness=0)
        self.canvas.pack(fill="x", pady=(0, 12))
        self._draw_empty_preview()

        self.log = tk.Text(
            pattern,
            height=8,
            bg="#08100d",
            fg="#d8e4de",
            insertbackground="#d8e4de",
            relief="flat",
            wrap="word",
            font=("Consolas", 9),
        )
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

    def _draw_empty_preview(self) -> None:
        self.canvas.delete("all")
        self.canvas.create_text(
            18,
            64,
            text="Press SWARM SIGNAL to write the next pattern into Firebase.",
            fill="#afc7bd",
            anchor="w",
            font=("Segoe UI", 10),
        )

    def _draw_pattern(self, decision: LocalLightDecision) -> None:
        self.canvas.delete("all")
        width = max(720, self.canvas.winfo_width())
        colors = sanitized_colors(decision.pattern.colors)
        block_width = max(120, int((width - 42) / 3))
        for index, color in enumerate(colors):
            x0 = 14 + index * (block_width + 8)
            x1 = x0 + block_width
            self.canvas.create_rectangle(x0, 16, x1, 112, fill=rgb_to_hex(color), outline="")
            self.canvas.create_text(
                x0 + 14,
                96,
                text=f"{color[0]}, {color[1]}, {color[2]}",
                fill="#08100d",
                anchor="w",
                font=("Segoe UI", 9, "bold"),
            )
        self.canvas.create_text(
            16,
            18,
            text=f"{decision.label}  fx={decision.pattern.effect}  speed={decision.pattern.speed}  intensity={decision.pattern.intensity}",
            fill="#08100d",
            anchor="nw",
            font=("Segoe UI", 10, "bold"),
        )

    def _refresh_connection_text(self) -> None:
        pin = self.settings.device_id or "-"
        wled = self.settings.wled_host or "off"
        self.connection_var.set(f"Pin: {pin}   |   Advanced WLED: {wled}   |   Settings: {self.settings.path}")

    def toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_frame.pack(fill="x", pady=(0, 14), before=self.pattern_panel)
        else:
            self.advanced_frame.pack_forget()

    def save_pin(self) -> None:
        device_id = self.pin_var.get().strip()
        if not device_id:
            messagebox.showwarning(APP_NAME, "Please enter a pin ID.")
            return
        self.settings.device_id = device_id
        self._refresh_connection_text()
        self._run_background(
            "Registering pin...",
            lambda: self.firebase.add_pin(device_id),
            lambda _result: self._log(f"Pin saved and checked in Firebase: {device_id}"),
        )

    def save_wled(self) -> None:
        host = WledClient.normalize_host(self.wled_var.get())
        if not host:
            messagebox.showwarning(APP_NAME, "Please enter a WLED host or IP.")
            return
        self.settings.wled_host = host
        self.wled_var.set(host)
        self._refresh_connection_text()
        self._log(f"WLED node saved: {host}")
        self.status_var.set("WLED node saved.")

    def clear_wled(self) -> None:
        self.settings.wled_host = ""
        self.wled_var.set("")
        self._refresh_connection_text()
        self._log("Advanced WLED node cleared.")
        self.status_var.set("WLED cleared.")

    def read_pin(self) -> None:
        device_id = self.pin_var.get().strip() or self.settings.device_id
        if not device_id:
            messagebox.showwarning(APP_NAME, "Save a pin ID before reading Firebase.")
            return
        self.settings.device_id = device_id
        self._refresh_connection_text()

        def done(snapshot: dict[str, Any] | None) -> None:
            if not snapshot:
                self.pattern_var.set("Firebase readback: no node exists for this pin ID.")
                self._log(f"Firebase readback: no node for {device_id}")
                return
            summary = describe_pin_snapshot(snapshot)
            self.pattern_var.set(summary)
            self._log("Firebase readback: " + summary)
            desired = snapshot.get("desired_settings")
            pattern = led_pattern_from_settings(desired if isinstance(desired, dict) else {})
            if pattern:
                self.current_pattern = pattern
                self._draw_pattern(
                    LocalLightDecision(
                        pattern=pattern,
                        message=summary,
                        label="FIREBASE READBACK",
                    )
                )

        self._run_background(
            "Reading Firebase pin...",
            lambda: self.firebase.read_pin_snapshot(device_id),
            done,
        )

    def reset_wifi(self) -> None:
        device_id = self.pin_var.get().strip() or self.settings.device_id
        if not device_id:
            messagebox.showwarning(APP_NAME, "Save a pin ID before sending reset WiFi.")
            return
        if not messagebox.askyesno(APP_NAME, "Send WiFi reset to this pin?"):
            return
        self._run_background(
            "Sending WiFi reset...",
            lambda: self.firebase.reset_wifi(device_id),
            lambda _result: self._log(f"WiFi reset command sent to pin: {device_id}"),
        )

    def send_swarm_signal(self) -> None:
        force = 13 + (self.pulse_count % 4)
        self.send_pulse(force)

    def send_pulse(self, shake_force: float) -> None:
        device_id = self.pin_var.get().strip() or self.settings.device_id
        wled_host = self.wled_var.get().strip() or self.settings.wled_host
        if not device_id and not wled_host:
            messagebox.showwarning(APP_NAME, "Save a pin ID or WLED host first.")
            return
        if device_id:
            self.settings.device_id = device_id
        if wled_host:
            self.settings.wled_host = WledClient.normalize_host(wled_host)
            self.wled_var.set(self.settings.wled_host)
        self._refresh_connection_text()

        def work() -> tuple[LocalLightDecision, list[str], list[str]]:
            self.pulse_count += 1
            decision = self.engine.generate(
                device_id=device_id or wled_host,
                shake_force=shake_force,
                pulse_count=self.pulse_count,
                previous_pattern=self.current_pattern,
            )
            delivered: list[str] = []
            errors: list[str] = []
            if device_id:
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
            if not delivered:
                raise RuntimeError("The light was chosen, but no registered node accepted it. " + "; ".join(errors))
            return decision, delivered, errors

        def done(result: tuple[LocalLightDecision, list[str], list[str]]) -> None:
            decision, delivered, errors = result
            self.current_pattern = decision.pattern
            self.pattern_var.set(decision.message)
            self._draw_pattern(decision)
            self._log(f"{decision.label} sent to {' + '.join(delivered)}")
            if errors:
                self._log("Partial delivery issue: " + "; ".join(errors))

        self._run_background("Sending swarm light...", work, done)

    def _run_background(
        self,
        label: str,
        work: Callable[[], Any],
        done: Callable[[Any], None],
    ) -> None:
        self.status_var.set(label)

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
        self.status_var.set("Ready.")

    def _show_error(self, exc: Exception) -> None:
        self.status_var.set("Operation failed.")
        self._log(f"Error: {short_error(exc)}")
        messagebox.showerror(APP_NAME, short_error(exc))

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")


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
