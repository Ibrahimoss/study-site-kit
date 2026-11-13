# The voice PC (optional)

The narration (audio lessons and shorts) runs Kokoro, a voice model. By default it runs on this computer
(`"engine": "kokoro-local"` in `course.json`): it uses an NVIDIA graphics card if there is one, otherwise the
processor, which is slower but fine.

If another Windows PC in your home has a better graphics card, it can do the narration instead. This folder
sets that up. You only need it for `"engine": "kokoro-ssh"`.

## Set up the other PC once

1. On that PC, turn on **OpenSSH Server** (Settings, System, Optional features, Add a feature).
2. Copy `setup.ps1` to it and run, in PowerShell:

   ```powershell
   powershell -ExecutionPolicy Bypass -File setup.ps1
   ```

   Everything goes in one folder, by default `study-kit-tts` in your user folder (Python, Kokoro, Whisper and
   the voice model, a few GB). `-Dir E:\voices` picks another folder (no spaces in the path).
   `-NoWhisper` skips Whisper, the optional listener that double-checks every clip.
3. Let this computer log in with a key: make one here with `ssh-keygen -t ed25519`, and add the `.pub` file's
   line to the other PC (for an admin account: `C:\ProgramData\ssh\administrators_authorized_keys`, otherwise
   `.ssh\authorized_keys` in the user's folder).
4. If the PC is not on the same network, a private network app such as Tailscale gives it a fixed address.

## Point the course at it

In `course.json`:

```json
"audio":   { "engine": "kokoro-ssh", "voice": "af_heart", "speed": 0.96 },
"shorts":  { "engine": "kokoro-ssh" },
"voicePC": { "host": "user@pc-address", "key": "~/.ssh/id_ed25519", "dir": "study-kit-tts" }
```

- `host`: the user name and the PC's address.
- `key`: the private key file on this computer (leave it out to use your usual SSH key).
- `dir`: the folder from step 2. Leave it out for the default; a relative folder is inside the user's folder.
- `python` (rarely needed): the Python to run on the PC, when it is not `<dir>/venv/Scripts/python.exe`.

Each run copies `tts_kokoro.py` and the list of lines to the PC, narrates only the lines it has not done yet, and
copies the clips back into `.cache/tts/`.
