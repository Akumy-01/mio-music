from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import stat
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime

import imageio_ffmpeg
import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC, USLT, TXXX
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
import numpy as np
from scipy.signal import stft
from PIL import Image
from io import BytesIO

SUPPORTED = {'.flac', '.mp3', '.m4a', '.wav', '.ogg', '.opus', '.aiff', '.aif'}
WRITABLE = {'.flac', '.mp3', '.m4a'}


@dataclass
class Track:
    path: str
    title: str
    artist: str = ''
    album: str = ''
    duration: float = 0
    sample_rate: int = 0
    bits: int = 0
    bitrate: int = 0
    channels: int = 0
    cover: bytes = field(default=b'', repr=False)
    lyrics: str = ''
    romaji: str = ''


def read_track(path: str) -> Track:
    p = Path(path).resolve()
    if p.suffix.lower() not in SUPPORTED:
        raise ValueError('不支持此文件格式')
    audio = mutagen.File(p)
    if audio is None:
        raise ValueError('无法读取音频，文件可能损坏')
    easy = mutagen.File(p, easy=True)
    tags = easy or {}
    def value(key, fallback=''):
        v = tags.get(key, [fallback])
        return str(v[0]) if v else fallback
    info = audio.info
    t = Track(str(p), value('title', p.stem), value('artist'), value('album'),
              info.length, getattr(info, 'sample_rate', 0), getattr(info, 'bits_per_sample', 0),
              getattr(info, 'bitrate', 0), getattr(info, 'channels', 0))
    if isinstance(audio, FLAC):
        pics = sorted(audio.pictures, key=lambda x: x.type != 3)
        t.cover = pics[0].data if pics else b''
        t.lyrics = (audio.get('lyrics') or [''])[0]
        t.romaji = (audio.get('MIO_ROMAJI') or [''])[0]
    elif isinstance(audio.tags, ID3):
        pics = sorted(audio.tags.getall('APIC'), key=lambda p: p.type != 3)
        t.cover = pics[0].data if pics else b''
        lyrics = audio.tags.getall('USLT')
        t.lyrics = lyrics[0].text if lyrics else ''
        roma = audio.tags.getall('TXXX:MIO_ROMAJI')
        t.romaji = str(roma[0].text[0]) if roma and roma[0].text else ''
    elif isinstance(audio, MP4):
        t.cover = bytes((audio.get('covr') or [b''])[0])
        t.lyrics = (audio.get('\xa9lyr') or [''])[0]
        t.romaji = bytes((audio.get('----:com.mio:ROMAJI') or [b''])[0]).decode('utf-8', errors='replace')
    return t


@dataclass
class Analysis:
    frequency: np.ndarray
    time: np.ndarray
    db: np.ndarray
    profile: np.ndarray
    cutoff: float
    verdict: str
    detail: str
    segments: int
    peak_db: float


