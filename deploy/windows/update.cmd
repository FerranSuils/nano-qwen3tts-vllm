@echo off
rem Pull this checkout and restart the voices service. Secrets stay in
rem C:\ProgramData\nano-qwen3tts\voices.env and are not in git.
cd /d C:\apps\nano-qwen3tts
git pull --ff-only
schtasks /End /TN nano-qwen3tts-voices
schtasks /Run /TN nano-qwen3tts-voices
echo Restarted nano-qwen3tts-voices
