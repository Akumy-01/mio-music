import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from mio.ui import Window, STYLE
from mio.core import Track


def test_ui_switch_preserves_edits():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    w = Window()
    w.tracks = [Track('C:/one.flac', 'One'), Track('C:/two.flac', 'Two')]
    w.list.addItems(['One', 'Two'])
    w.list.setCurrentRow(0)
    w.lyrics.setPlainText('edited lyric')
    w.romaji.setPlainText('edited romaji')
    w.title_edit.setText('search edit')
    w.list.setCurrentRow(1)
    assert not w.lyrics.toPlainText()
    w.list.setCurrentRow(0)
    assert w.lyrics.toPlainText() == 'edited lyric'
    assert w.romaji.toPlainText() == 'edited romaji'
    assert w.title_edit.text() == 'search edit'
    w.lyrics.setPlainText('changed')
    assert not w.romaji.toPlainText()
    w.close()


def test_background_job_completes_on_ui_thread():
    from PySide6.QtCore import QEventLoop, QTimer, QThread
    app = QApplication.instance() or QApplication([])
    w = Window()
    loop = QEventLoop()
    result = []
    def finished(value):
        result.append((value, QThread.currentThread() == app.thread()))
        loop.quit()
    w.job('test', lambda: 42, finished)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert result == [(42, True)]
    assert not w.busy
    w.close()
