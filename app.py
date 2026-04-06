import os
import platform
import shutil
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent
RECORDINGS_DIR = BASE_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Screen Recorder with System Audio")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class FFmpegRecorder:
    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen] = None
        self.output_path: Optional[Path] = None

    def ffmpeg_path(self) -> Optional[str]:
        return shutil.which("ffmpeg")

    def ffmpeg_available(self) -> bool:
        return self.ffmpeg_path() is not None

    def current_os(self) -> str:
        return platform.system().lower()

    def is_recording(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def build_command(
        self,
        output_path: Path,
        fps: int,
        include_system_audio: bool,
        include_mic: bool,
        mic_device: str,
        system_audio_device: str,
        display: str,
        screen_size: str,
        offset_x: int,
        offset_y: int,
        video_codec: str,
        video_preset: str,
        video_crf: int,
        audio_bitrate: str,
    ) -> list[str]:
        ffmpeg = self.ffmpeg_path()
        if not ffmpeg:
            raise RuntimeError("FFmpeg is not installed or not found in PATH.")

        system = self.current_os()

        cmd = [ffmpeg, "-y"]

        if system == "windows":
            cmd += [
                "-f", "gdigrab",
                "-framerate", str(fps),
                "-offset_x", str(offset_x),
                "-offset_y", str(offset_y),
                "-video_size", screen_size,
                "-i", "desktop",
            ]

            if include_system_audio:
                audio_dev = system_audio_device.strip() or "audio=virtual-audio-capturer"
                cmd += ["-f", "dshow", "-i", audio_dev]

            if include_mic:
                mic_dev = mic_device.strip()
                if mic_dev:
                    cmd += ["-f", "dshow", "-i", f"audio={mic_dev}"]

            if include_system_audio and include_mic:
                cmd += [
                    "-filter_complex",
                    "[1:a][2:a]amix=inputs=2:duration=longest[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                ]
            elif include_system_audio and not include_mic:
                cmd += ["-map", "0:v:0", "-map", "1:a:0"]
            elif include_mic and not include_system_audio:
                cmd += ["-map", "0:v:0", "-map", "1:a:0"]
            else:
                cmd += ["-map", "0:v:0"]

        elif system == "linux":
            cmd += [
                "-f", "x11grab",
                "-framerate", str(fps),
                "-video_size", screen_size,
                "-i", f"{display}+{offset_x},{offset_y}",
            ]

            if include_system_audio:
                pulse_source = system_audio_device.strip() or "default"
                cmd += ["-f", "pulse", "-i", pulse_source]

            if include_mic:
                mic_source = mic_device.strip()
                if mic_source:
                    cmd += ["-f", "pulse", "-i", mic_source]

            if include_system_audio and include_mic:
                cmd += [
                    "-filter_complex",
                    "[1:a][2:a]amix=inputs=2:duration=longest[aout]",
                    "-map", "0:v:0",
                    "-map", "[aout]",
                ]
            elif include_system_audio and not include_mic:
                cmd += ["-map", "0:v:0", "-map", "1:a:0"]
            elif include_mic and not include_system_audio:
                cmd += ["-map", "0:v:0", "-map", "1:a:0"]
            else:
                cmd += ["-map", "0:v:0"]

        elif system == "darwin":
            # macOS screen capture works through avfoundation, but true system-audio capture
            # generally requires a loopback driver such as BlackHole.
            av_input = display.strip() or "1"
            cmd += [
                "-f", "avfoundation",
                "-framerate", str(fps),
                "-i", f"{av_input}:none",
            ]

            if include_system_audio or include_mic:
                raise RuntimeError(
                    "On macOS, system audio capture usually requires a loopback device "
                    "such as BlackHole and custom AVFoundation device selection. "
                    "This starter version records screen only on macOS."
                )

            cmd += ["-map", "0:v:0"]

        else:
            raise RuntimeError(f"Unsupported OS: {platform.system()}")

        codec = video_codec.strip().lower() or "libx264"
        if codec not in {"libx264", "libx265"}:
            raise RuntimeError("Unsupported video codec. Use libx264 or libx265.")

        preset = video_preset.strip().lower() or "medium"
        if preset not in {
            "ultrafast", "superfast", "veryfast", "faster", "fast",
            "medium", "slow", "slower", "veryslow",
        }:
            raise RuntimeError("Unsupported preset value.")

        crf = max(18, min(video_crf, 35))

        cmd += [
            "-c:v", codec,
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ]

        if include_system_audio or include_mic:
            cmd += ["-c:a", "aac", "-b:a", audio_bitrate.strip() or "128k"]

        cmd += [str(output_path)]
        return cmd

    def start(
        self,
        fps: int = 12,
        include_system_audio: bool = True,
        include_mic: bool = False,
        mic_device: str = "",
        system_audio_device: str = "",
        display: str = ":0.0",
        screen_size: str = "1920x1080",
        offset_x: int = 0,
        offset_y: int = 0,
        video_codec: str = "libx265",
        video_preset: str = "medium",
        video_crf: int = 28,
        audio_bitrate: str = "128k",
    ) -> dict:
        if self.is_recording():
            return {"ok": False, "message": "Recording is already in progress."}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_path = RECORDINGS_DIR / f"recording_{timestamp}.mp4"

        try:
            cmd = self.build_command(
                output_path=self.output_path,
                fps=fps,
                include_system_audio=include_system_audio,
                include_mic=include_mic,
                mic_device=mic_device,
                system_audio_device=system_audio_device,
                display=display,
                screen_size=screen_size,
                offset_x=offset_x,
                offset_y=offset_y,
                video_codec=video_codec,
                video_preset=video_preset,
                video_crf=video_crf,
                audio_bitrate=audio_bitrate,
            )
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {
                "ok": True,
                "message": "Recording started.",
                "file": self.output_path.name,
            }
        except Exception as e:
            self.process = None
            return {"ok": False, "message": f"Could not start recording: {e}"}

    def stop(self) -> dict:
        if not self.is_recording():
            return {"ok": False, "message": "No active recording to stop."}

        try:
            if self.process and self.process.stdin:
                self.process.stdin.write(b"q\n")
                self.process.stdin.flush()
            self.process.wait(timeout=8)
        except Exception:
            if self.process:
                self.process.terminate()
        finally:
            self.process = None

        return {
            "ok": True,
            "message": "Recording stopped.",
            "file": self.output_path.name if self.output_path else None,
            "path": str(self.output_path) if self.output_path else None,
        }

    def status(self) -> dict:
        system = self.current_os()
        return {
            "is_recording": self.is_recording(),
            "current_file": self.output_path.name if self.output_path else None,
            "recordings_dir": str(RECORDINGS_DIR),
            "ffmpeg_installed": self.ffmpeg_available(),
            "os": system,
            "local_url": f"http://{local_ip()}:8080",
        }


recorder = FFmpegRecorder()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "status": recorder.status(),
        },
    )


