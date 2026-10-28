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


def wait_for_job(w):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: loop.quit() if not w.busy else None)
    timer.start(10)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    timer.stop()
    assert not w.busy


def test_lyrics_outage_is_inline_and_preserves_editor(monkeypatch):
    from mio import ui
    from mio.lyrics import SearchResult
    app = QApplication.instance() or QApplication([])
    w = Window()
    w.tracks = [Track('C:/one.flac', 'One')]
    w.list.addItem('One')
    w.list.setCurrentRow(0)
    w.lyrics.setPlainText('my unsaved lyrics')
    monkeypatch.setattr(ui, 'search_online_lyrics', lambda *a: SearchResult([], [
        {'source': 'lrclib', 'label': 'LRCLIB', 'ok': False, 'count': 0, 'message': 'HTTP 503'}]))
    monkeypatch.setattr(ui.QMessageBox, 'warning', lambda *a: (_ for _ in ()).throw(AssertionError('modal error')))
    w.search_lyrics()
    wait_for_job(w)
    assert '503' in w.provider_status.text()
    assert '均未连接成功' in w.status.text()
    assert w.lyrics.toPlainText() == 'my unsaved lyrics'
    w.close()


def test_candidate_fetch_failure_preserves_editor_and_other_choices(monkeypatch):
    from mio import ui
    app = QApplication.instance() or QApplication([])
    w = Window()
    w.tracks = [Track('C:/one.flac', 'One')]
    w.list.addItem('One')
    w.list.setCurrentRow(0)
    w.lyrics.setPlainText('old lyrics')
    def fail(*args): raise ValueError('HTTP 503')
    monkeypatch.setattr(ui, 'fetch_lyrics', fail)
    monkeypatch.setattr(ui.QMessageBox, 'warning', lambda *a: (_ for _ in ()).throw(AssertionError('modal error')))
    w.candidates.addItem('网易云', {'sourceLabel': '网易云音乐', 'source': 'netease', 'id': '1'})
    w.candidates.setCurrentIndex(1)
    wait_for_job(w)
    assert w.lyrics.toPlainText() == 'old lyrics'
    assert '503' in w.lyrics_source.text()
    assert w.candidates.count() == 2
    w.close()


def test_lazy_playback_released_before_real_write(tmp_path):
    import subprocess, imageio_ffmpeg
    from PySide6.QtTest import QTest
    from mio.core import read_track, write_tags
    path = tmp_path / "I'm still alive today.flac"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i',
        'sine=frequency=440:duration=1', str(path)], check=True, capture_output=True)
    app = QApplication.instance() or QApplication([])
    w = Window()
    w.tracks = [read_track(str(path))]
    w.list.addItem(path.name)
    w.list.setCurrentRow(0)
    assert w.player.source().isEmpty()
    w.toggle_play()
    QTest.qWait(180)
    assert not w.player.source().isEmpty()
    w.release_player()
    assert w.player.source().isEmpty()
    write_tags(w.current(), 'original test lyric', None)
    assert read_track(str(path)).lyrics == 'original test lyric'
    w.close()


def test_same_second_history_selects_latest_append(tmp_path):
    import json
    path = str(tmp_path / 'example.flac')
    directory = tmp_path / '.mio'
    directory.mkdir()
    records = [{'record_id': key, 'time': '2026-10-28T20:00:00', 'path': path,
                'after_sha256': key, 'backup': str(directory/'backup.bak')} for key in ('earlier', 'latest')]
    (directory/'history.jsonl').write_text('\n'.join(json.dumps(r) for r in records), encoding='utf-8')
    app = QApplication.instance() or QApplication([])
    w = Window()
    w.tracks = [Track(path, 'Example')]
    w.list.addItem('Example')
    w.list.setCurrentRow(0)
    assert w.write_panel.selected_record()['record_id'] == 'latest'
    w.close()


def test_spotify_link_in_search_box_fetches_directly_with_saved_session(monkeypatch):
    from mio import ui, spotify_direct
    from mio.lyrics import LyricsPayload
    class Settings:
        def value(self, key, default=None): return default
    monkeypatch.setattr(ui, 'QSettings', lambda *a: Settings())
    monkeypatch.setattr(spotify_direct, 'get_session', lambda: 'fixture-saved-session')
    received = []
    def fetch(row, refresh=False):
        received.append(row)
        return LyricsPayload('[00:01.00]original direct fixture')
    monkeypatch.setattr(ui, 'fetch_lyrics', fetch)
    app = QApplication.instance() or QApplication([])
    w = Window()
    w.tracks = [Track('C:/example.flac', 'Example')]
    w.list.addItem('Example')
    w.list.setCurrentRow(0)
    w.title_edit.setText('https://open.spotify.com/track/5f8eCNwTlr0RJopE9vQ6mB')
    w.search_lyrics()
    wait_for_job(w)
    assert received[0]['mode'] == 'direct' and 'endpoint' not in received[0]
    assert 'fixture-saved-session' not in str(received)
    assert w.lyrics.toPlainText().endswith('original direct fixture')
    assert 'Spotify' in w.lyrics_source.text()
    assert w.write_panel.plan().lyrics.endswith('original direct fixture')
    w.close()
