import base64
import os
import shutil
import subprocess
import tempfile

import requests

SPEECHIFY_API_KEY = ""
SPEECHIFY_TTS_URL = "https://api.speechify.ai/v1/audio/speech"
PLAYER_CANDIDATES = (
    "ffplay",
    "mpg123",
    "mpv",
    "mplayer",
    "cvlc",
    "vlc",
    "gst-play-1.0",
    "powershell",
)

def get_audio_players():
    players = []
    for player in PLAYER_CANDIDATES:
        if shutil.which(player):
            players.append(player)

    if not players:
        raise RuntimeError(
            "No supported MP3 player found. Install one of: ffplay, mpg123, mpv, mplayer, cvlc, vlc, gst-play-1.0, or use Windows PowerShell playback."
        )

    return players

def play_audio_file(file_path, player):
    if player == "ffplay":
        command = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", file_path]
    elif player == "mpg123":
        command = [player, "-q", file_path]
    elif player == "mpv":
        command = [player, "--no-video", "--really-quiet", file_path]
    elif player == "mplayer":
        command = [player, "-really-quiet", file_path]
    elif player == "cvlc":
        command = [player, "--play-and-exit", "--intf", "dummy", file_path]
    elif player == "vlc":
        command = [player, "--play-and-exit", "--intf", "dummy", file_path]
    elif player == "gst-play-1.0":
        command = [player, "--no-interactive", file_path]
    elif player == "powershell":
        command = [
            player,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "Add-Type -AssemblyName presentationCore; "
                "$player = New-Object System.Windows.Media.MediaPlayer; "
                f"$player.Open([Uri]'{file_path}'); "
                "$player.Play(); "
                "while ($player.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 100 }; "
                "Start-Sleep -Milliseconds ($player.NaturalDuration.TimeSpan.TotalMilliseconds + 250); "
                "$player.Stop(); "
                "$player.Close();"
            ),
        ]
    else:
        raise RuntimeError(f"Unsupported audio player: {player}")

    subprocess.run(command, check=True)

def speak_text(text):
    headers = {
        "Authorization": f"Bearer {SPEECHIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "input": text,
        "voice_id": "leon",
        "audio_format": "mp3",
    }

    response = requests.post(SPEECHIFY_TTS_URL, json=data, headers=headers, timeout=30)
    response.raise_for_status()
    result = response.json()
    audio_bytes = base64.b64decode(result["audio_data"])

    players = get_audio_players()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
        temp_audio.write(audio_bytes)
        temp_audio_path = temp_audio.name

    try:
        last_error = None
        for player in players:
            try:
                play_audio_file(temp_audio_path, player)
                return
            except (OSError, subprocess.SubprocessError) as exc:
                last_error = exc

        raise RuntimeError(f"All audio players failed: {last_error}")
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


# insert lines into easyocr_integration.py
# from speechify_implementation import speak_text
# speak_text(word) in def run_lookup_for_words(words)
