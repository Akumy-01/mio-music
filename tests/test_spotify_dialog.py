import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication, QLineEdit, QDialog
from mio.spotify_dialog import SpotifyDialog
from mio import spotify_direct

ID = '5f8eCNwTlr0RJopE9vQ6mB'


class Settings:
    def __init__(self): self.values = {}
    def value(self, key, default=None): return self.values.get(key, default)
    def setValue(self, key, value): self.values[key] = value


def test_saved_session_single_fetch_has_no_cookie_in_config(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(spotify_direct, 'get_session', lambda: 'saved-fixture-cookie')
    settings = Settings()
    dialog = SpotifyDialog(settings=settings)
    assert dialog.mode.currentData() == 'direct'
    assert dialog.secret.echoMode() == QLineEdit.EchoMode.Password
    dialog.song.setText('https://open.spotify.com/track/' + ID)
    dialog.validate()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_config == {'id': ID, 'mode': 'direct'}
    assert 'saved-fixture-cookie' not in str(settings.values)
    dialog.close()


def test_first_use_requires_session_instead_of_server(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(spotify_direct, 'get_session', lambda: None)
    dialog = SpotifyDialog(settings=Settings())
    dialog.song.setText(ID)
    dialog.validate()
    assert dialog.result_config is None and 'SP_DC' in dialog.notice.text()
    dialog.close()
