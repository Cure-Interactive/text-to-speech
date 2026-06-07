# Text To Speech

Highly experimental desktop text-to-speech app using local system voices.

## Beta Status

This project is in a high-beta state and should not be expected to work out of the box. Its current implementation depends on local operating-system speech support through `pyttsx3`, and that stack can fail or behave inconsistently depending on installed voices, audio devices, platform speech drivers, and environment setup.

Use this repo as a prototype or development target, not as a finished utility.

## Requirements

- Python 3.10+
- Dependencies from `requirements.txt`
- A working local speech engine

Linux systems may also need speech and Tk packages such as `espeak-ng` and `python3-tk`.

## Install

```bash
python setup.py --venv
```

Or manually:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Linux or macOS, activate the virtual environment with `source .venv/bin/activate`.

## Run

```bash
python text-to-speech.py
```

## Usage

Paste text, choose a voice and rate, then use Speak, Pause, and Stop controls.

If it does not speak, that is currently expected on some systems. See `wiki.md` for limitations and troubleshooting notes.
