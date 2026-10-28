"""First-use setup and single-click fetch for built-in Spotify access."""
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QFrame, QPushButton, QDialogButtonBox)
from .spotify import track_id, endpoint_url
from . import spotify_direct


class SpotifyDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings('MioMusic', 'MioMusic')
        self.result_config = None
        self.setWindowTitle('Spotify 歌词 · 在 Mio 内获取')
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        heading = QLabel('粘贴歌曲链接，直接获取歌词。')
        heading.setStyleSheet('font-size:20px;font-weight:600;')
        layout.addWidget(heading)
        self.song = QLineEdit()
        self.song.setPlaceholderText('Spotify 歌曲链接 / spotify:track: URI / Track ID')
        layout.addWidget(self.song)
        self.mode = QComboBox()
        self.mode.addItem('内置直连 · 无需 Docker 或额外服务', 'direct')
        self.mode.addItem('高级 · 使用自己的 spotify-lyrics-api 服务', 'service')
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.settings.value('spotify/mode', 'direct'))))
        layout.addWidget(self.mode)
        self.account_frame = QFrame()
        account_layout = QVBoxLayout(self.account_frame)
        account_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.account_status = QLabel()
        self.account_status.setWordWrap(True)
        row.addWidget(self.account_status, 1)
        self.configure = QPushButton('配置 / 更新会话')
        self.configure.clicked.connect(self.toggle_setup)
        row.addWidget(self.configure)
        account_layout.addLayout(row)
        self.setup_frame = QFrame()
        self.setup_frame.setObjectName('card')
        setup = QVBoxLayout(self.setup_frame)
        notice = QLabel('首次需要你自己的 Spotify 登录会话（SP_DC）。配置一次后，通常只需粘贴歌曲链接获取；会话失效时在这里更新。')
        notice.setWordWrap(True)
        setup.addWidget(notice)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText('只粘贴 SP_DC 的值；不会显示或写入项目文件')
        setup.addWidget(self.secret)
        self.persist = QCheckBox('保存到当前 Windows 用户的凭据管理器')
        self.persist.setChecked(True)
        self.persist.setToolTip('取消勾选仅在本次使用新会话，不修改此前已保存的会话。')
        setup.addWidget(self.persist)
        actions = QHBoxLayout()
        login = QPushButton('打开 Spotify 登录')
        login.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://open.spotify.com/')))
        actions.addWidget(login)
        help_button = QPushButton('如何取得自己的 SP_DC')
        help_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://github.com/Akumy-01/mio-music/blob/main/docs/SPOTIFY.md#首次配置')))
        actions.addWidget(help_button)
        forget = QPushButton('清除已保存会话')
        forget.clicked.connect(self.forget)
        actions.addWidget(forget)
        setup.addLayout(actions)
        account_layout.addWidget(self.setup_frame)
        layout.addWidget(self.account_frame)
        self.service_frame = QFrame()
        service_layout = QVBoxLayout(self.service_frame)
        service_layout.setContentsMargins(0, 0, 0, 0)
        service_layout.addWidget(QLabel('自建服务地址（只在高级模式使用）'))
        self.endpoint = QLineEdit(self.settings.value('spotify/endpoint', 'http://127.0.0.1:8765/'))
        service_layout.addWidget(self.endpoint)
        layout.addWidget(self.service_frame)
        self.notice = QLabel('会话仅发送给 Spotify 的登录接口；程序不读取浏览器 Cookie，也不使用公共账号代理。')
        self.notice.setWordWrap(True)
        self.notice.setObjectName('muted')
        layout.addWidget(self.notice)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Ok).setText('获取歌词')
        controls.button(QDialogButtonBox.StandardButton.Ok).setObjectName('primary')
        controls.accepted.connect(self.validate)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        self.refresh_account()
        self.mode.currentIndexChanged.connect(self.update_mode)
        self.update_mode()

    def refresh_account(self):
        try:
            present = bool(spotify_direct.get_session())
            self.account_status.setText('已有本机会话 · 可直接获取（有效性在请求时验证）' if present else '尚未配置 Spotify 登录会话')
        except ValueError:
            present = False
            self.account_status.setText('凭据存储暂不可用，可取消保存并仅在本次使用')
        self.setup_frame.setVisible(not present)

    def update_mode(self, *_):
        direct = self.mode.currentData() == 'direct'
        self.account_frame.setVisible(direct)
        self.service_frame.setVisible(not direct)

    def toggle_setup(self):
        self.setup_frame.setVisible(not self.setup_frame.isVisible())

    def forget(self):
        try:
            spotify_direct.forget_session()
            self.secret.clear()
            self.refresh_account()
            self.notice.setText('本机已保存会话和内存令牌已清除。')
        except ValueError as e:
            self.notice.setText(str(e))

    def validate(self):
        try:
            result = {'id': track_id(self.song.text()), 'mode': self.mode.currentData()}
            if result['mode'] == 'direct':
                if self.secret.text().strip():
                    spotify_direct.configure_session(self.secret.text(), self.persist.isChecked())
                if not spotify_direct.get_session():
                    raise ValueError('请先填写自己的 SP_DC；首次配置后无需额外服务。')
            else:
                result['endpoint'] = endpoint_url(self.endpoint.text())
                self.settings.setValue('spotify/endpoint', result['endpoint'])
            self.settings.setValue('spotify/mode', result['mode'])
            self.result_config = result
            self.secret.clear()
            self.accept()
        except ValueError as e:
            self.notice.setText(str(e))
