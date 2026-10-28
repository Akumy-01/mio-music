"""Verify the actual packaged application without requiring Python on the target."""
import json
from pathlib import Path
import subprocess
import tempfile
import traceback


def run_lyrics(output_path):
    """Live test of the executable's HTTP/TLS and provider parsing; not a CI dependency."""
    report = {'ok': False}
    try:
        from .core import Track
        from .lyrics import search_lyrics, fetch_lyrics
        from . import __version__
        result = search_lyrics(Track('', 'Lemon', '米津玄師', duration=255), refresh=True)
        fetches = []
        for source in ('netease', 'kugou', 'lrclib'):
            row = next((r for r in result.rows if r['source'] == source and not r.get('instrumental')), None)
            if row:
                try:
                    p = fetch_lyrics(row, refresh=True)
                    fetches.append({'source': source, 'ok': bool(p.text), 'characters': len(p.text),
                                    'romaji_characters': len(p.romaji), 'stale': p.stale})
                except Exception as e:
                    fetches.append({'source': source, 'ok': False, 'error': str(e)})
        report = {'ok': any(f['ok'] for f in fetches), 'version': __version__,
                  'statuses': result.statuses, 'fetches': fetches}
    except Exception:
        report['error'] = traceback.format_exc()
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


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
            w.tracks = [read_track(str(flac))]
            w.list.addItem('smoke')
            w.list.setCurrentRow(0)
            assert w.player.source().isEmpty()
            w.lyrics.setPlainText('[00:01.00]original smoke fixture')
            w.write_panel.select_lyrics('editor')
            assert w.write_panel.plan().lyrics == '[00:01.00]original smoke fixture'
            from PySide6.QtCore import QEventLoop, QTimer
            def finish_job():
                loop = QEventLoop()
                timer = QTimer()
                timer.timeout.connect(lambda: loop.quit() if not w.busy else None)
                timer.start(10)
                QTimer.singleShot(10000, loop.quit)
                loop.exec()
                timer.stop()
                assert not w.busy
            w.save()
            finish_job()
            assert read_track(str(flac)).lyrics == '[00:01.00]original smoke fixture'
            assert w.write_panel.selected_record()
            w.undo()
            finish_job()
            assert digest(flac) == before
            # Verify the packaged HTTP adapter, without any Spotify account credentials.
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
            from threading import Thread
            from .spotify import fetch_spotify
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': False, 'syncType': 'LINE_SYNCED',
                        'lines': [{'timeTag': '00:01.00', 'words': 'original protocol fixture'}]}).encode())
                def log_message(self, *args): pass
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = fetch_spotify(f'http://127.0.0.1:{server.server_port}/', '5f8eCNwTlr0RJopE9vQ6mB')
                assert payload.text == '[00:01.00]original protocol fixture'
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            w.resize(1280, 880)
            w.show()
            app.processEvents()
            assert not w.grab().isNull()
            w.close()
            result = {'ok': True, 'checks': ['ffmpeg decode', 'scipy STFT', 'offline Japanese dictionary',
                      'FLAC tags', 'backup and restore SHA-256', 'native Qt window render',
                      'GUI write plan / asynchronous save / selected-record undo',
                      'Spotify HTTP protocol (local fixture, not live account)'],
                      'verdict': a.verdict}
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
