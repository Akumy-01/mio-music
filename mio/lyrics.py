"""Independent lyrics providers with bounded requests, partial results and disk cache.

Only public line-synced/text endpoints are used. No audio download or login required.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode

import requests
from .core import Track

PROVIDERS = {'netease': '网易云音乐', 'kugou': '酷狗音乐', 'lrclib': 'LRCLIB'}
CACHE = Path(os.getenv('LOCALAPPDATA', Path.home() / '.cache')) / 'MioMusic' / 'cache' / 'lyrics-v2'
TIMEOUT = (3.5, 6)
MAX_BYTES = 2 * 1024 * 1024
_STAMP = re.compile(r'\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]')


class LyricsError(ValueError):
    pass


@dataclass
class SearchResult:
    rows: list[dict]
    statuses: list[dict]


@dataclass
class LyricsPayload:
    text: str
    translation: str = ''
    romaji: str = ''
    cached: bool = False
    stale: bool = False


def error_message(error):
    if isinstance(error, requests.exceptions.SSLError):
        return 'TLS 证书校验失败'
    if isinstance(error, requests.exceptions.Timeout):
        return '连接超时'
    if isinstance(error, requests.exceptions.ConnectionError):
        return '网络连接失败'
    if isinstance(error, (ValueError, KeyError, TypeError)) and not isinstance(error, LyricsError):
        return '接口响应格式已变化'
    return str(error)[:160] or type(error).__name__


class Client:
    def __init__(self, refresh=False):
        self.refresh = refresh
        self.cached = False
        self.stale = False

    def get(self, url, params=None, *, ttl=86400, referer=None):
        key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        path = CACHE / (key + '.json')
        saved, age = None, float('inf')
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            age = time.time() - path.stat().st_mtime
            if not self.refresh and age < ttl:
                self.cached = True
                return saved
        except (OSError, ValueError):
            pass
        headers = {'User-Agent': 'MioMusic/1.1 (+https://github.com/Akumy-01/mio-music)',
                   'Accept': 'application/json'}
        if referer:
            headers['Referer'] = referer
        try:
            # Fail over to another provider instead of retrying the same unavailable service.
            with requests.get(url, params=params, headers=headers, timeout=TIMEOUT, stream=True) as r:
                if r.status_code != 200:
                    raise LyricsError(f'HTTP {r.status_code}')
                raw = bytearray()
                for chunk in r.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise LyricsError('响应超过 2 MB，已停止读取')
                data = json.loads(raw.decode('utf-8-sig'))
                if not isinstance(data, (dict, list)):
                    raise LyricsError('接口返回了无效数据')
        except (requests.RequestException, ValueError):
            if saved is not None and age < 30 * 86400:
                self.cached = self.stale = True
                return saved
            raise
        # Never cache application errors or empty results: allow a fresh retry immediately.
        valid = bool(data) and (not isinstance(data, dict) or
                (data.get('code', 200) == 200 and data.get('status', 200) in (200, '200')))
        if valid:
            try:
                CACHE.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix=key, suffix='.tmp', dir=CACHE)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False)
                    os.replace(tmp, path)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
            except OSError:
                pass
        return data


def clean_query(title):
    title = Path(title).stem if re.search(r'\.(flac|mp3|m4a|wav|ogg|opus|aiff?)$', title, re.I) else title
    return re.sub(r'\s+', ' ', title).strip()


def _row(source, ident, title, artist='', album='', duration=0, **extra):
    return {'source': source, 'sourceLabel': PROVIDERS[source], 'id': str(ident),
            'trackName': str(title), 'artistName': str(artist), 'albumName': str(album),
            'duration': float(duration or 0), **extra}


def _check(data, key='code'):
    if not isinstance(data, dict):
        raise LyricsError('接口响应格式已变化')
    if data.get(key, 200) not in (200, '200'):
        raise LyricsError(f'服务拒绝请求（{data.get(key)}）')
    return data


def _search_netease(track, client):
    params = {'s': clean_query(track.title) + (' ' + track.artist if track.artist else ''),
              'type': 1, 'limit': 8, 'offset': 0}
    data = _check(client.get('https://music.163.com/api/search/get', params, referer='https://music.163.com/'))
    if not (data.get('result') or {}).get('songs') and track.artist:
        data = _check(client.get('https://music.163.com/api/search/get',
            {**params, 's': clean_query(track.title)}, referer='https://music.163.com/'))
    rows = []
    for s in (data.get('result') or {}).get('songs', [])[:8]:
        rows.append(_row('netease', s['id'], s['name'],
            ' / '.join(a['name'] for a in s.get('artists', [])),
            (s.get('album') or {}).get('name', ''), s.get('duration', 0) / 1000,
            sourceUrl=f'https://music.163.com/song?id={s["id"]}', needsFetch=True))
    return rows


def _search_kugou(track, client):
    params = {'ver': 1, 'man': 'yes', 'client': 'pc',
         'keyword': clean_query(track.title) + (' ' + track.artist if track.artist else ''),
         'duration': round(track.duration * 1000)}
    data = _check(client.get('https://lyrics.kugou.com/search', params), 'status')
    if not data.get('candidates') and track.artist:
        data = _check(client.get('https://lyrics.kugou.com/search',
            {**params, 'keyword': clean_query(track.title)}), 'status')
    return [_row('kugou', s['id'], s.get('song', ''), s.get('singer', ''),
            duration=s.get('duration', 0) / 1000, accesskey=s['accesskey'],
            sourceUrl='https://www.kugou.com/', needsFetch=True)
            for s in data.get('candidates', [])[:8]]


def _search_lrclib(track, client):
    params = {'track_name': clean_query(track.title)}
    if track.artist:
        params['artist_name'] = track.artist
    data = client.get('https://lrclib.net/api/search', params)
    if not isinstance(data, list):
        raise LyricsError('接口响应格式已变化')
    # Overly strict artist tags (aliases, multiple artists) should not hide title matches.
    if not data and track.artist:
        data = client.get('https://lrclib.net/api/search', {'q': clean_query(track.title)})
    rows = []
    for s in data:
        if s.get('plainLyrics') or s.get('syncedLyrics') or s.get('instrumental'):
            r = dict(s)
            r.update(source='lrclib', sourceLabel=PROVIDERS['lrclib'], id=str(s['id']),
                     sourceUrl=f'https://lrclib.net/api/get/{s["id"]}', needsFetch=False)
            rows.append(r)
    return rank(rows, track)[:12]


SEARCHERS = {'netease': _search_netease, 'kugou': _search_kugou, 'lrclib': _search_lrclib}


def _similarity(a, b):
    def normalize(s):
        import unicodedata
        return re.sub(r'[^\w]', '', unicodedata.normalize('NFKC', s).casefold())
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def rank(rows, track):
    unique = {}
    for row in rows:
        key = row['source'], str(row['id'])
        if key in unique:
            continue
        title = _similarity(clean_query(track.title), row.get('trackName', ''))
        artist = _similarity(track.artist, row.get('artistName', '')) if track.artist else .5
        duration = float(row.get('duration') or 0)
        timing = max(0, 1 - abs(track.duration - duration) / 20) if duration and track.duration else .5
        album = _similarity(track.album, row.get('albumName', '')) if track.album and row.get('albumName') else .5
        unique[key] = {**row, 'match': round(100 * (.5*title + .25*artist + .2*timing + .05*album))}
    # Preserve all per-source candidates so a top result without lyrics never hides alternatives.
    return sorted(unique.values(), key=lambda r: r['match'], reverse=True)[:32]


def search_lyrics(track: Track, source='auto', progress=None, refresh=False) -> SearchResult:
    if source != 'auto' and source not in SEARCHERS:
        raise ValueError('未知歌词来源')
    chosen = list(SEARCHERS) if source == 'auto' else [source]
    all_rows, statuses = [], []
    def run(name):
        c = Client(refresh=refresh)
        try:
            rows = SEARCHERS[name](track, c)
            state = '缓存回退' if c.stale else '缓存' if c.cached else '在线'
            return rows, {'source': name, 'label': PROVIDERS[name], 'ok': True,
                          'count': len(rows), 'message': f'{state} · {len(rows)} 个候选'}
        except Exception as e:
            return [], {'source': name, 'label': PROVIDERS[name], 'ok': False,
                        'count': 0, 'message': error_message(e)}
    with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        futures = {pool.submit(run, name): name for name in chosen}
        for future in as_completed(futures):
            rows, status = future.result()
            all_rows.extend(rows)
            statuses.append(status)
            if progress:
                progress(SearchResult(rank(all_rows, track), [dict(s) for s in statuses]))
    return SearchResult(rank(all_rows, track), statuses)


def _lyric_field(data, key):
    value = data.get(key) or {}
    return str(value.get('lyric') or '') if isinstance(value, dict) else ''


def fetch_lyrics(row, refresh=False) -> LyricsPayload:
    source = row['source']
    if source == 'spotify':
        if row.get('mode') == 'direct':
            from .spotify_direct import fetch_direct
            return fetch_direct(row['id'])
        from .spotify import fetch_spotify
        return fetch_spotify(row['endpoint'], row['id'])
    client = Client(refresh=refresh)
    if source == 'lrclib':
        text = row.get('syncedLyrics') or row.get('plainLyrics') or ''
        if not text.strip():
            raise LyricsError('此候选没有可用歌词，请选择其他版本或来源')
        return LyricsPayload(text)
    if source == 'netease':
        if not str(row['id']).isdigit():
            raise LyricsError('无效歌曲 ID')
        d = _check(client.get('https://music.163.com/api/song/lyric',
            {'id': row['id'], 'lv': -1, 'kv': -1, 'tv': -1, 'rv': -1},
            ttl=7*86400, referer='https://music.163.com/'))
        payload = LyricsPayload(_lyric_field(d, 'lrc'), _lyric_field(d, 'tlyric'), _lyric_field(d, 'romalrc'))
    elif source == 'kugou':
        d = _check(client.get('https://lyrics.kugou.com/download',
            {'ver': 1, 'client': 'pc', 'id': row['id'], 'accesskey': row['accesskey'],
             'fmt': 'lrc', 'charset': 'utf8'}, ttl=7*86400), 'status')
        try:
            text = base64.b64decode(d.get('content', ''), validate=True).decode('utf-8-sig')
        except (ValueError, UnicodeDecodeError) as e:
            raise LyricsError('酷狗歌词解码失败，请选择其他候选') from e
        payload = LyricsPayload(text)
    else:
        raise LyricsError('未知歌词来源')
    if not payload.text.strip():
        raise LyricsError('此候选没有可用歌词（可能是纯音乐或服务未提供），请选择其他版本或来源')
    payload.text = html.unescape(payload.text)
    payload.translation = html.unescape(payload.translation)
    payload.romaji = html.unescape(payload.romaji)
    payload.cached, payload.stale = client.cached, client.stale
    return payload


def merge_lrc(primary, secondary):
    """Align optional translations/romaji by timestamp, never concatenate complete files."""
    if not secondary.strip():
        return primary
    def ms(match):
        minute, second, fraction = match.groups()
        return int(minute)*60000 + int(second)*1000 + int((fraction or '').ljust(3, '0'))
    extras = {}
    for line in secondary.splitlines():
        stamps = list(_STAMP.finditer(line))
        body = _STAMP.sub('', line).strip()
        if body:
            for stamp in stamps:
                extras.setdefault(ms(stamp), []).append(body)
    out = []
    for line in primary.splitlines():
        out.append(line)
        stamps = list(_STAMP.finditer(line))
        if not stamps:
            continue
        # Tolerate 20ms timestamp rounding differences, but never match distant lines.
        for stamp in stamps:
            key = ms(stamp)
            nearest = min(extras, key=lambda x: abs(x-key)) if extras else None
            if nearest is not None and abs(nearest-key) <= 20:
                for text in dict.fromkeys(extras[nearest]):
                    if text != _STAMP.sub('', line).strip():
                        out.append(stamp.group(0) + text)
    return '\n'.join(out)
