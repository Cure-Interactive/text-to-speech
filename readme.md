# Text To Speech

Desktop text-to-speech app using local system voices.

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
python text_to_speech.py
```

## Usage

Paste text, choose a voice and rate, then use Speak, Pause, and Stop controls.

See `wiki.md` for troubleshooting notes.
