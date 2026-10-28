import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
import pytest
from mio.core import Track
from mio.write_panel import WritePanel


def test_write_plan_explicit_sources_and_preview():
    app = QApplication.instance() or QApplication([])
    p = WritePanel()
    t = Track('C:/example.flac', 'Song', lyrics='old', cover=b'old-cover', romaji='old-romaji')
    p.set_content(t, [{'key': 'netease', 'label': '网易云', 'text': 'new-original'},
                     {'key': 'roma', 'label': '双行罗马音', 'text': 'original\nromaji'}],
                  [{'key': 'new', 'label': '新封面', 'data': b'new-cover'}], 'romaji-only')
    with pytest.raises(ValueError, match='没有待写入'):
        p.plan()
    p.select_lyrics('roma')
    assert p.lyrics_preview.toPlainText() == 'original\nromaji'
    assert p.plan().lyrics == 'original\nromaji'
    p.select_cover('new')
    p.cover_mode.setCurrentIndex(1)  # Missing-only preserves an existing cover.
    assert p.plan().cover is None
    p.cover_mode.setCurrentIndex(2)
    assert p.plan().cover == b'new-cover' and p.plan().replace_cover
    p.romaji_check.setChecked(True)
    assert p.plan().romaji == 'romaji-only'
    p.output_mode.setCurrentIndex(1)
    assert p.plan().copy
    p.close()


def test_refresh_preserves_selected_version_and_empty_content_blocks_save():
    app = QApplication.instance() or QApplication([])
    p = WritePanel()
    t = Track('C:/example.flac', 'Song')
    rows = [{'key': 'editor', 'label': '当前编辑', 'text': 'edited'},
            {'key': 'saved', 'label': '保存版本', 'text': 'snapshot'}]
    p.set_content(t, rows, [], '')
    p.select_lyrics('saved')
    rows[0]['text'] = 'changed edit'
    p.set_content(t, rows, [], '')
    assert p.plan().lyrics == 'snapshot'
    p.select_lyrics('editor')
    rows[0]['text'] = ''
    p.set_content(t, rows, [], '')
    assert not p.save_button.isEnabled()
    with pytest.raises(ValueError, match='所选歌词为空'):
        p.plan()
    p.close()
