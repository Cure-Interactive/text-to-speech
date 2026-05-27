# Text To Speech Wiki

Text To Speech reads pasted text aloud using local system voices through `pyttsx3`.

## Quick Start

```bash
python setup.py --venv
python text_to_speech.py
```

Manual install:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python text_to_speech.py
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