def decode_segment(path, start, seconds, sample_rate):
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-ss', str(start), '-i', path,
           '-t', str(seconds), '-vn', '-ac', '1', '-ar', str(sample_rate), '-f', 'f32le', 'pipe:1']
    result = subprocess.run(cmd, capture_output=True, timeout=90,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('解码失败：' + result.stderr.decode(errors='replace')[-400:])
    return np.frombuffer(result.stdout, dtype='<f4')


def analyze(track: Track) -> Analysis:
    # Three bounded, nonoverlapping windows. Native sample rate is preserved.
    sr = track.sample_rate
    if not 8000 <= sr <= 384000:
        raise ValueError('采样率不在支持范围（8–384 kHz）')
    duration = track.duration
    starts = sorted(set(round(max(0, min(duration - 12, duration * f)), 3)
                        for f in (0.08, 0.44, 0.80)))
    specs, times, peaks = [], [], []
    nfft = 4096 if sr <= 96000 else 8192
    for start in starts:
        samples = decode_segment(track.path, start, min(12, duration), sr)
        if len(samples) < nfft:
            samples = np.pad(samples, (0, max(0, nfft - len(samples))))
        peaks.append(float(np.max(np.abs(samples))))
        f, t, z = stft(samples, sr, nperseg=nfft, noverlap=nfft // 2)
        power = np.abs(z) ** 2
        # Retain at most 260 time columns per window for bounded display memory.
        step = max(1, power.shape[1] // 260)
        specs.append(power[:, ::step])
        times.append(t[::step] + start)
    power = np.concatenate(specs, axis=1)
    db = 10 * np.log10(np.maximum(power, 1e-14))
    profile = 10 * np.log10(np.maximum(np.mean(power, axis=1), 1e-14))
    # Relative floor is only a visual bandwidth estimate, not a provenance detector.
    reference = float(np.max(profile))
    active = f[profile > reference - 60]
    cutoff = float(active[-1]) if len(active) else 0.0
    lossy = Path(track.path).suffix.lower() in {'.mp3', '.ogg', '.opus'}
    if Path(track.path).suffix.lower() == '.m4a':
        lossy = getattr(mutagen.File(track.path).info, 'codec', '').lower() != 'alac'
    if max(peaks) < 0.00001:
        verdict, detail = '证据不足', '抽样接近静音，无法根据频谱判断音源。'
    elif lossy:
        verdict, detail = '有损编码', '当前编码为有损格式；封装和高码率不能恢复已经丢失的信号。'
    elif sr >= 44100 and 12000 <= cutoff < 18000:
        verdict, detail = '疑似有损转码', '高频带宽偏窄，可能来自有损转码，也可能是录音、母带或滤波所致。'
    else:
        verdict, detail = '未见明显转码迹象', '抽样频谱未显示明显的带宽异常。这不能证明原始音源是真无损。'
    return Analysis(f, np.concatenate(times), db, profile, cutoff, verdict, detail,
                    len(starts), float(20 * np.log10(max(max(peaks), 1e-14))))


def romanize(text: str) -> str:
    from pykakasi import kakasi
    converter = kakasi()
    lines = []
    japanese_text = bool(re.search(r'[\u3040-\u30ff]', text))
    for line in text.splitlines():
        stamps = ''.join(re.findall(r'\[\d+:\d+(?:\.\d+)?\]', line))
        body = re.sub(r'\[\d+:\d+(?:\.\d+)?\]', '', line)
        if re.search(r'[\u3040-\u30ff]', body) or (japanese_text and re.search(r'[\u4e00-\u9fff]', body)):
            roma = ' '.join(p['hepburn'] for p in converter.convert(body)).strip()
            lines.extend([line, stamps + roma])
        else:
            lines.append(line)
    return '\n'.join(lines)


def image_bytes(data: bytes) -> bytes:
    if len(data) > 12 * 1024 * 1024:
        raise ValueError('封面超过 12 MB')
    with Image.open(BytesIO(data)) as im:
        im.load()
        # Already suitable JPEGs stay byte-identical; repeated saves must not recompress them.
        if im.format == 'JPEG' and im.mode == 'RGB' and max(im.size) <= 1600 and not im.getexif():
            return data
        im = im.convert('RGB')
        im.thumbnail((1600, 1600))
        output = BytesIO()
        im.save(output, 'JPEG', quality=92)
        return output.getvalue()


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_replace(staged, target, expected_hash=None):
    for delay in (0, .08, .16, .32, .5, .8):
        if delay:
            time.sleep(delay)
        try:
            if expected_hash is not None and digest(target) != expected_hash:
                raise ValueError('文件已被其他程序修改，已停止替换，请重新导入后重试')
            os.replace(staged, target)
            return
        except PermissionError:
            continue
    raise PermissionError('Windows 拒绝替换文件：文件可能被其他播放器占用、设为只读，或目录不允许修改。'
                          '原文件未替换，备份已保留。请关闭占用程序后重试，或选择「另存整理副本」。')


def write_tags(track: Track, lyrics: str | None, cover: bytes | None, romaji: str | None = None,
               provenance: dict | None = None, *, replace_cover=False, output_path=None) -> dict:
    """Stage -> validate -> exclusive backup -> atomic replacement. Never re-encode."""
    src = Path(track.path)
    dst = Path(output_path).resolve() if output_path else src
    is_copy = dst != src
    if src.suffix.lower() not in WRITABLE:
        raise ValueError('此格式仅支持分析；嵌入支持 FLAC、MP3、M4A')
    if is_copy and (dst.exists() or dst.suffix.lower() != src.suffix.lower()):
        raise ValueError('另存目标必须是同扩展名的新文件，不能覆盖已有文件')
    if not is_copy and not (src.stat().st_mode & stat.S_IWRITE):
        raise PermissionError('原文件设置为只读。请取消只读属性，或选择「另存整理副本」。')
    if lyrics is None and cover is None and romaji is None:
        raise ValueError('没有待写入的内容')
    original_hash = digest(src)
    # Validate and normalize before touching any file.
    cover = image_bytes(cover) if cover else None
    backup_dir = dst.parent / '.mio' / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (src.name + '.' + original_hash[:16] + '.bak')
    fd, tmp = tempfile.mkstemp(prefix='.mio-', suffix=src.suffix, dir=dst.parent)
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.chmod(tmp, os.stat(tmp).st_mode | stat.S_IWRITE)
        audio = mutagen.File(tmp)
        if audio.tags is None:
            audio.add_tags()
        if isinstance(audio, FLAC):
            if lyrics is not None:
                audio['lyrics'] = lyrics
            if romaji is not None:
                audio['MIO_ROMAJI'] = romaji
            if cover and (replace_cover or not audio.pictures):
                if replace_cover:
                    other_pictures = [p for p in audio.pictures if p.type != 3]
                    audio.clear_pictures()
                    for other in other_pictures:
                        audio.add_picture(other)
                pic = Picture()
                pic.type, pic.mime, pic.desc, pic.data = 3, 'image/jpeg', 'Front cover', cover
                with Image.open(BytesIO(cover)) as im:
                    pic.width, pic.height = im.size
                pic.depth = 24
                audio.add_picture(pic)
        elif isinstance(audio, MP3):
            if lyrics is not None:
                audio.tags.delall('USLT')
                audio.tags.add(USLT(encoding=3, lang='und', desc='', text=lyrics))
            if romaji is not None:
                audio.tags.add(TXXX(encoding=3, desc='MIO_ROMAJI', text=[romaji]))
            if cover and (replace_cover or not audio.tags.getall('APIC')):
                if replace_cover:
                    other_pictures = [p for p in audio.tags.getall('APIC') if p.type != 3]
                    audio.tags.delall('APIC')
                    for other in other_pictures:
                        audio.tags.add(other)
                audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Front cover', data=cover))
        elif isinstance(audio, MP4):
            if lyrics is not None:
                audio['\xa9lyr'] = [lyrics]
            if romaji is not None:
                audio['----:com.mio:ROMAJI'] = [romaji.encode('utf-8')]
            if cover and (replace_cover or not audio.get('covr')):
                audio['covr'] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)] + list(audio.get('covr', []))[1:]
        else:
            raise ValueError('不支持此音频容器的写入')
        audio.save()
        check = read_track(tmp)
        if abs(check.duration - track.duration) > 0.1:
            raise ValueError('写入校验失败：音频时长发生变化')
        if lyrics is not None and check.lyrics != lyrics:
            raise ValueError('写入校验失败：歌词不一致')
        if romaji is not None and check.romaji != romaji:
            raise ValueError('写入校验失败：罗马音不一致')
        if cover and not check.cover:
            raise ValueError('写入校验失败：封面未写入')
        if cover and (replace_cover or not track.cover) and check.cover != cover:
            raise ValueError('写入校验失败：封面与所选图片不一致')
        if digest(src) != original_hash:
            raise ValueError('原文件被其他程序修改，请重新导入后重试')
        if not backup.exists():
            try:
                with open(src, 'rb') as inp, open(backup, 'xb') as out:
                    shutil.copyfileobj(inp, out)
            except FileExistsError:
                pass
        if digest(backup) != original_hash:
            raise ValueError('备份验证失败，原文件未修改')
        if is_copy:
            # Publish a validated new file without overwriting a raced-in destination.
            if os.name == 'nt':
                os.rename(tmp, dst)  # Windows rename fails if destination exists.
            else:
                os.link(tmp, dst)
                os.unlink(tmp)
        else:
            atomic_replace(tmp, src, original_hash)
        record = {'time': datetime.now().isoformat(timespec='seconds'), 'path': str(dst),
                  'original_path': str(src), 'action': 'copy' if is_copy else 'write', 'record_id': str(uuid.uuid4()),
                  'backup': str(backup), 'before_sha256': original_hash, 'after_sha256': digest(dst),
                  'sources': provenance or {}, 'log_path': str(dst.parent / '.mio' / 'history.jsonl'),
                  'changes': {'lyrics': lyrics is not None, 'romaji': romaji is not None,
                              'cover': bool(cover), 'replace_cover': bool(cover and replace_cover)}}
        try:
            with open(record['log_path'], 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        except OSError as e:
            record['warning'] = '已写入且保留备份，但操作记录保存失败：' + str(e)
        return record
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def restore(record):
    src, backup = Path(record['path']), Path(record['backup'])
    if digest(src) != record['after_sha256']:
        raise ValueError('文件在写入后已变化，拒绝覆盖。请手动检查备份。')
    if digest(backup) != record['before_sha256']:
        raise ValueError('备份完整性校验失败')
    if record.get('action') == 'copy':
        src.unlink()
        return
    fd, tmp = tempfile.mkstemp(prefix='.mio-restore-', suffix=src.suffix, dir=src.parent)
    os.close(fd)
    try:
        shutil.copy2(backup, tmp)
        atomic_replace(tmp, src, record['after_sha256'])
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
