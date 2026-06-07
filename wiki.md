# Text To Speech Wiki

Text To Speech is a high-beta prototype for reading pasted text aloud using local system voices through `pyttsx3`.

## Current Status

This app does not reliably work out of the box. The current implementation is limited by local speech-engine support, installed voices, audio device configuration, and `pyttsx3` platform behavior. Some systems may show no usable voices, fail to produce audio, or behave inconsistently between runs.

Treat this as a development prototype. Expect setup and implementation work before it is dependable.

## Quick Start

```bash
python setup.py --venv
python text-to-speech.py
```

Manual install:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python text-to-speech.py
```

On Linux or macOS, use `source .venv/bin/activate`.

Linux systems may also need:

```bash
sudo apt-get install espeak-ng python3-tk
```

## Runtime Files

- `config.json`: local app settings beside the script
- `_log/`: runtime logs

These files are ignored by Git.

## Troubleshooting

If no voices appear, check that the operating system has usable speech voices installed. If there is no audio, check the selected output device and try another voice.

Known limitations:

- Depends on local OS voices and speech drivers.
- Voice discovery may fail even when dependencies install successfully.
- Pause/resume behavior is implementation-limited and may not be reliable.
- The app has not been hardened for all Windows, Linux, and macOS speech-engine variants.
