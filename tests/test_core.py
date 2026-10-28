from io import BytesIO
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
from PIL import Image
import pytest
from scipy.io.wavfile import write as wavwrite

from mio.core import (read_track, analyze, decode_segment, write_tags, restore,
                      digest, romanize, image_bytes)
from mio.providers import similarity, quote_query


@pytest.fixture
def music(tmp_path):
    sr = 44100
    rng = np.random.default_rng(42)
    samples = (rng.normal(0, .08, sr * 4) * 32767).astype(np.int16)
    wav = tmp_path / '测试 原声.wav'
    wavwrite(wav, sr, samples)
    def make(ext, codec):
        target = tmp_path / ('测试 原声' + ext)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-i', str(wav),
                        '-c:a', codec, str(target)], check=True, capture_output=True)
        return target
    return wav, make


def cover(color='green'):
    b = BytesIO()
    Image.new('RGB', (100, 100), color).save(b, 'PNG')
    return b.getvalue()


@pytest.mark.parametrize('ext,codec', [('.flac', 'flac'), ('.mp3', 'libmp3lame'),
                                      ('.m4a', 'alac'), ('.m4a', 'aac')])
def test_roundtrip_preserves_audio_and_restores(music, ext, codec):
    _, make = music
    p = make(ext, codec)
    t = read_track(str(p))
    before = digest(p)
    pcm = decode_segment(str(p), 0, 4, t.sample_rate).copy()
    lyric = '[00:01.00]こんにちは 世界\n[00:02.00]音楽'
    record = write_tags(t, lyric, cover(), romanize(lyric))
    updated = read_track(str(p))
    assert updated.lyrics == lyric
    assert updated.cover
    if codec == 'aac':
        assert analyze(updated).verdict == '有损编码'
    assert digest(record['backup']) == before
    np.testing.assert_array_equal(pcm, decode_segment(str(p), 0, 4, t.sample_rate))
    old_cover = updated.cover
    record2 = write_tags(updated, '新しい歌詞', cover('red'))
    assert read_track(str(p)).cover == old_cover
    restore(record2)
    assert read_track(str(p)).lyrics == lyric
    restore(record)
    assert digest(p) == before


def test_restore_refuses_external_changes(music):
    _, make = music
    p = make('.flac', 'flac')
    record = write_tags(read_track(str(p)), 'hello', None)
    with open(p, 'ab') as f:
        f.write(b'external-change')
    before = digest(p)
    with pytest.raises(ValueError, match='已变化'):
        restore(record)
    assert digest(p) == before


def test_bad_cover_never_modifies_original(music):
    _, make = music
    p = make('.flac', 'flac')
    before = digest(p)
    with pytest.raises(Exception):
        write_tags(read_track(str(p)), 'hello', b'not an image')
    assert digest(p) == before
    assert not list(p.parent.glob('.mio-*'))


def test_analysis_fullband_and_lossy(music):
    wav, make = music
    r = analyze(read_track(str(wav)))
    assert r.cutoff > 21000
    assert r.verdict == '未见明显转码迹象'
    assert r.segments == 1
    assert np.isfinite(r.db).all()
    mp3 = make('.mp3', 'libmp3lame')
    assert analyze(read_track(str(mp3))).verdict == '有损编码'


def test_silence_is_inconclusive(tmp_path):
    p = tmp_path / 'silence.wav'
    wavwrite(p, 44100, np.zeros(44100, dtype=np.int16))
    assert analyze(read_track(str(p))).verdict == '证据不足'


def test_suspected_lowpass(tmp_path):
    from scipy.signal import butter, sosfilt
    p = tmp_path / 'filtered.wav'
    rng = np.random.default_rng(7)
    samples = sosfilt(butter(16, 14000, fs=44100, output='sos'), rng.normal(0, .04, 44100*4))
    wavwrite(p, 44100, (samples * 32767).astype(np.int16))
    r = analyze(read_track(str(p)))
    assert r.verdict == '疑似有损转码'


def test_romaji_timestamps_and_non_japanese():
    r = romanize('[00:01.20]こんにちは\nEnglish text\n[ar:Artist]\n音楽')
    assert r.count('[00:01.20]') == 2
    assert 'konnichiha' in r
    assert r.count('English text') == 1
    assert '[ar:Artist]' in r
    assert 'ongaku' in r