@app.get("/api/status")
async def get_status():
    return JSONResponse(recorder.status())


@app.post("/api/start")
async def start_recording(
    fps: int = Form(12),
    include_system_audio: bool = Form(True),
    include_mic: bool = Form(False),
    mic_device: str = Form(""),
    system_audio_device: str = Form(""),
    display: str = Form(":0.0"),
    screen_size: str = Form("1920x1080"),
    offset_x: int = Form(0),
    offset_y: int = Form(0),
    video_codec: str = Form("libx265"),
    video_preset: str = Form("medium"),
    video_crf: int = Form(28),
    audio_bitrate: str = Form("128k"),
):
    result = recorder.start(
        fps=fps,
        include_system_audio=include_system_audio,
        include_mic=include_mic,
        mic_device=mic_device,
        system_audio_device=system_audio_device,
        display=display,
        screen_size=screen_size,
        offset_x=offset_x,
        offset_y=offset_y,
        video_codec=video_codec,
        video_preset=video_preset,
        video_crf=video_crf,
        audio_bitrate=audio_bitrate,
    )
    status_code = 200 if result["ok"] else 400
    return JSONResponse(result, status_code=status_code)


@app.post("/api/stop")
async def stop_recording():
    result = recorder.stop()
    status_code = 200 if result["ok"] else 400
    return JSONResponse(result, status_code=status_code)
