# FastAPI Screen Recorder with System Audio

This version uses FFmpeg directly because system-audio capture is much easier that way.

## What it can do
- Record screen
- Record system audio
- Optionally mix microphone + system audio
- Save output as MP4
- Reduce output size with H.265/H.264 quality controls

## Run

```bash
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8080
```

Open:
```text
http://127.0.0.1:8080
```

## You must install FFmpeg

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Windows
Install FFmpeg and make sure it is available in PATH.

### macOS
```bash
brew install ffmpeg
```

## Platform notes

### Windows
For system audio, a common loopback device is:
```text
audio=virtual-audio-capturer
```

You may need a virtual audio capture driver for reliable system-audio capture.

### Linux
For system audio with PulseAudio / PipeWire:
- Try `default`
- Or use a monitor source from:

```bash
pactl list short sources
```

A monitor source often looks like:
```text
alsa_output.pci-0000_00_1f.3.analog-stereo.monitor
```

### macOS
Screen recording works, but real system-audio capture usually needs a loopback driver such as BlackHole.

## Useful checks

### Linux display
```bash
echo $DISPLAY
xrandr
```

### Linux audio sources
```bash
pactl list short sources
```

### Windows DirectShow devices
```bash
ffmpeg -list_devices true -f dshow -i dummy
```

## Example Linux settings in the UI
- Display: `:0.0`
- Screen Size: `1920x1080`
- System Audio Device: `default`
- Video Codec: `libx265`
- Video Preset: `medium`
- Video CRF: `28`
- Audio Bitrate: `128k`

## Example Windows settings in the UI
- Display / Input: leave default
- Screen Size: `1920x1080`
- System Audio Device: `audio=virtual-audio-capturer`
- Video Codec: `libx264` if you need maximum playback compatibility

## File-size tuning

- Default optimized settings now use `libx265` with `CRF 28` and `128k` AAC audio.
- Lower `CRF` means better quality and larger files.
- Higher `CRF` means smaller files and lower quality.
- `libx265` usually gives smaller files than `libx264`, but some older players handle `libx264` more reliably.
- `medium` is a good balance. Using `slow` can shrink files a bit more, but encoding uses more CPU.
