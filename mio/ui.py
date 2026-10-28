from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import traceback
from dataclasses import replace

import numpy as np
from PySide6.QtCore import (Qt, QObject, Signal, QRunnable, QThreadPool, QUrl,
                            QPropertyAnimation, QEasingCurve, QTimer)
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap, QDesktopServices)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QTabWidget,
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QMessageBox, QProgressBar, QFrame,
    QGraphicsOpacityEffect, QSplitter, QScrollArea)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from .core import (Track, Analysis, read_track, analyze, romanize, write_tags, restore,
                   SUPPORTED, WRITABLE, image_bytes)
from .providers import find_lyrics, find_covers, download_cover

STYLE = '''
QWidget { background:#f5f5f1; color:#24372f; font-family:"Microsoft YaHei UI"; font-size:13px; }
QMainWindow { background:#f5f5f1; }
QWidget#sidebar { background:#eaece5; border-right:1px solid #dce0d5; }
QLabel { background:transparent; }
QLabel#muted { color:#738176; font-size:12px; }
QLabel#eyebrow { color:#708571; font-size:11px; letter-spacing:3px; }
QLabel#heading { font-size:28px; font-weight:600; }
QLabel#brand { font-size:32px; font-weight:700; letter-spacing:2px; }
QFrame#card { background:#ffffff; border:1px solid #e2e6dd; border-radius:16px; }
QFrame#card QLabel { background:transparent; }
QPushButton { background:#fff; border:1px solid #d8ded2; padding:10px 16px; border-radius:9px; }
QPushButton:hover { background:#edf1e7; border-color:#9cac96; }
QPushButton:pressed { background:#dce5d4; }
QPushButton:disabled { color:#a1aba0; background:#eee; border-color:#e2e5df; }
QPushButton#primary { background:#344f3c; color:white; border:1px solid #344f3c; font-weight:600; }
QPushButton#primary:hover { background:#48684f; }
QPushButton#primary:disabled { background:#b3bdb0; border-color:#b3bdb0; }
QLineEdit, QTextEdit, QComboBox { background:white; border:1px solid #dde2d7; border-radius:8px; padding:9px; selection-background-color:#c6d5bc; }
QLineEdit:focus, QTextEdit:focus { border-color:#78916c; }
QTextEdit { font-size:14px; line-height:1.6; }
QListWidget { background:transparent; border:0; outline:none; }
QListWidget::item { padding:14px 10px; border-radius:8px; margin:3px 0; }
QListWidget::item:selected { background:#d9e2d1; color:#253e2b; }
QTabWidget::pane { border:0; background:transparent; }
QTabBar::tab { color:#839080; padding:13px 19px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#344f3c; border-bottom:2px solid #344f3c; }
QTabBar::tab:hover { color:#344f3c; }
QCheckBox { spacing:8px; background:transparent; }
QProgressBar { background:#e2e7dc; border:0; border-radius:2px; max-height:4px; }
QProgressBar::chunk { background:#76956a; border-radius:2px; }
QScrollBar:vertical { background:transparent; width:7px; }
QScrollBar::handle:vertical { background:#c6cebf; border-radius:3px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QStatusBar { background:#edf0e8; color:#697c64; }
'''


class JobSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.signals = fn, JobSignals()

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except Exception as e:
            self.signals.failed.emit(str(e) or type(e).__name__)


def label(text, name=None):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(True)
    return w


def button(text, callback, primary=False):
    w = QPushButton(text)
    if primary:
        w.setObjectName('primary')
    w.clicked.connect(callback)
    return w


