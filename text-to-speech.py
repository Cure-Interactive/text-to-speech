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
- Speak / Pause / Stop controls.
- Persist UI settings to local config.json beside the script.

Dependency:
- customtkinter
- pyttsx3
"""

from __future__ import annotations

import datetime
import json
import os
import queue
import threading
import re
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import pyttsx3


APP_TITLE = "Text To Speech - Cure Interactive"
APP_USER_MODEL_ID = "CureInteractive.TextToSpeech"

PATH_DIR_SCRIPT = os.path.abspath(os.path.dirname(__file__))
PATH_CONFIG_JSON = os.path.join(PATH_DIR_SCRIPT, "config.json")
PATH_LOG_DIR = os.path.join(PATH_DIR_SCRIPT, "_log")

DEFAULT_CONFIG = {
  "window": {
    "width": 960,
    "height": 700,
  },
  "appearance_mode": "System",
  "color_theme": "blue",
  "speech_rate": 130,
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


def split_text_for_tts(text: str, max_chunk_chars: int = 120) -> list[str]:
  """
  Break text into sentence-like chunks so live rate/voice changes can apply
  between chunks.
  """
  raw_parts = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
  sentence_parts = [p.strip() for p in raw_parts if p and p.strip()]
  if not sentence_parts:
    return []

  out: list[str] = []
  for sentence in sentence_parts:
    if len(sentence) <= max_chunk_chars:
      out.append(sentence)
      continue

    # Hard wrap very long sentences by words so stop/live updates get frequent
    # checkpoints.
    words = sentence.split()
    current = ""
    for word in words:
      if not current:
        current = word
        continue
      candidate = f"{current} {word}"
      if len(candidate) <= max_chunk_chars:
        current = candidate
      else:
        out.append(current)
        current = word
    if current:
      out.append(current)

  return out


# =============================================================================
# TTS Engine
# =============================================================================

class TtsEngine:
  @staticmethod
  def create_engine() -> pyttsx3.Engine:
    return pyttsx3.init()

  @staticmethod
  def list_voices(engine: pyttsx3.Engine) -> list[tuple[str, str]]:
    voices = engine.getProperty("voices") or []
    out: list[tuple[str, str]] = []
    for v in voices:
      voice_id = getattr(v, "id", "") or ""
      name = getattr(v, "name", "") or voice_id or "Voice"
      out.append((voice_id, name))
    return out


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
    self._state_lock = threading.Lock()
    self._engine_lock = threading.Lock()
    self._current_engine: pyttsx3.Engine | None = None
    self._active_playback_id = 0
    self._active_stop_event: threading.Event | None = None
    self._active_action: str | None = None
    self._active_action_playback_id = 0
    self._log_file_lock = threading.Lock()
    self._log_path = self._make_log_path()
    self._live_rate = clamp_int(self.config_data.get("speech_rate", 130), 80, 300, 130)
    self._live_voice_id = ""
    self._paused_source_text = ""
    self._paused_chunks: list[str] = []
    self._paused_index = 0

    self.var_rate = tk.IntVar(value=self._live_rate)

    voice_probe_engine = self._tts.create_engine()
    self.voice_items = self._tts.list_voices(voice_probe_engine)
    try:
      voice_probe_engine.stop()
    except Exception:
      pass
    self.voice_name_by_id = {voice_id: label for voice_id, label in self.voice_items}
    self.voice_id_by_name = {label: voice_id for voice_id, label in self.voice_items}

    default_voice_id = str(self.config_data.get("voice_id", "") or "")
    default_voice_name = self.voice_name_by_id.get(default_voice_id, "")
    if not default_voice_name and self.voice_items:
      default_voice_name = self.voice_items[0][1]

    self.var_voice_name = tk.StringVar(value=default_voice_name)
    self._live_voice_id = self.voice_id_by_name.get(default_voice_name, "")

    self._build_ui()

    initial_text = str(self.config_data.get("text", "") or "")
    if initial_text:
      self.text_input.insert("1.0", initial_text)

    self.protocol("WM_DELETE_WINDOW", self._on_close)
    self.after(120, self._poll_ui_queue)
    self._log("App started.")

  def _build_ui(self) -> None:
    pad = {"padx": 14, "pady": 8}

    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(3, weight=1)

    header = ctk.CTkLabel(
      self,
      text="Text To Speech",
      font=ctk.CTkFont(size=20, weight="bold"),
    )
    header.grid(row=0, column=0, sticky="w", **pad)

    beta_note = ctk.CTkLabel(
      self,
      text="Highly experimental: may not work out of the box because it depends on local OS voices, audio devices, and pyttsx3 platform support.",
      anchor="w",
      justify="left",
      wraplength=900,
    )
    beta_note.grid(row=1, column=0, sticky="ew", **pad)

    controls = ctk.CTkFrame(self)
    controls.grid(row=2, column=0, sticky="ew", **pad)
    controls.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(controls, text="Voice").grid(row=0, column=0, padx=10, pady=10, sticky="w")

    voice_values = [label for _voice_id, label in self.voice_items] if self.voice_items else ["Default"]
    self.voice_menu = ctk.CTkOptionMenu(
      controls,
      values=voice_values,
      variable=self.var_voice_name,
      command=self._on_voice_changed,
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
    text_wrap.grid(row=3, column=0, sticky="nsew", **pad)
    text_wrap.grid_columnconfigure(0, weight=1)
    text_wrap.grid_rowconfigure(0, weight=1)

    self.text_input = ctk.CTkTextbox(text_wrap, wrap="word")
    self.text_input.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    actions = ctk.CTkFrame(self)
    actions.grid(row=4, column=0, sticky="ew", **pad)

    self.btn_speak = ctk.CTkButton(actions, text="Speak", command=self._on_speak_clicked, width=120)
    self.btn_speak.pack(side="left", padx=10, pady=10)

    self.btn_pause = ctk.CTkButton(actions, text="Pause", command=self._on_pause_clicked, width=120)
    self.btn_pause.pack(side="left", padx=6, pady=10)
    self.btn_pause.configure(state="disabled")

    self.btn_stop = ctk.CTkButton(actions, text="Stop", command=self._on_stop_clicked, width=120)
    self.btn_stop.pack(side="left", padx=6, pady=10)

    self.status_label = ctk.CTkLabel(actions, text="Idle")
    self.status_label.pack(side="left", padx=16, pady=10)

    log_wrap = ctk.CTkFrame(self)
    log_wrap.grid(row=5, column=0, sticky="ew", **pad)
    log_wrap.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(log_wrap, text="Log").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
    self.log_text = ctk.CTkTextbox(log_wrap, height=130, wrap="word")
    self.log_text.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
    self.log_text.configure(state="disabled")

  def _on_rate_changed(self, value: float) -> None:
    n = int(value)
    self.var_rate.set(n)
    self._live_rate = n
    self.rate_value.configure(text=str(n))

  def _on_voice_changed(self, selected_label: str) -> None:
    self._live_voice_id = self.voice_id_by_name.get((selected_label or "").strip(), "")
    self._log(f"Voice changed to: {selected_label}")

  def _selected_voice_id(self) -> str:
    selected_label = self.var_voice_name.get().strip()
    return self.voice_id_by_name.get(selected_label, "")

  def _set_busy(self, busy: bool, status: str) -> None:
    self.btn_speak.configure(state=("disabled" if busy else "normal"))
    self.btn_pause.configure(state=("normal" if busy else "disabled"))
    self.status_label.configure(text=status)

  def _on_speak_clicked(self) -> None:
    text = self.text_input.get("1.0", "end-1c").strip()
    if not text:
      messagebox.showwarning(APP_TITLE, "Paste or type text first.")
      return

    resume_chunks: list[str] | None = None
    resume_index = 0
    if self._paused_source_text == text and self._paused_chunks and 0 <= self._paused_index < len(self._paused_chunks):
      resume_chunks = list(self._paused_chunks)
      resume_index = int(self._paused_index)
      self._log(f"Resuming paused playback from chunk {resume_index + 1}/{len(resume_chunks)}.")
    else:
      self._clear_pause_state()

    playback_id, stop_event = self._start_new_playback()
    self._set_busy(True, "Speaking...")
    self._log(f"Speak requested (playback #{playback_id}).")

    def _worker() -> None:
      stopped = False
      paused = False
      next_index = resume_index
      engine: pyttsx3.Engine | None = None
      try:
        engine = self._tts.create_engine()
        self._set_current_engine(playback_id, engine)

        chunks = resume_chunks if resume_chunks is not None else split_text_for_tts(text)
        if not chunks:
          self._ui_queue.put(("warn", "No speakable text found."))
          return

        for idx in range(resume_index, len(chunks)):
          chunk = chunks[idx]
          if stop_event.is_set():
            stopped = True
            break

          voice_id, rate = self._current_live_settings()
          if voice_id:
            try:
              engine.setProperty("voice", voice_id)
            except Exception as e:
              self._ui_queue.put(("log", f"Voice apply failed: {e}"))
          try:
            engine.setProperty("rate", int(rate))
          except Exception as e:
            self._ui_queue.put(("log", f"Rate apply failed: {e}"))

          self._ui_queue.put(("log", f"Speaking chunk {idx + 1}/{len(chunks)} (rate={rate})"))
          next_index = idx
          engine.say(chunk)
          engine.runAndWait()

          if stop_event.is_set():
            stopped = True
            break
          next_index = idx + 1
      except Exception as e:
        self._ui_queue.put(("error", str(e)))
      finally:
        try:
          if engine is not None:
            engine.stop()
        except Exception:
          pass
        self._clear_current_engine(playback_id, engine)

        action = self._consume_action_for_playback(playback_id)
        if stopped and action == "pause":
          paused = True
          self._store_pause_state(text, chunks if 'chunks' in locals() else [], next_index)
        elif stopped:
          self._clear_pause_state()
        else:
          self._clear_pause_state()

        if self._is_active_playback(playback_id):
          self._ui_queue.put(("done", ("Paused" if paused else ("Stopped" if stopped else "Idle"))))

        self._ui_queue.put(("log", f"Playback #{playback_id} {'paused' if paused else ('stopped' if stopped else 'finished')}"))

    self._speak_thread = threading.Thread(target=_worker, daemon=True, name=f"tts-playback-{playback_id}")
    self._speak_thread.start()

  def _on_pause_clicked(self) -> None:
    self._request_stop("Pause button pressed.", action="pause")
    self._set_busy(False, "Paused")

  def _on_stop_clicked(self) -> None:
    self._request_stop("Stop button pressed.", action="stop")
    self._clear_pause_state()
    self._set_busy(False, "Stopped")

  def _poll_ui_queue(self) -> None:
    try:
      while True:
        kind, payload = self._ui_queue.get_nowait()
        if kind == "done":
          self._set_busy(False, str(payload))
        elif kind == "error":
          self._set_busy(False, "Error")
          self._log(f"Error: {payload}")
          messagebox.showerror(APP_TITLE, payload)
        elif kind == "warn":
          self._set_busy(False, "Idle")
          self._log(f"Warn: {payload}")
        elif kind == "log":
          self._log(str(payload))
    except queue.Empty:
      pass

    self.after(120, self._poll_ui_queue)

  def _on_close(self) -> None:
    self._request_stop("App closing.", action="stop")
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
    cfg["speech_rate"] = clamp_int(self.var_rate.get(), 80, 300, 130)
    cfg["voice_id"] = self._selected_voice_id()
    cfg["text"] = self.text_input.get("1.0", "end-1c")

    _write_json_atomic(PATH_CONFIG_JSON, cfg)

  def _current_live_settings(self) -> tuple[str, int]:
    return (self._live_voice_id, clamp_int(self._live_rate, 80, 300, 130))

  def _start_new_playback(self) -> tuple[int, threading.Event]:
    with self._state_lock:
      old_stop_event = self._active_stop_event
      self._active_playback_id += 1
      playback_id = self._active_playback_id
      new_stop_event = threading.Event()
      self._active_stop_event = new_stop_event
      self._active_action = None
      self._active_action_playback_id = playback_id

    if old_stop_event is not None:
      old_stop_event.set()
    old_engine = self._get_current_engine_snapshot()
    if old_engine is not None:
      self._stop_engine_async(old_engine)
    return playback_id, new_stop_event

  def _request_stop(self, reason: str, action: str = "stop") -> None:
    with self._state_lock:
      stop_event = self._active_stop_event
      self._active_action = action
      self._active_action_playback_id = self._active_playback_id
    if stop_event is not None:
      stop_event.set()
    engine = self._get_current_engine_snapshot()
    if engine is not None:
      self._stop_engine_async(engine)
    self._log(reason)

  def _set_current_engine(self, playback_id: int, engine: pyttsx3.Engine) -> None:
    if not self._is_active_playback(playback_id):
      return
    with self._engine_lock:
      self._current_engine = engine

  def _clear_current_engine(self, playback_id: int, engine: pyttsx3.Engine | None) -> None:
    with self._engine_lock:
      if self._current_engine is engine:
        self._current_engine = None

  def _stop_current_engine(self) -> None:
    with self._engine_lock:
      engine = self._current_engine
    if engine is None:
      return
    try:
      engine.stop()
    except Exception as e:
      self._ui_queue.put(("log", f"Stop warning: {e}"))

  def _get_current_engine_snapshot(self) -> pyttsx3.Engine | None:
    with self._engine_lock:
      return self._current_engine

  def _stop_engine_async(self, engine: pyttsx3.Engine) -> None:
    def _worker() -> None:
      try:
        engine.stop()
      except Exception as e:
        self._ui_queue.put(("log", f"Stop warning: {e}"))

    t = threading.Thread(target=_worker, daemon=True, name="tts-stop")
    t.start()

  def _is_active_playback(self, playback_id: int) -> bool:
    with self._state_lock:
      return playback_id == self._active_playback_id

  def _consume_action_for_playback(self, playback_id: int) -> str | None:
    with self._state_lock:
      if self._active_action_playback_id != playback_id:
        return None
      action = self._active_action
      self._active_action = None
      return action

  def _store_pause_state(self, source_text: str, chunks: list[str], next_index: int) -> None:
    self._paused_source_text = source_text
    self._paused_chunks = list(chunks)
    self._paused_index = max(0, min(next_index, len(self._paused_chunks)))

  def _clear_pause_state(self) -> None:
    self._paused_source_text = ""
    self._paused_chunks = []
    self._paused_index = 0

  def _make_log_path(self) -> str:
    os.makedirs(PATH_LOG_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    return os.path.join(PATH_LOG_DIR, f"text_to_speech_{stamp}.log")

  def _append_log_text(self, line: str) -> None:
    try:
      self.log_text.configure(state="normal")
      self.log_text.insert("end", line + "\n")
      self.log_text.see("end")
      self.log_text.configure(state="disabled")
    except Exception:
      pass

  def _write_log_file(self, line: str) -> None:
    with self._log_file_lock:
      with open(self._log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

  def _log(self, message: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    self._append_log_text(line)
    self._write_log_file(line)


def main() -> int:
  set_windows_app_user_model_id(APP_USER_MODEL_ID)

  app = TextToSpeechApp()
  app.mainloop()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
