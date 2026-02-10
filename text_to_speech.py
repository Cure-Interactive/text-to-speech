#!/usr/bin/env python3
# =============================================================================
# [Python Script] [CustomTkinter GUI] [Text To Speech]
# =============================================================================
"""
Text-to-speech desktop app.

Features:
- Paste/type text in a multi-line input box.
- Select available system voice.
- Configure speech rate.
- Speak / Stop controls.
- Persist UI settings to local config.json beside the script.

Dependency:
- customtkinter
- pyttsx3
"""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import pyttsx3


APP_TITLE = "Text To Speech - Cure Interactive"
APP_USER_MODEL_ID = "CureInteractive.TextToSpeech"

PATH_DIR_SCRIPT = os.path.abspath(os.path.dirname(__file__))
PATH_CONFIG_JSON = os.path.join(PATH_DIR_SCRIPT, "config.json")

DEFAULT_CONFIG = {
  "window": {
    "width": 960,
    "height": 700,
  },
  "appearance_mode": "System",
  "color_theme": "blue",
  "speech_rate": 190,
  "voice_id": "",
  "text": "",
}


# =============================================================================
# Helpers
# =============================================================================

def _read_json(path: str) -> dict | None:
  try:
    if not os.path.isfile(path):
      return None
    with open(path, "r", encoding="utf-8") as f:
      return json.load(f)
  except Exception:
    return None


def _write_json_atomic(path: str, data: dict) -> None:
  tmp = path + ".tmp"
  with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
  os.replace(tmp, path)


def load_or_create_config(path: str) -> dict:
  cfg = _read_json(path)
  if isinstance(cfg, dict):
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update(cfg)
    if isinstance(cfg.get("window"), dict):
      merged["window"].update(cfg["window"])
    return merged

  _write_json_atomic(path, DEFAULT_CONFIG)
  return json.loads(json.dumps(DEFAULT_CONFIG))


def clamp_int(value, lo: int, hi: int, fallback: int) -> int:
  try:
    n = int(value)
    return max(lo, min(hi, n))
  except Exception:
    return fallback


def set_windows_app_user_model_id(app_id: str) -> None:
  try:
    if os.name != "nt":
      return
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
  except Exception:
    return


def set_window_icon(root, ico_path: str, png_path: str) -> None:
  ico_abs = os.path.abspath(ico_path) if ico_path else ""
  png_abs = os.path.abspath(png_path) if png_path else ""

  try:
    if ico_abs and os.path.isfile(ico_abs):
      root.iconbitmap(ico_abs)
  except Exception:
    pass

  try:
    if png_abs and os.path.isfile(png_abs):
      img = tk.PhotoImage(file=png_abs)
      root.iconphoto(True, img)
      root._iconphoto_ref = img
  except Exception:
    pass


# =============================================================================
# TTS Engine (worker-thread usage)
# =============================================================================

class TtsEngine:
  def __init__(self):
    self._engine = pyttsx3.init()
    self._lock = threading.Lock()

  def list_voices(self) -> list[tuple[str, str]]:
    voices = self._engine.getProperty("voices") or []
    out: list[tuple[str, str]] = []
    for v in voices:
      voice_id = getattr(v, "id", "") or ""
      name = getattr(v, "name", "") or voice_id or "Voice"
      out.append((voice_id, name))
    return out

  def speak(self, *, text: str, voice_id: str | None, rate: int) -> None:
    # Only lock around queue/property mutation. Keep runAndWait unlocked so
    # Stop can interrupt playback without freezing the GUI thread.
    with self._lock:
      try:
        self._engine.stop()
      except Exception:
        pass

      if voice_id:
        self._engine.setProperty("voice", voice_id)
      self._engine.setProperty("rate", int(rate))
      self._engine.say(text)

    self._engine.runAndWait()

  def stop(self) -> None:
    try:
      self._engine.stop()
    except Exception:
      pass


# =============================================================================
# App
# =============================================================================

