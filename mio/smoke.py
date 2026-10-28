"""Verify the actual packaged application without requiring Python on the target."""
import json
from pathlib import Path
import subprocess
import tempfile
import traceback


def run(output_path):
    result = {'ok': False}
    try:
        import imageio_ffmpeg
        import numpy as np
        from scipy.io.wavfile import write
        from PySide6.QtWidgets import QApplication
        from .ui import Window, STYLE
        from .core import read_track, analyze, romanize, write_tags, restore, digest
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / 'smoke.wav'
            flac = Path(folder) / 'smoke.flac'
            rng = np.random.default_rng(5)
            write(wav, 44100, (rng.normal(0, .05, 88200)*32767).astype(np.int16))
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(wav),
                            str(flac)], check=True, capture_output=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            t = read_track(str(flac))
            before = digest(flac)
            a = analyze(t)
            roma = romanize('[00:01.00]こんにちは')
            assert 'konnichiha' in roma
            record = write_tags(t, '[00:01.00]こんにちは', None, roma)
            assert read_track(str(flac)).lyrics == '[00:01.00]こんにちは'
            restore(record)
            assert digest(flac) == before
            app = QApplication.instance() or QApplication([])
            app.setStyleSheet(STYLE)
            w = Window()
            w.resize(1280, 880)
            w.show()
            app.processEvents()
            assert not w.grab().isNull()
            w.close()
            result = {'ok': True, 'checks': ['ffmpeg decode', 'scipy STFT', 'offline Japanese dictionary',
                      'FLAC tags', 'backup and restore SHA-256', 'native Qt window render'],
                      'verdict': a.verdict}
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