def test_helpers():
    assert similarity('Hello World!', 'hello world') == 1
    assert quote_query('a" OR release:*') == '"a  OR release  "'
    assert image_bytes(cover()).startswith(b'\xff\xd8')
    normalized = image_bytes(cover())
    assert image_bytes(normalized) == normalized


@pytest.mark.parametrize('ext,codec', [('.flac', 'flac'), ('.mp3', 'libmp3lame'), ('.m4a', 'alac')])
def test_independent_romaji_and_explicit_cover_replacement(music, ext, codec):
    _, make = music
    p = make(ext, codec)
    write_tags(read_track(str(p)), 'original', cover(), 'romaji-original')
    t = read_track(str(p))
    original_cover = t.cover
    write_tags(t, 'new lyrics', None)  # None preserves the independent custom tag.
    assert read_track(str(p)).romaji == 'romaji-original'
    write_tags(read_track(str(p)), None, cover('red'), 'new romaji', replace_cover=True)
    result = read_track(str(p))
    assert result.lyrics == 'new lyrics'
    assert result.romaji == 'new romaji'
    assert result.cover != original_cover


def test_copy_does_not_touch_source_or_clobber_existing(music):
    _, make = music
    p = make('.flac', 'flac')
    before = digest(p)
    dst = p.with_name('organized.flac')
    record = write_tags(read_track(str(p)), 'copy lyrics', None, output_path=str(dst))
    assert digest(p) == before
    assert read_track(str(dst)).lyrics == 'copy lyrics'
    with pytest.raises(ValueError, match='不能覆盖'):
        write_tags(read_track(str(p)), 'other', None, output_path=str(dst))
    restore(record)
    assert not dst.exists() and digest(p) == before


def test_transient_lock_retried_and_external_modification_refused(monkeypatch, tmp_path):
    from mio import core
    src, stage = tmp_path/'src', tmp_path/'stage'
    src.write_bytes(b'original')
    stage.write_bytes(b'new')
    original_replace = core.os.replace
    calls = []
    def transient(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError('locked')
        original_replace(a, b)
    monkeypatch.setattr(core.os, 'replace', transient)
    monkeypatch.setattr(core.time, 'sleep', lambda _: None)
    core.atomic_replace(stage, src, digest(src))
    assert src.read_bytes() == b'new' and len(calls) == 3
    stage.write_bytes(b'next')
    with pytest.raises(ValueError, match='其他程序修改'):
        core.atomic_replace(stage, src, 'wrong-hash')
    assert src.read_bytes() == b'new'


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Windows handle sharing regression')
def test_actual_windows_file_lock_preserves_original_and_allows_copy(music):
    import ctypes
    from ctypes import wintypes
    _, make = music
    p = make('.flac', 'flac')
    t, before = read_track(str(p)), digest(p)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(p), 0x80000000, 1, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        with pytest.raises(PermissionError, match='另存整理副本'):
            write_tags(t, 'locked example', None)
        assert digest(p) == before
        dst = p.with_name('copy.flac')
        write_tags(t, 'copy example', None, output_path=str(dst))
        assert read_track(str(dst)).lyrics == 'copy example'
        assert digest(p) == before
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.parametrize('ext,codec', [('.flac', 'flac'), ('.mp3', 'libmp3lame')])
def test_replace_front_preserves_back_artwork(music, ext, codec):
    import mutagen
    from mutagen.flac import Picture
    from mutagen.id3 import APIC
    _, make = music
    path = make(ext, codec)
    audio = mutagen.File(path)
    if audio.tags is None:
        audio.add_tags()
    back = cover('blue')
    if ext == '.flac':
        pic = Picture()
        pic.type, pic.mime, pic.data = 4, 'image/png', back
        audio.add_picture(pic)
    else:
        audio.tags.add(APIC(encoding=3, type=4, mime='image/png', desc='back', data=back))
    audio.save()
    write_tags(read_track(str(path)), None, cover('red'), replace_cover=True)
    audio = mutagen.File(path)
    pictures = audio.pictures if ext == '.flac' else audio.tags.getall('APIC')
    assert sorted(p.type for p in pictures) == [3, 4]
    assert next(p for p in pictures if p.type == 4).data == back