class TextToSpeechApp(ctk.CTk):
  def __init__(self):
    super().__init__()

    self.config_data = load_or_create_config(PATH_CONFIG_JSON)

    ctk.set_appearance_mode(self.config_data.get("appearance_mode", "System"))
    ctk.set_default_color_theme(self.config_data.get("color_theme", "blue"))

    w = self.config_data.get("window", {}).get("width", 960)
    h = self.config_data.get("window", {}).get("height", 700)

    self.title(APP_TITLE)
    self.geometry(f"{w}x{h}")
    self.minsize(720, 520)

    set_window_icon(
      self,
      os.path.join(PATH_DIR_SCRIPT, "icon.ico"),
      os.path.join(PATH_DIR_SCRIPT, "icon.png"),
    )

    self._tts = TtsEngine()
    self._ui_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    self._speak_thread: threading.Thread | None = None

    self.var_rate = tk.IntVar(value=clamp_int(self.config_data.get("speech_rate", 190), 80, 300, 190))

    self.voice_items = self._tts.list_voices()
    self.voice_name_by_id = {voice_id: label for voice_id, label in self.voice_items}
    self.voice_id_by_name = {label: voice_id for voice_id, label in self.voice_items}

    default_voice_id = str(self.config_data.get("voice_id", "") or "")
    default_voice_name = self.voice_name_by_id.get(default_voice_id, "")
    if not default_voice_name and self.voice_items:
      default_voice_name = self.voice_items[0][1]

    self.var_voice_name = tk.StringVar(value=default_voice_name)

    self._build_ui()

    initial_text = str(self.config_data.get("text", "") or "")
    if initial_text:
      self.text_input.insert("1.0", initial_text)

    self.protocol("WM_DELETE_WINDOW", self._on_close)
    self.after(120, self._poll_ui_queue)

  def _build_ui(self) -> None:
    pad = {"padx": 14, "pady": 8}

    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(2, weight=1)

    header = ctk.CTkLabel(
      self,
      text="Paste text and press Speak",
      font=ctk.CTkFont(size=20, weight="bold"),
    )
    header.grid(row=0, column=0, sticky="w", **pad)

    controls = ctk.CTkFrame(self)
    controls.grid(row=1, column=0, sticky="ew", **pad)
    controls.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(controls, text="Voice").grid(row=0, column=0, padx=10, pady=10, sticky="w")

    voice_values = [label for _voice_id, label in self.voice_items] if self.voice_items else ["Default"]
    self.voice_menu = ctk.CTkOptionMenu(
      controls,
      values=voice_values,
      variable=self.var_voice_name,
      dynamic_resizing=False,
      width=340,
    )
    self.voice_menu.grid(row=0, column=1, padx=10, pady=10, sticky="w")

    ctk.CTkLabel(controls, text="Rate").grid(row=0, column=2, padx=10, pady=10, sticky="e")

    self.rate_slider = ctk.CTkSlider(
      controls,
      from_=80,
      to=300,
      number_of_steps=220,
      command=self._on_rate_changed,
      width=220,
    )
    self.rate_slider.grid(row=0, column=3, padx=10, pady=10, sticky="ew")
    self.rate_slider.set(self.var_rate.get())

    self.rate_value = ctk.CTkLabel(controls, text=str(self.var_rate.get()), width=46)
    self.rate_value.grid(row=0, column=4, padx=(0, 10), pady=10, sticky="w")

    text_wrap = ctk.CTkFrame(self)
    text_wrap.grid(row=2, column=0, sticky="nsew", **pad)
    text_wrap.grid_columnconfigure(0, weight=1)
    text_wrap.grid_rowconfigure(0, weight=1)

    self.text_input = ctk.CTkTextbox(text_wrap, wrap="word")
    self.text_input.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    actions = ctk.CTkFrame(self)
    actions.grid(row=3, column=0, sticky="ew", **pad)

    self.btn_speak = ctk.CTkButton(actions, text="Speak", command=self._on_speak_clicked, width=120)
    self.btn_speak.pack(side="left", padx=10, pady=10)

    self.btn_stop = ctk.CTkButton(actions, text="Stop", command=self._on_stop_clicked, width=120)
    self.btn_stop.pack(side="left", padx=6, pady=10)

    self.status_label = ctk.CTkLabel(actions, text="Idle")
    self.status_label.pack(side="left", padx=16, pady=10)

  def _on_rate_changed(self, value: float) -> None:
    n = int(value)
    self.var_rate.set(n)
    self.rate_value.configure(text=str(n))

  def _selected_voice_id(self) -> str:
    selected_label = self.var_voice_name.get().strip()
    return self.voice_id_by_name.get(selected_label, "")

  def _set_busy(self, busy: bool, status: str) -> None:
    self.btn_speak.configure(state=("disabled" if busy else "normal"))
    self.status_label.configure(text=status)

  def _on_speak_clicked(self) -> None:
    text = self.text_input.get("1.0", "end-1c").strip()
    if not text:
      messagebox.showwarning(APP_TITLE, "Paste or type text first.")
      return

    if self._speak_thread and self._speak_thread.is_alive():
      messagebox.showinfo(APP_TITLE, "Speech is already running. Press Stop first if needed.")
      return

    voice_id = self._selected_voice_id()
    rate = clamp_int(self.var_rate.get(), 80, 300, 190)

    self._set_busy(True, "Speaking...")

    def _worker() -> None:
      try:
        self._tts.speak(text=text, voice_id=voice_id, rate=rate)
        self._ui_queue.put(("done", "Idle"))
      except Exception as e:
        self._ui_queue.put(("error", str(e)))

    self._speak_thread = threading.Thread(target=_worker, daemon=True)
    self._speak_thread.start()

  def _on_stop_clicked(self) -> None:
    self._tts.stop()
    self._set_busy(False, "Stopped")

  def _poll_ui_queue(self) -> None:
    try:
      while True:
        kind, payload = self._ui_queue.get_nowait()
        if kind == "done":
          self._set_busy(False, payload)
        elif kind == "error":
          self._set_busy(False, "Error")
          messagebox.showerror(APP_TITLE, payload)
    except queue.Empty:
      pass

    self.after(120, self._poll_ui_queue)

  def _on_close(self) -> None:
    self._tts.stop()
    self._save_config()
    self.destroy()

  def _save_config(self) -> None:
    try:
      geom = self.geometry().split("+")[0]
      w_str, h_str = geom.split("x", 1)
      w = clamp_int(w_str, 400, 6000, 960)
      h = clamp_int(h_str, 300, 4000, 700)
    except Exception:
      w = 960
      h = 700

    cfg = json.loads(json.dumps(self.config_data))
    cfg["window"] = {"width": w, "height": h}
    cfg["speech_rate"] = clamp_int(self.var_rate.get(), 80, 300, 190)
    cfg["voice_id"] = self._selected_voice_id()
    cfg["text"] = self.text_input.get("1.0", "end-1c")

    _write_json_atomic(PATH_CONFIG_JSON, cfg)


def main() -> int:
  set_windows_app_user_model_id(APP_USER_MODEL_ID)

  app = TextToSpeechApp()
  app.mainloop()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
