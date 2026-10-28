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
        path = Path(d) / 'A quiet morning.wav'
        sr = 44100
        t = np.arange(sr*30)/sr
        rng = np.random.default_rng(41)
        x = .22*np.sin(2*np.pi*440*t) + .08*np.sin(2*np.pi*880*t) + .005*rng.normal(size=t.shape)
        write(path, sr, (x*32767).astype(np.int16))
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
            from PySide6.QtCore import QUrl
            w.player.setSource(QUrl())
            app.quit()
        QTimer.singleShot(500, shot)
        # Keep temporary audio alive until screenshots are captured.
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        QTimer.singleShot(1300, loop.quit)
        loop.exec()
QTimer.singleShot(400, capture)
app.exec()
