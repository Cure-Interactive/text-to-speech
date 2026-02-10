# Text To Speech (GUI)

This tool reads pasted text out loud using your local system voices.

## Quick Start

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python text_to_speech.py
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python text_to_speech.py
```

Linux packages required for speech/Tk:

```bash
# Debian/Ubuntu example
sudo apt-get update
sudo apt-get install -y espeak-ng python3-tk
```

## Usage

1. Paste or type text into the main textbox.
2. Choose a voice from the dropdown.
3. Adjust the speech rate slider.
4. Click **Speak**.
5. Click **Pause** to pause playback.
6. Click **Speak** again to resume from the paused chunk.
7. Click **Stop** to stop playback and clear paused position.
8. You can change voice/rate while speaking; changes apply on upcoming sentence/chunk boundaries.

## Notes

- Settings are saved in `config.json` beside the script.
- Default speech rate is `130`.
- Runtime logs are shown in the app and written to `_log/text_to_speech_YYYYMMDD.log`.
- Voices come from your OS speech engine.
- If no custom voice appears, your default system voice is used.

## Troubleshooting

### `No module named customtkinter` or `pyttsx3`

Install dependencies:

```bash
pip install -r requirements.txt
```

### No audio playback

- Check system volume/output device.
- Confirm text was entered.
- Try a different voice in the dropdown.