class Spectrum(QWidget):
    def __init__(self):
        super().__init__()
        self.result = None
        self.setMinimumHeight(275)

    def set_result(self, result):
        self.result = result
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(48, 15, -16, -40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#172a27'))
        p.drawRoundedRect(rect, 12, 12)
        p.setPen(QColor('#98aaa0'))
        if self.result is None:
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, '导入音乐，查看声音的纹理\n\n频率 × 时间 · 本地分析')
            return
        r = self.result
        # Show up to 24 kHz; analysis still uses the complete native frequency range.
        mask = r.frequency <= min(r.frequency[-1], 24000)
        a = np.clip((r.db[mask] + 110) / 80, 0, 1)
        stops = np.array([0, .25, .50, .75, 1])
        palette = np.array([[23, 42, 39], [41, 78, 69], [91, 142, 107], [189, 202, 134], [249, 229, 174]])
        rgb = np.stack([np.interp(a, stops, palette[:, i]) for i in range(3)], axis=2).astype('uint8')
        rgb = np.ascontiguousarray(rgb[::-1])
        im = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
        p.drawImage(rect, im)
        p.setFont(QFont('Segoe UI', 9))
        for fraction in (0, .25, .5, .75, 1):
            y = rect.bottom() - int(fraction * rect.height())
            p.setPen(QColor('#66776d'))
            p.drawText(0, y - 8, 43, 18, Qt.AlignmentFlag.AlignRight,
                       f'{fraction * r.frequency[mask][-1] / 1000:.0f}k')
        n = r.segments
        for i in range(n):
            x = rect.left() + int(i * rect.width() / n)
            if i:
                p.setPen(QPen(QColor('#cbd6aa'), 1, Qt.PenStyle.DashLine))
                p.drawLine(x, rect.top(), x, rect.bottom())
            sec = r.time[int(i * len(r.time) / n)]
            p.setPen(QColor('#71816e'))
            p.drawText(x + 4, rect.bottom() + 22, f'{int(sec)//60}:{int(sec)%60:02d} 起 · 抽样 {i+1}')
        p.drawText(rect.right() - 100, rect.bottom() + 38, '−110 → −30 dBFS')


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Mio 音乐修复室')
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets' / 'mio.png'
        self.setWindowIcon(QIcon(str(icon)))
        self.resize(1280, 880)
        self.setMinimumSize(1060, 760)
        self.setAcceptDrops(True)
        self.tracks = []
        self.analyses = {}
        self.pending_cover = None
        self.busy = False
        self.last_record = None
        self.drafts = {}
        self.selected_path = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(.6)
        self.player.setAudioOutput(self.output)
        self.player.errorOccurred.connect(lambda e, msg: self.statusBar().showMessage('试听不可用：' + msg))
        self.player.playbackStateChanged.connect(lambda state: self.play.setText('暂停试听' if state == QMediaPlayer.PlaybackState.PlayingState else '▷ 试听'))
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(238)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 30, 22, 22)
        side.addWidget(label('mio', 'brand'))
        side.addWidget(label('音乐修复室  /  MUSIC ATELIER', 'eyebrow'))
        side.addSpacing(28)
        side.addWidget(button('＋  导入音乐', self.import_files, True))
        side.addWidget(button('导入文件夹', self.import_folder))
        side.addSpacing(22)
        self.count = label('我的工作台  ·  0', 'muted')
        side.addWidget(self.count)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.select_track)
        side.addWidget(self.list, 1)
        side.addWidget(button('移出工作台', self.remove_track))
        side.addSpacing(14)
        side.addWidget(label('声音留在本地\n联网仅查询歌曲标签', 'muted'))
        side.addWidget(button('关于与使用说明', self.about))
        outer.addWidget(sidebar)

        self.main = QWidget()
        layout = QVBoxLayout(self.main)
        layout.setContentsMargins(34, 28, 34, 24)
        layout.setSpacing(15)
        top = QHBoxLayout()
        top.addWidget(label('YOUR MUSIC, WHOLE AGAIN', 'eyebrow'))
        top.addStretch()
        top.addWidget(label('●  本地优先   /   v1.0', 'muted'))
        layout.addLayout(top)
        layout.addWidget(label('让每一首歌，完整如初。', 'heading'))
        layout.addWidget(label('看见音质 · 找回歌词 · 补全封面', 'muted'))

        card = QFrame()
        card.setObjectName('card')
        hero = QHBoxLayout(card)
        hero.setContentsMargins(20, 20, 20, 20)
        self.art = QLabel('♪')
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setFixedSize(108, 108)
        self.art.setStyleSheet('background:#e7edde;color:#728862;border-radius:12px;font-size:46px;')
        hero.addWidget(self.art)
        meta = QVBoxLayout()
        self.track_title = label('把喜欢的音乐，带进来。')
        self.track_title.setStyleSheet('font-size:21px;font-weight:600;')
        self.track_sub = label('拖放音频或文件夹到这里，开始整理你的收藏。', 'muted')
        self.tech = label('FLAC / MP3 / M4A / WAV / OGG / OPUS / AIFF', 'muted')
        meta.addWidget(self.track_title)
        meta.addWidget(self.track_sub)
        meta.addWidget(self.tech)
        hero.addLayout(meta, 1)
        self.play = button('▷ 试听', self.toggle_play)
        hero.addWidget(self.play)
        layout.addWidget(card)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.analysis_page(), '01  音质透视')
        self.tabs.addTab(self.lyrics_page(), '02  歌词与罗马音')
        self.tabs.addTab(self.cover_page(), '03  专辑封面')
        self.tabs.addTab(self.history_page(), '04  写入与记录')
        self.tabs.currentChanged.connect(self.animate_page)
        layout.addWidget(self.tabs, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = label('准备就绪 · 原文件只会在你点击「嵌入并保存」后修改。', 'muted')
        layout.addWidget(self.status)
        outer.addWidget(self.main, 1)
        self.statusBar().showMessage('欢迎来到 Mio')
        self.enable_track(False)

    def analysis_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 14, 0, 0)
        row = QHBoxLayout()
        self.verdict = label('等待一首好音乐')
        self.verdict.setStyleSheet('font-size:20px;font-weight:600;')
        row.addWidget(self.verdict, 1)
        self.analyze_btn = button('分析频谱', self.run_analysis, True)
        row.addWidget(button('导出报告', self.export_report))
        row.addWidget(self.analyze_btn)
        box.addLayout(row)
        self.spectrum = Spectrum()
        box.addWidget(self.spectrum, 1)
        self.evidence = label('原始采样率 STFT · 最多 3 段 × 12 秒 · 不进行音频重编码', 'muted')
        box.addWidget(self.evidence)
        self.explanation = label('频谱可以揭示可疑的高频截止，但无法单独证明音源出处。所有结论都会附上依据。')
        box.addWidget(self.explanation)
        return page

    def lyrics_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 14, 0, 0)
        row = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText('搜索用曲名')
        self.artist_edit = QLineEdit()
        self.artist_edit.setPlaceholderText('搜索用歌手')
        row.addWidget(self.title_edit, 1)
        row.addWidget(self.artist_edit, 1)
        self.search_lyrics_btn = button('查找歌词', self.search_lyrics, True)
        row.addWidget(self.search_lyrics_btn)
        box.addLayout(row)
        self.candidates = QComboBox()
        self.candidates.addItem('选择匹配版本 · 来源 LRCLIB')
        self.candidates.currentIndexChanged.connect(self.choose_lyrics)
        box.addWidget(self.candidates)
        split = QSplitter()
        self.lyrics = QTextEdit()
        self.lyrics.setPlaceholderText('在线匹配后在此预览、校对歌词。\n也可以粘贴歌词或导入本地 .lrc / .txt。')
        self.romaji = QTextEdit()
        self.romaji.setPlaceholderText('日语原文 + Hepburn 罗马音\n\n自动读音可能有歧义，生成后可人工校对。')
        split.addWidget(self.lyrics)
        split.addWidget(self.romaji)
        box.addWidget(split, 1)
        self.lyrics_source = label('尚未选择在线来源。搜索字段仅用于匹配，不会改写歌曲基本标签。', 'muted')
        self.lyrics_source.setOpenExternalLinks(True)
        box.addWidget(self.lyrics_source)
        row = QHBoxLayout()
        row.addWidget(button('导入 LRC', self.load_lrc))
        row.addWidget(button('导出当前歌词', self.export_lrc))
        row.addStretch()
        self.roma_btn = button('生成日语罗马音', self.make_romaji)
        row.addWidget(self.roma_btn)
        box.addLayout(row)
        self.lyrics.textChanged.connect(self.invalidate_romaji)
        return page

    def cover_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 14, 0, 0)
        row = QHBoxLayout()
        self.album_edit = QLineEdit()
        self.album_edit.setPlaceholderText('专辑名称（在歌词页填写歌手）')
        row.addWidget(self.album_edit)
        self.search_cover_btn = button('查找封面', self.search_cover, True)
        row.addWidget(self.search_cover_btn)
        box.addLayout(row)
        self.cover_candidates = QComboBox()
        self.cover_candidates.addItem('发行版本 · 来源 MusicBrainz / Cover Art Archive')
        box.addWidget(self.cover_candidates)
        row = QHBoxLayout()
        self.cover_preview = QLabel('♪')
        self.cover_preview.setFixedSize(240, 240)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setStyleSheet('background:#e5eadf;border-radius:14px;font-size:64px;color:#8a9b80;')
        row.addWidget(self.cover_preview)
        info = QVBoxLayout()
        self.cover_info = label('先确认专辑和发行版本，再预览封面。\n已有内嵌封面会保留。')
        self.cover_info.setOpenExternalLinks(True)
        info.addWidget(self.cover_info)
        self.download_btn = button('预览所选发行版封面', self.fetch_cover)
        info.addWidget(self.download_btn)
        info.addWidget(button('选择本地封面', self.local_cover))
        info.addStretch()
        row.addLayout(info, 1)
        box.addLayout(row)
        box.addStretch()
        box.addWidget(label('封面规范：JPEG / PNG / WebP · 最大 12 MB · 写入时转为最长边 1600 px JPEG', 'muted'))
        return page

    def history_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 14, 0, 0)
        box.addWidget(label('每一次整理，都可以安心回溯。'))
        self.write_lyrics = QCheckBox('嵌入当前原文歌词（会替换已有歌词）')
        self.write_lyrics.setChecked(True)
        self.write_romaji = QCheckBox('同时保存罗马音到独立自定义标签（保留原文歌词）')
        self.write_romaji.setChecked(True)
        self.write_cover = QCheckBox('补全缺失封面（保留已有封面）')
        self.write_cover.setChecked(True)
        for w in (self.write_lyrics, self.write_romaji, self.write_cover):
            box.addWidget(w)
        box.addWidget(label('先预览歌词与封面，再保存。程序会校验临时文件、建立 SHA-256 备份后原子替换原件，不重新编码音频。WAV / OGG / OPUS / AIFF 暂只分析，可导出歌词。', 'muted'))
        row = QHBoxLayout()
        self.save_btn = button('嵌入并保存', self.save, True)
        self.undo_btn = button('撤销最近一次写入', self.undo)
        row.addWidget(self.save_btn)
        row.addWidget(self.undo_btn)
        row.addWidget(button('打开备份目录', self.open_backups))
        row.addWidget(button('查看持久记录', self.load_history))
        box.addLayout(row)
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setPlaceholderText('写入日志与来源将显示在这里。\n持久记录保存在音乐目录的 .mio/history.jsonl。')
        box.addWidget(self.history, 1)
        return page

    def current(self):
        i = self.list.currentRow()
        return self.tracks[i] if 0 <= i < len(self.tracks) else None

    def enable_track(self, enabled):
        self.tabs.setEnabled(enabled)
        self.play.setEnabled(enabled)

    def job(self, title, fn, success):
        if self.busy:
            return
        self.busy = True
        self.centralWidget().setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText(title)
        job = Job(fn)
        self.active_job = job
        def finish():
            self.busy = False
            self.centralWidget().setEnabled(True)
            self.progress.hide()
            self.enable_track(self.current() is not None)
        def done(value):
            finish()
            try:
                success(value)
            except Exception as e:
                self.error(str(e))
        def fail(message):
            finish()
            self.error(message)
        job.signals.done.connect(done)
        job.signals.failed.connect(fail)
        self.pool.start(job)

    def error(self, message):
        self.status.setText('操作未完成 · 可重试')
        self.history.append('错误：' + message)
        QMessageBox.warning(self, 'Mio · 操作提示', message)

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择音乐', '',
            '音乐 (*.flac *.mp3 *.m4a *.wav *.ogg *.opus *.aiff *.aif)')
        self.add_paths(paths)

    def import_folder(self):
        path = QFileDialog.getExistingDirectory(self, '选择音乐文件夹')
        if path:
            self.add_paths([path])

    def add_paths(self, paths):
        if self.busy or not paths:
            return
        known = {t.path.casefold() for t in self.tracks}
        def load():
            found, errors = [], []
            for path in paths:
                p = Path(path)
                files = p.rglob('*') if p.is_dir() else [p]
                for f in files:
                    if '.mio' in f.parts or f.suffix.lower() not in SUPPORTED:
                        continue
                    key = str(f.resolve()).casefold()
                    if key in known:
                        continue
                    known.add(key)
                    try:
                        found.append(read_track(str(f)))
                    except Exception as e:
                        errors.append(f'{f.name}: {e}')
            return found, errors
        def loaded(result):
            tracks, errors = result
            for t in tracks:
                self.tracks.append(t)
                item = QListWidgetItem(t.title + '\n' + (t.artist or '未知歌手'))
                item.setToolTip(t.path)
                self.list.addItem(item)
            self.count.setText(f'我的工作台  ·  {len(self.tracks)}')
            if self.current() is None and self.tracks:
                self.list.setCurrentRow(0)
            self.status.setText(f'已导入 {len(tracks)} 首 · 跳过 {len(errors)} 个不可读文件')
            for err in errors:
                self.history.append(err)
        self.job('正在读取音乐标签…', load, loaded)

    def remove_track(self):
        i = self.list.currentRow()
        if i < 0:
            return
        self.player.stop()
        self.drafts.pop(self.tracks[i].path, None)
        self.selected_path = None
        self.list.blockSignals(True)
        self.tracks.pop(i)
        self.list.takeItem(i)
        self.list.blockSignals(False)
        self.count.setText(f'我的工作台  ·  {len(self.tracks)}')
        self.select_track(self.list.currentRow())

    def select_track(self, index):
        self.player.stop()
        if self.selected_path:
            self.drafts[self.selected_path] = {
                'lyrics': self.lyrics.toPlainText(), 'romaji': self.romaji.toPlainText(),
                'title': self.title_edit.text(), 'artist': self.artist_edit.text(),
                'album': self.album_edit.text(), 'cover': self.pending_cover,
                'source': self.lyrics_source.text(), 'cover_info': self.cover_info.text()}
        self.pending_cover = None
        self.candidates.blockSignals(True)
        self.candidates.clear()
        self.candidates.addItem('选择匹配版本 · 来源 LRCLIB')
        self.candidates.blockSignals(False)
        self.cover_candidates.clear()
        self.cover_candidates.addItem('选择发行版本 · 来源 MusicBrainz')
        t = self.current()
        self.selected_path = t.path if t else None
        self.enable_track(t is not None)
        if not t:
            self.track_title.setText('把喜欢的音乐，带进来。')
            self.track_sub.setText('拖放音频或文件夹到这里，开始整理你的收藏。')
            self.tech.setText('FLAC / MP3 / M4A / WAV / OGG / OPUS / AIFF')
            self.show_art(self.art, b'')
            return
        self.track_title.setText(t.title)
        self.track_sub.setText(f'{t.artist or "未知歌手"}  /  {t.album or "未知专辑"}')
        self.tech.setText(f'{Path(t.path).suffix[1:].upper()}   ·   {t.sample_rate/1000:g} kHz   ·   '
                          f'{str(t.bits)+" bit" if t.bits else str(round(t.bitrate/1000))+" kbps"}   ·   '
                          f'{int(t.duration)//60}:{int(t.duration)%60:02d}   ·   {t.channels} 声道')
        self.title_edit.setText(t.title)
        self.artist_edit.setText(t.artist)
        self.album_edit.setText(t.album)
        self.lyrics.setPlainText(t.lyrics)
        self.romaji.clear()
        self.show_art(self.art, t.cover)
        self.show_art(self.cover_preview, t.cover)
        self.cover_info.setText('已有内嵌封面 · 自动保留' if t.cover else '尚无内嵌封面 · 可在线匹配或选择本地图片')
        self.lyrics_source.setText('当前来自本地文件' if t.lyrics else '尚无歌词 · 可以联网匹配或导入本地歌词')
        draft = self.drafts.get(t.path)
        if draft:
            self.lyrics.setPlainText(draft['lyrics'])
            self.romaji.setPlainText(draft['romaji'])
            self.title_edit.setText(draft['title'])
            self.artist_edit.setText(draft['artist'])
            self.album_edit.setText(draft['album'])
            self.pending_cover = draft['cover']
            self.lyrics_source.setText(draft['source'])
            self.cover_info.setText(draft['cover_info'])
            self.show_art(self.cover_preview, self.pending_cover or t.cover)
        self.show_analysis(self.analyses.get(t.path))
        self.player.setSource(QUrl.fromLocalFile(t.path))
        self.save_btn.setEnabled(Path(t.path).suffix.lower() in WRITABLE)
        self.undo_btn.setEnabled(self.last_record is not None)
        self.animate_page()

    def show_art(self, widget, data):
        pix = QPixmap()
        if data and pix.loadFromData(data):
            widget.setPixmap(pix.scaled(widget.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
        else:
            widget.setPixmap(QPixmap())
            widget.setText('♪')

    def edited_track(self):
        t = self.current()
        if not self.title_edit.text().strip():
            raise ValueError('请填写搜索曲名')
        return replace(t, title=self.title_edit.text().strip(), artist=self.artist_edit.text().strip(),
                       album=self.album_edit.text().strip())

    def run_analysis(self):
        t = self.current()
        if not t:
            return
        def done(r):
            self.analyses[t.path] = r
            self.show_analysis(r)
            self.status.setText('分析完成 · 结论基于抽样频谱，不代表音源认证')
        self.job('正在本地解码并分析频谱…', lambda: analyze(t), done)

    def show_analysis(self, r):
        self.spectrum.set_result(r)
        self.verdict.setText(r.verdict if r else '等待分析 · 让声音自己说话')
        self.explanation.setText(r.detail if r else '频谱可以揭示可疑的高频截止，但无法单独证明音源出处。')
        self.evidence.setText(f'估计有效带宽 {r.cutoff/1000:.1f} kHz  ·  峰值 {r.peak_db:.1f} dBFS  ·  {r.segments} 个抽样窗口' if r else '原始采样率 STFT · 最多 3 段 × 12 秒 · 不进行音频重编码')

    def export_report(self):
        t = self.current()
        r = self.analyses.get(t.path) if t else None
        if not r:
            return self.error('请先分析当前音乐')
        path, _ = QFileDialog.getSaveFileName(self, '导出检测报告', str(Path(t.path).with_suffix('.mio.json')), 'JSON (*.json)')
        if path:
            try:
                report = {'file': Path(t.path).name, 'sample_rate': t.sample_rate,
                    'duration': t.duration, 'verdict': r.verdict, 'detail': r.detail,
                    'estimated_bandwidth_hz': r.cutoff, 'peak_dbfs': r.peak_db,
                    'sample_windows': r.segments, 'method': 'Native-rate STFT, 3 x up to 12 seconds; heuristic only',
                    'frequency_hz': r.frequency.tolist(), 'average_dbfs': r.profile.tolist()}
                Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                self.status.setText('检测报告已导出')
            except Exception as e:
                self.error(str(e))

    def search_lyrics(self):
        try:
            t = self.edited_track()
        except ValueError as e:
            return self.error(str(e))
        def done(rows):
            self.candidates.blockSignals(True)
            self.candidates.clear()
            self.candidates.addItem(f'{len(rows)} 个候选 · 请核对歌手、时长和版本后选择')
            for r in rows:
                self.candidates.addItem(f"{r['match']}% · {r.get('artistName')} — {r.get('trackName')} / {r.get('albumName')} · {r.get('duration')}s" + (' · 纯音乐' if r.get('instrumental') else ''), r)
            self.candidates.blockSignals(False)
            self.status.setText('歌词搜索完成 · 相似度仅供参考，请手动选择匹配版本')
        self.job('正在查询 LRCLIB…', lambda: find_lyrics(t), done)

    def choose_lyrics(self, index):
        r = self.candidates.currentData()
        if not r:
            return
        if r.get('instrumental'):
            self.lyrics_source.setText('此候选标记为纯音乐，未修改当前歌词。')
            return
        self.lyrics.setPlainText(r.get('syncedLyrics') or r.get('plainLyrics') or '')
        self.lyrics_source.setText(f'来源：<a href="https://lrclib.net/api/get/{r["id"]}">LRCLIB #{r["id"]}</a> · 请校对版本及时间轴')

    def invalidate_romaji(self):
        self.romaji.clear()

    def make_romaji(self):
        text = self.lyrics.toPlainText()
        if not text.strip():
            return self.error('请先匹配或输入歌词')
        self.job('正在离线生成日语罗马音…', lambda: romanize(text),
                 lambda r: (self.romaji.setPlainText(r), self.status.setText('罗马音已生成 · 保留原时间戳，可手动校正特殊读音')))

    def search_cover(self):
        try:
            t = self.edited_track()
        except ValueError as e:
            return self.error(str(e))
        def done(rows):
            self.cover_candidates.clear()
            self.cover_candidates.addItem(f'{len(rows)} 个发行版本 · 选择后下载预览')
            for r in rows:
                self.cover_candidates.addItem(f"{r['score']} · {r['title']} / {r['artist']} / {r['date']} {r['country']}", r)
            self.status.setText('发行版查询完成 · 同名专辑可能有不同封面')
        self.job('正在查询 MusicBrainz…', lambda: find_covers(t), done)

    def fetch_cover(self):
        r = self.cover_candidates.currentData()
        if not r:
            return self.error('请先选择发行版本')
        def done(data):
            self.pending_cover = data
            self.show_art(self.cover_preview, data)
            self.cover_info.setText(f'待写入封面 · {len(data)//1024} KB<br><a href="{r["url"]}">查看 MusicBrainz 发行版与来源</a><br>若已有封面，写入时仍会保留原封面。')
            self.status.setText('封面已准备 · 尚未修改音乐文件')
        self.job('正在从 Cover Art Archive 下载封面…', lambda: download_cover(r['id']), done)

    def local_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择封面', '', '封面 (*.jpg *.jpeg *.png *.webp)')
        if path:
            try:
                if Path(path).stat().st_size > 12 * 1024 * 1024:
                    raise ValueError('封面超过 12 MB')
                self.pending_cover = image_bytes(Path(path).read_bytes())
                self.show_art(self.cover_preview, self.pending_cover)
                self.cover_info.setText('待写入本地封面：' + Path(path).name)
            except Exception as e:
                self.error(str(e))

    def load_lrc(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入歌词', '', '歌词 (*.lrc *.txt)')
        if path:
            try:
                text = Path(path).read_text(encoding='utf-8-sig')
                self.lyrics.setPlainText(text)
                self.lyrics_source.setText('本地导入：' + Path(path).name)
            except Exception as e:
                self.error('请使用 UTF-8 编码歌词：' + str(e))

    def export_lrc(self):
        text = self.romaji.toPlainText() or self.lyrics.toPlainText()
        if not text.strip():
            return self.error('暂无可导出的歌词')
        t = self.current()
        default = str(Path(t.path).with_suffix('.mio.lrc')) if t else 'lyrics.lrc'
        path, _ = QFileDialog.getSaveFileName(self, '导出歌词（优先导出原文＋罗马音预览）', default, 'LRC (*.lrc);;Text (*.txt)')
        if path:
            try:
                Path(path).write_text(text, encoding='utf-8')
                self.status.setText('歌词已导出：' + path)
            except Exception as e:
                self.error(str(e))

    def save(self):
        t = self.current()
        if not t:
            return
        lyrics = self.lyrics.toPlainText() if self.write_lyrics.isChecked() else None
        cover = self.pending_cover if self.write_cover.isChecked() and not t.cover else None
        roma = self.romaji.toPlainText() if self.write_romaji.isChecked() else ''
        provenance = {'lyrics': self.lyrics_source.text() if lyrics is not None else '',
                      'cover': self.cover_info.text() if cover else ''}
        if lyrics is not None and not lyrics.strip():
            return self.error('当前歌词为空。为避免清空已有歌词，请取消歌词嵌入选项或先填写歌词。')
        if lyrics is None and cover is None:
            return self.error('没有待写入内容：请准备歌词或缺失封面')
        self.player.stop()
        self.player.setSource(QUrl())
        index = self.list.currentRow()
        def done(record):
            self.last_record = record
            self.drafts.pop(t.path, None)
            self.selected_path = None
            self.tracks[index] = read_track(t.path)
            self.select_track(index)
            self.history.append(f"✓ {record['time']}  {Path(t.path).name}\n备份：{record['backup']}\nSHA-256：{record['after_sha256']}")
            if record.get('warning'):
                self.history.append(record['warning'])
            self.status.setText('已安全嵌入 · 原文件备份完成，可撤销最近一次写入')
        self.job('正在验证、备份并安全嵌入标签…', lambda: write_tags(t, lyrics, cover, roma, provenance), done)

    def undo(self):
        if not self.last_record:
            return self.error('本次会话暂无可撤销的写入；历史备份可在 .mio/backups 手动找回')
        record = self.last_record
        self.player.stop()
        self.player.setSource(QUrl())
        def done(_):
            self.last_record = None
            self.drafts.pop(record['path'], None)
            self.selected_path = None
            for i, t in enumerate(self.tracks):
                if t.path == record['path']:
                    self.tracks[i] = read_track(t.path)
            self.select_track(self.list.currentRow())
            self.history.append('已撤销：' + record['path'])
            self.status.setText('原文件已从验证过的备份恢复')
        self.job('正在验证备份并恢复…', lambda: restore(record), done)

    def open_backups(self):
        t = self.current()
        if t:
            path = Path(t.path).parent / '.mio'
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            else:
                self.status.setText('还未进行写入，备份将在首次保存时创建')

    def load_history(self):
        t = self.current()
        if not t:
            return
        path = Path(t.path).parent / '.mio' / 'history.jsonl'
        if not path.exists():
            self.status.setText('此音乐目录暂无写入记录')
            return
        try:
            lines = path.read_text(encoding='utf-8').splitlines()[-200:]
            self.history.setPlainText('\n\n'.join(json.dumps(json.loads(line), ensure_ascii=False, indent=2) for line in lines))
            self.status.setText('已载入当前音乐目录最近 200 条写入记录')
        except Exception as e:
            self.error(str(e))

    def toggle_play(self):
        if not self.current():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def animate_page(self, *_):
        page = self.tabs.currentWidget()
        if not page:
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        self.animation = QPropertyAnimation(effect, b'opacity', self)
        self.animation.setDuration(230)
        self.animation.setStartValue(.25)
        self.animation.setEndValue(1)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])

    def closeEvent(self, event):
        if self.busy:
            self.status.setText('正在完成当前任务，请稍后关闭，以保证文件操作完整。')
            event.ignore()
            return
        self.player.stop()
        event.accept()

    def about(self):
        QMessageBox.information(self, '关于 Mio',
            'Mio 音乐修复室 1.0\n\n'
            '1. 导入音乐，点击分析查看抽样频谱。\n'
            '2. 核对搜索曲名、歌手，选择歌词版本；日语可离线生成罗马音。\n'
            '3. 输入专辑，选择发行版并预览封面，或选择本地图片。\n'
            '4. 在写入页选择内容，嵌入并保存。原件自动备份，可撤销。\n\n'
            '频谱不能证明音源出处；自动读音可能需要人工校对。\n'
            '在线服务可能缺少内容或暂时不可用，可使用本地导入。\n'
            '音频不上传；查询发送曲名/歌手/专辑。数据缓存 7 天。\n\n'
            '源码与完整说明：https://github.com/Akumy-01/mio-music\n'
            'GNU GPL v3 · Qt / Mutagen / pykakasi / FFmpeg')


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Mio Music')
    app.setOrganizationName('MioMusic')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if len(sys.argv) > 1:
        QTimer.singleShot(100, lambda: window.add_paths(sys.argv[1:]))
    sys.exit(app.exec())
