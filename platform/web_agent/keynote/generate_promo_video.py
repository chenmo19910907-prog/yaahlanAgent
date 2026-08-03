#!/usr/bin/env python3
"""录制 Web Agent Keynote 自动放映，合成卡点 BGM，输出 MP4 宣传视频。

依赖：playwright、ffmpeg；首次运行会自动 pip install playwright 并安装 Chromium。

用法：
  python3 platform/web_agent/keynote/generate_promo_video.py
  python3 platform/web_agent/keynote/generate_promo_video.py --bpm 128 --port 18766
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
WEB_AGENT_DIR = BASE.parent
REPO_ROOT = WEB_AGENT_DIR.parents[1]
PROMO_VENV = BASE / ".venv-promo"
DEFAULT_PORT = 18766
DEFAULT_BPM = 128
OUTPUT_DIR = WEB_AGENT_DIR / "data" / "outputs" / "promo"
BEAT_TRACK = BASE / "assets" / "promo_beat.wav"


def _promo_python() -> str:
    venv_py = PROMO_VENV / "bin" / "python3"
    return str(venv_py if venv_py.is_file() else sys.executable)


def _ensure_playwright() -> None:
    venv_py = PROMO_VENV / "bin" / "python3"
    if not venv_py.is_file():
        print(f"[promo] 创建虚拟环境 {PROMO_VENV} …")
        subprocess.run([sys.executable, "-m", "venv", str(PROMO_VENV)], check=True)
    try:
        subprocess.run(
            [str(venv_py), "-c", "from playwright.sync_api import sync_playwright"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    except subprocess.CalledProcessError:
        pass
    print("[promo] 安装 playwright …")
    subprocess.run([str(venv_py), "-m", "pip", "install", "playwright", "-q"], check=True)
    subprocess.run([str(venv_py), "-m", "playwright", "install", "chromium"], check=True)


def _server_alive(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/keynote?cinema=1"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _start_server(port: int) -> subprocess.Popen[bytes] | None:
    if _server_alive(port):
        print(f"[promo] Web Agent 已在 127.0.0.1:{port} 运行")
        return None
    print(f"[promo] 启动 Web Agent :{port} …")
    proc = subprocess.Popen(
        [sys.executable, str(WEB_AGENT_DIR / "server.py"), "--port", str(port)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if _server_alive(port):
            return proc
        time.sleep(0.25)
    proc.kill()
    raise RuntimeError(f"Web Agent 未能在 :{port} 启动，请先手动运行 server.py")


def _generate_beat_wav(path: Path, *, duration_s: float, bpm: int) -> None:
    """用 Python 生成简约电子卡点 WAV。"""
    import struct
    import wave

    sample_rate = 44100
    n_samples = int(duration_s * sample_rate)
    beat_s = 60.0 / bpm
    frames = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        beat_i = int(t / beat_s)
        phase = t - beat_i * beat_s
        val = 0.015 * math.sin(2 * math.pi * 55 * t)
        if phase < 0.11:
            env = 1.0 - phase / 0.11
            if beat_i % 4 == 0:
                val += 0.55 * math.sin(2 * math.pi * 62 * t) * env
            elif beat_i % 2 == 0:
                val += 0.18 * math.sin(2 * math.pi * 880 * t) * env
            else:
                val += 0.09 * math.sin(2 * math.pi * 1400 * t) * env
        sample = int(max(-32767, min(32767, val * 32767)))
        frames.extend(struct.pack("<h", sample))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)


def _record_keynote(port: int, bpm: int, out_video: Path) -> float:
    venv_py = _promo_python()
    script = f"""
import shutil, time
from pathlib import Path
from playwright.sync_api import sync_playwright

url = "http://127.0.0.1:{port}/keynote?autoplay=1&cinema=1&bpm={bpm}&fast=1"
out_video = Path({str(out_video)!r})
out_video.parent.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={{"width": 1920, "height": 1080}},
        record_video_dir=str(out_video.parent),
        record_video_size={{"width": 1920, "height": 1080}},
        device_scale_factor=1,
    )
    page = context.new_page()
    page.goto(url, wait_until="networkidle", timeout=120000)
    page.wait_for_function(
        "() => document.body && document.body.classList.contains('kn-autoplay')",
        timeout=30000,
    )
    page.wait_for_function(
        "() => document.body.dataset.promoFinished === '1'",
        timeout=600000,
    )
    time.sleep(1.2)
    video = page.video
    page.close()
    context.close()
    browser.close()
    raw_path = Path(video.path())
    if raw_path != out_video:
        shutil.move(str(raw_path), str(out_video))
print(out_video)
"""
    subprocess.run([venv_py, "-c", script], check=True)
    return _probe_duration(out_video)


def _probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def _mux_audio(video: Path, audio: Path, output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video),
            "-i", str(audio),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(output),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Web Agent 发布会风格宣传视频")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--bpm", type=int, default=DEFAULT_BPM)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "Web_Agent_Promo.mp4")
    args = parser.parse_args()

    _ensure_playwright()
    server = _start_server(args.port)

    tmp_dir = Path(tempfile.mkdtemp(prefix="web_agent_promo_"))
    raw_video = tmp_dir / "raw.webm"
    beat_wav = tmp_dir / "beat.wav"
    try:
        print(f"[promo] 录制 http://127.0.0.1:{args.port}/keynote?autoplay=1&cinema=1&bpm={args.bpm}")
        duration = _record_keynote(args.port, args.bpm, raw_video) + 0.5
        print(f"[promo] 录制完成，时长约 {duration:.1f}s")
        print(f"[promo] 生成 {args.bpm} BPM 卡点音轨 …")
        _generate_beat_wav(beat_wav, duration_s=duration, bpm=args.bpm)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        print(f"[promo] 合成 MP4 → {args.output}")
        _mux_audio(raw_video, beat_wav, args.output)
        print(f"[promo] 完成：{args.output}")
        print(f"[promo] 浏览器预览：/keynote?autoplay=1&cinema=1&bpm={args.bpm}&fast=1")
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
