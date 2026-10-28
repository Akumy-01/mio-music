"""Public metadata providers. Audio bytes never leave the machine."""
from __future__ import annotations
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import threading
import time
import hashlib
import requests
from .core import Track, image_bytes

USER_AGENT = 'MioMusic/1.0 (https://github.com/Akumy-01/mio-music)'
_lock = threading.Lock()
_last_request = 0.0
CACHE = Path(os.getenv('LOCALAPPDATA', Path.home() / '.cache')) / 'MioMusic' / 'cache'


def get_json(url, params=None):
    global _last_request
    key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    cache = CACHE / (key + '.json')
    try:
        if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
            return json.loads(cache.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    for attempt in range(3):
        with _lock:
            time.sleep(max(0, 1.1 - (time.monotonic() - _last_request)))
            try:
                response = requests.get(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=(8, 20))
            finally:
                _last_request = time.monotonic()
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        if response.status_code >= 400:
            raise ValueError(f'在线服务暂不可用（HTTP {response.status_code}）。请稍后重试，或导入本地歌词 / 封面。')
        break
    data = response.json()
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        temp = cache.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temp.replace(cache)
    except OSError:
        pass
    return data


def similarity(a, b):
    normalize = lambda x: re.sub(r'[^\w]', '', x.casefold())
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def find_lyrics(track: Track):
    from .lyrics import search_lyrics
    return search_lyrics(track).rows


def quote_query(value):
    return '"' + re.sub(r'[\\"+:!()\[\]{}~^?*|&]', ' ', value) + '"'


def find_covers(track: Track):
    if not track.album or not track.artist:
        raise ValueError('请先填写专辑与歌手，再搜索封面，以免匹配到错误专辑')
    query = f'release:{quote_query(track.album)} AND artist:{quote_query(track.artist)}'
    data = get_json('https://musicbrainz.org/ws/2/release/', {'query': query, 'fmt': 'json', 'limit': 8})
    return [{'id': r['id'], 'title': r['title'], 'date': r.get('date', '未知日期'),
             'artist': ' / '.join(a['artist']['name'] for a in r.get('artist-credit', []) if isinstance(a, dict)),
             'score': r.get('score', 0), 'country': r.get('country', ''),
             'url': f"https://musicbrainz.org/release/{r['id']}"}
            for r in data.get('releases', [])]


def download_cover(release_id):
    if not re.fullmatch(r'[0-9a-f-]{36}', release_id):
        raise ValueError('无效的发行版 ID')
    url = f'https://coverartarchive.org/release/{release_id}/front-500'
    with requests.get(url, headers={'User-Agent': USER_AGENT}, stream=True, timeout=(8, 25)) as response:
        if response.status_code == 404:
            raise ValueError('此发行版本没有可用的正面封面，请选择其他发行版本或导入本地封面。')
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 12 * 1024 * 1024:
                raise ValueError('封面过大，已停止下载')
    return image_bytes(bytes(data))
