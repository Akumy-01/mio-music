"""Reviewable write plan, independent of the application's network providers."""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox,
    QTextEdit, QCheckBox, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QScrollArea)


@dataclass
class WritePlan:
    lyrics: str | None
    cover: bytes | None
    romaji: str | None
    replace_cover: bool
    copy: bool
    sources: dict


class WritePanel(QWidget):
    saveRequested = Signal()
    undoRequested = Signal()
    backupsRequested = Signal()
    reloadRequested = Signal()

    def __init__(self):
        super().__init__()
        self.track = None
        self.lyric_options = []
        self.cover_options = []
        self.romaji_text = ''
        self.records = []
        self.loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 8, 0)
        box.setSpacing(10)
        self.target = QLabel('选择一首歌，确认要写入的内容')
        self.target.setWordWrap(True)
        self.target.setObjectName('muted')
        box.addWidget(self.target)
        cards = QHBoxLayout()
        def card(title):
            w = QFrame()
            w.setObjectName('card')
            layout = QVBoxLayout(w)
            layout.setContentsMargins(14, 12, 14, 12)
            heading = QLabel(title)
            heading.setStyleSheet('font-weight:600;font-size:15px;')
            layout.addWidget(heading)
            cards.addWidget(w, 1)
            return layout
        lyrics_card = card('歌词 · 选择具体内容')
        self.lyrics_choice = QComboBox()
        lyrics_card.addWidget(self.lyrics_choice)
        self.lyrics_preview = QTextEdit()
        self.lyrics_preview.setReadOnly(True)
        self.lyrics_preview.setMinimumHeight(72)
        self.lyrics_preview.setMaximumHeight(112)
        lyrics_card.addWidget(self.lyrics_preview)
        self.romaji_check = QCheckBox('额外更新罗马音自定义标签')
        self.romaji_check.setToolTip('与标准歌词字段独立；未勾选时保留原有自定义标签。')
        lyrics_card.addWidget(self.romaji_check)
        cover_card = card('封面 · 保留、补全或替换')
        self.cover_mode = QComboBox()
        for text, key in [('保留现有封面', 'keep'), ('仅在缺失时补全', 'missing'), ('替换为所选封面', 'replace')]:
            self.cover_mode.addItem(text, key)
        cover_card.addWidget(self.cover_mode)
        self.cover_choice = QComboBox()
        cover_card.addWidget(self.cover_choice)
        cover_row = QHBoxLayout()
        self.cover_preview = QLabel('♪')
        self.cover_preview.setFixedSize(80, 80)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setStyleSheet('background:#e7edde;border-radius:8px;color:#728862;font-size:30px;')
        cover_row.addWidget(self.cover_preview)
        self.cover_note = QLabel('已有封面会保留')
        self.cover_note.setWordWrap(True)
        self.cover_note.setObjectName('muted')
        cover_row.addWidget(self.cover_note, 1)
        cover_card.addLayout(cover_row)
        box.addLayout(cards)
        row = QHBoxLayout()
        row.addWidget(QLabel('保存位置'))
        self.output_mode = QComboBox()
        self.output_mode.addItem('备份后更新原文件', 'original')
        self.output_mode.addItem('另存整理副本…', 'copy')
        row.addWidget(self.output_mode, 1)
        self.summary = QLabel('没有待写入的更改')
        self.summary.setWordWrap(True)
        row.addWidget(self.summary, 2)
        box.addLayout(row)
        buttons = QHBoxLayout()
        self.save_button = QPushButton('确认内容并保存')
        self.save_button.setObjectName('primary')
        self.save_button.clicked.connect(self.saveRequested)
        buttons.addWidget(self.save_button, 2)
        self.undo_button = QPushButton('撤销所选记录')
        self.undo_button.clicked.connect(self.undoRequested)
        buttons.addWidget(self.undo_button)
        for text, signal in [('备份目录', self.backupsRequested), ('刷新记录', self.reloadRequested)]:
            b = QPushButton(text)
            b.clicked.connect(signal)
            buttons.addWidget(b)
        box.addLayout(buttons)
        tabs = QTabWidget()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['时间', '操作', '写入内容', '文件'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(95)
        self.table.itemSelectionChanged.connect(self.refresh)
        tabs.addTab(self.table, '文件保存记录')
        self.diagnostics = QTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlaceholderText('查询状态和错误详情；不会混入文件保存记录。')
        tabs.addTab(self.diagnostics, '运行诊断')
        tabs.setMinimumHeight(145)
        box.addWidget(tabs)
        self.record_note = QLabel('自动校验并保留完整备份；撤销前会检查文件是否被其他程序修改。')
        self.record_note.setWordWrap(True)
        self.record_note.setObjectName('muted')
        box.addWidget(self.record_note)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        for combo in (self.lyrics_choice, self.cover_choice, self.cover_mode, self.output_mode):
            combo.currentIndexChanged.connect(self.refresh)
        self.romaji_check.toggled.connect(self.refresh)
        for combo in (self.lyrics_choice, self.cover_choice):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(16)
        self.refresh()

    def state(self):
        return {'lyrics': self.lyrics_choice.currentData(), 'cover': self.cover_choice.currentData(),
                'cover_mode': self.cover_mode.currentData(), 'output': self.output_mode.currentData(),
                'romaji': self.romaji_check.isChecked()}

    def restore_state(self, state):
        for widget, key in [(self.lyrics_choice, 'lyrics'), (self.cover_choice, 'cover'),
                            (self.cover_mode, 'cover_mode'), (self.output_mode, 'output')]:
            i = widget.findData(state.get(key))
            if i >= 0:
                widget.setCurrentIndex(i)
        self.romaji_check.setChecked(bool(state.get('romaji')))
        self.refresh()

    def set_content(self, track, lyrics, covers, romaji):
        old = self.state()
        same = self.track and track and self.track.path == track.path
        self.loading = True
        self.track, self.lyric_options, self.cover_options, self.romaji_text = track, lyrics, covers, romaji
        self.lyrics_choice.clear()
        self.lyrics_choice.addItem('保留文件里的歌词', 'keep')
        for r in lyrics:
            self.lyrics_choice.addItem(r['label'], r['key'])
        self.cover_choice.clear()
        self.cover_choice.addItem('尚未准备新封面', None)
        for r in covers:
            self.cover_choice.addItem(r['label'], r['key'])
        if same:
            self.restore_state(old)
        else:
            self.cover_mode.setCurrentIndex(0)
            self.output_mode.setCurrentIndex(0)
            self.romaji_check.setChecked(False)
        self.loading = False
        self.target.setText(Path(track.path).name + '  ·  保存前请核对下面的实际内容' if track else '选择一首歌，确认要写入的内容')
        self.target.setToolTip(track.path if track else '')
        self.refresh()

    def select_lyrics(self, key):
        i = self.lyrics_choice.findData(key)
        if i >= 0:
            self.lyrics_choice.setCurrentIndex(i)

    def select_cover(self, key):
        self.cover_choice.setCurrentIndex(self.cover_choice.findData(key))
        if self.track and not self.track.cover:
            self.cover_mode.setCurrentIndex(1)

    def plan(self):
        t = self.track
        if not t:
            raise ValueError('请先选择音乐文件')
        lyric = next((r for r in self.lyric_options if r['key'] == self.lyrics_choice.currentData()), None)
        lyrics = lyric['text'] if lyric else None
        if lyrics is not None and not lyrics.strip():
            raise ValueError('所选歌词为空，请选择其他内容或保留文件里的歌词')
        if lyrics == t.lyrics:
            lyrics = None
        roma = self.romaji_text if self.romaji_check.isChecked() else None
        if roma is not None and not roma.strip():
            raise ValueError('暂无罗马音内容，请先生成，或取消自定义标签更新')
        if roma == t.romaji:
            roma = None
        cover = next((r for r in self.cover_options if r['key'] == self.cover_choice.currentData()), None)
        mode = self.cover_mode.currentData()
        data = cover['data'] if cover and mode != 'keep' and (mode == 'replace' or not t.cover) else None
        if mode != 'keep' and not cover and (mode == 'replace' or not t.cover):
            raise ValueError('请先在封面页准备图片，再选择要写入的封面')
        if data == t.cover:
            data = None
        if lyrics is None and data is None and roma is None:
            raise ValueError('没有待写入的更改：请选择歌词、封面或罗马音内容')
        return WritePlan(lyrics, data, roma, mode == 'replace', self.output_mode.currentData() == 'copy',
                         {'lyrics': lyric.get('source', lyric['label']) if lyric and lyrics is not None else '',
                          'cover': cover.get('source', cover['label']) if cover and data else ''})

    def refresh(self, *_):
        if self.loading:
            return
        t = self.track
        lyric = next((r for r in self.lyric_options if r['key'] == self.lyrics_choice.currentData()), None)
        self.lyrics_preview.setPlainText(lyric['text'] if lyric else (t.lyrics if t else ''))
        self.lyrics_preview.setPlaceholderText('文件中没有歌词；可选择已获取的版本或当前编辑内容。')
        cover = next((r for r in self.cover_options if r['key'] == self.cover_choice.currentData()), None)
        mode = self.cover_mode.currentData()
        use_new = cover and mode != 'keep' and (mode == 'replace' or not (t and t.cover))
        data = cover['data'] if use_new else t.cover if t else b''
        pix = QPixmap()
        if data and pix.loadFromData(data):
            self.cover_preview.setPixmap(pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.cover_preview.setPixmap(QPixmap())
            self.cover_preview.setText('♪')
        self.cover_note.setText(('将替换已有封面' if mode == 'replace' and t and t.cover else '将补全缺失封面')
                               if use_new else ('保留已有封面' if t and t.cover else '不写入封面'))
        self.cover_choice.setEnabled(mode != 'keep')
        try:
            plan = self.plan()
            changes = [name for name, active in [('歌词', plan.lyrics is not None), ('封面', plan.cover is not None), ('罗马音标签', plan.romaji is not None)] if active]
            self.summary.setText('将更新：' + '、'.join(changes))
            self.save_button.setEnabled(Path(t.path).suffix.lower() in {'.flac', '.mp3', '.m4a'})
        except ValueError as e:
            self.summary.setText(str(e))
            self.save_button.setEnabled(False)
        record = self.selected_record()
        self.undo_button.setEnabled(record is not None)
        if record:
            self.record_note.setText('备份：' + record.get('backup', '') + '\n撤销将' + ('删除这次创建且未经修改的整理副本。' if record.get('action') == 'copy' else '恢复此记录写入前的完整文件；文件已变化则拒绝覆盖。'))
        else:
            self.record_note.setText('自动校验并保留完整备份；撤销前会检查文件是否被其他程序修改。')

    def selected_record(self):
        row = self.table.currentRow()
        return self.records[row] if 0 <= row < len(self.records) else None

    def set_records(self, records):
        self.records = records
        self.table.setRowCount(len(records))
        for i, r in enumerate(records):
            changes = r.get('changes', {})
            names = '、'.join(n for n, k in [('歌词', 'lyrics'), ('封面', 'cover'), ('罗马音', 'romaji')] if changes.get(k)) or '标签'
            for j, text in enumerate([r.get('time', '').split('.')[0].replace('T', ' '), '另存副本' if r.get('action') == 'copy' else '更新原件', names, Path(r.get('path', '')).name]):
                item = QTableWidgetItem(text)
                item.setToolTip(r.get('path', ''))
                self.table.setItem(i, j, item)
        if records:
            self.table.selectRow(0)
        self.refresh()
