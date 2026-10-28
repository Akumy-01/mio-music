"""Generate screenshots using a synthetic, original audio fixture. No copyrighted music."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import numpy as np
from scipy.io.wavfile import write
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from mio.ui import Window, STYLE
from mio.core import read_track, analyze

app = QApplication([])
for font in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf', 'seguisym.ttf', 'msgothic.ttc'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
w = Window()
w.show()
root = Path(__file__).resolve().parents[1]
(root / 'docs').mkdir(exist_ok=True)

def capture():
    w.grab().save(str(root / 'docs' / 'screenshot-empty.png'))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'A quiet morning.flac'
        sr = 44100
        t = np.arange(sr*30)/sr
        rng = np.random.default_rng(41)
        x = .22*np.sin(2*np.pi*440*t) + .08*np.sin(2*np.pi*880*t) + .005*rng.normal(size=t.shape)
        wav_path = path.with_suffix('.wav')
        write(wav_path, sr, (x*32767).astype(np.int16))
        import subprocess, imageio_ffmpeg
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(wav_path), str(path)],
                       check=True, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        track = read_track(str(path))
        track.artist, track.album = 'Mio Studio', 'Small moments'
        w.tracks.append(track)
        w.list.addItem('A quiet morning\nMio Studio')
        w.list.setCurrentRow(0)
        w.count.setText('我的工作台  ·  1')
        w.analyses[track.path] = analyze(track)
        w.show_analysis(w.analyses[track.path])
        def shot():
            w.grab().save(str(root / 'docs' / 'screenshot-spectrum.png'))
            w.tabs.setCurrentIndex(1)
            w.lyrics.setPlainText('[00:01.00]こんにちは、朝の光\n[00:05.00]小さな音楽と歩こう\n\n（界面演示：原创示例文本）')
            from mio.core import romanize
            w.romaji.setPlainText(romanize(w.lyrics.toPlainText()))
            QTimer.singleShot(400, shot2)
        def shot2():
            w.grab().save(str(root / 'docs' / 'screenshot-lyrics.png'))
            w.remember_lyric('原创示例 · 原文', w.lyrics.toPlainText(), '原创演示文本')
            w.remember_cover('原创演示封面', (root/'assets/mio.png').read_bytes(), 'Mio 原创图标演示')
            w.write_panel.select_lyrics('preview')
            w.tabs.setCurrentIndex(3)
            QTimer.singleShot(350, shot3)
        def shot3():
            w.grab().save(str(root / 'docs' / 'screenshot-write.png'))
            from unittest.mock import patch
            from mio.spotify_dialog import SpotifyDialog
            from mio import spotify_direct
            with patch.object(spotify_direct, 'get_session', return_value=None):
                dialog = SpotifyDialog(w)
                dialog.mode.setCurrentIndex(0)
                dialog.song.setText('https://open.spotify.com/track/…')
                dialog.resize(760, 560)
                dialog.show()
                app.processEvents()
                dialog.grab().save(str(root / 'docs' / 'screenshot-spotify.png'))
                dialog.close()
            from PySide6.QtCore import QUrl
            w.player.setSource(QUrl())
            app.quit()
        QTimer.singleShot(500, shot)
        # Keep temporary audio alive until screenshots are captured.
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        QTimer.singleShot(1800, loop.quit)
        loop.exec()
QTimer.singleShot(400, capture)
app.exec()
