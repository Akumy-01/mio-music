import base64
import json
import os
import time

import pytest
import requests
from mio.core import Track
from mio import lyrics as m


TRACK = Track('x.flac', 'Lemon', '米津玄師', duration=255)


def candidate(source='netease'):
    return m._row(source, '123', 'Lemon', '米津玄師', duration=255,
                  sourceUrl='https://music.163.com/song?id=123', needsFetch=True)


def test_single_503_does_not_break_other_providers(monkeypatch):
    def fail(*args):
        raise m.LyricsError('HTTP 503')
    monkeypatch.setattr(m, 'SEARCHERS', {'netease': lambda *a: [candidate()],
                'lrclib': fail, 'kugou': lambda *a: [candidate('kugou')]})
    events = []
    result = m.search_lyrics(TRACK, progress=events.append)
    assert len(result.rows) == 2
    assert len(events) == 3
    assert any(s['source'] == 'lrclib' and not s['ok'] for s in result.statuses)
    assert any(s['message'] == 'HTTP 503' for s in result.statuses)


def test_all_fail_returns_diagnostics_instead_of_raising(monkeypatch):
    def fail(*args):
        raise requests.Timeout('private details')
    monkeypatch.setattr(m, 'SEARCHERS', {'lrclib': fail})
    result = m.search_lyrics(TRACK)
    assert result.rows == []
    assert result.statuses[0]['message'] == '连接超时'


def test_explicit_source_does_not_query_other_services(monkeypatch):
    calls = []
    def search(*a):
        calls.append('netease')
        return [candidate()]
    monkeypatch.setattr(m, 'SEARCHERS', {'netease': search, 'kugou': lambda *a: pytest.fail()})
    assert len(m.search_lyrics(TRACK, 'netease').rows) == 1
    assert calls == ['netease']


class Response:
    def __init__(self, data, status=200):
        self.data = json.dumps(data).encode()
        self.status_code = status
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def iter_content(self, size): yield self.data


def test_cache_then_outage_uses_marked_stale_data(monkeypatch, tmp_path):
    monkeypatch.setattr(m, 'CACHE', tmp_path)
    calls = []
    def get(*a, **kw):
        calls.append(kw)
        return Response({'result': {'songs': [{'id': 1}]}})
    monkeypatch.setattr(m.requests, 'get', get)
    first = m.Client().get('https://music.163.com/example', {'s': 'x'})
    c = m.Client()
    assert c.get('https://music.163.com/example', {'s': 'x'}) == first
    assert c.cached and not c.stale and len(calls) == 1
    p = next(tmp_path.glob('*.json'))
    os.utime(p, (time.time()-2*86400, time.time()-2*86400))
    monkeypatch.setattr(m.requests, 'get', lambda *a, **kw: Response({}, 503))
    c = m.Client(refresh=True)
    assert c.get('https://music.163.com/example', {'s': 'x'}) == first
    assert c.cached and c.stale
    assert calls[0]['timeout'] == m.TIMEOUT


def test_http_error_never_cached_and_refresh_bypasses_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(m, 'CACHE', tmp_path)
    monkeypatch.setattr(m.requests, 'get', lambda *a, **kw: Response({}, 503))
    with pytest.raises(m.LyricsError, match='503'):
        m.Client().get('https://lrclib.net/example')
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(m.requests, 'get', lambda *a, **kw: Response({'value': 1}))
    assert m.Client().get('https://lrclib.net/example')['value'] == 1
    monkeypatch.setattr(m.requests, 'get', lambda *a, **kw: Response({'value': 2}))
    assert m.Client(refresh=True).get('https://lrclib.net/example')['value'] == 2


def test_netease_search_and_payload(monkeypatch):
    def get(self, url, params=None, **kw):
        if 'search' in url:
            return {'code': 200, 'result': {'songs': [{'id': 1, 'name': 'Lemon',
                'artists': [{'name': '米津玄師'}], 'album': {'name': 'Lemon'}, 'duration': 255000}]}}
        return {'code': 200, 'lrc': {'lyric': '[00:01.00]原文'},
                'tlyric': {'lyric': '[00:01.00]译文'}, 'romalrc': {'lyric': '[00:01.00]romaji'}}
    monkeypatch.setattr(m.Client, 'get', get)
    row = m._search_netease(TRACK, m.Client())[0]
    assert row['duration'] == 255
    payload = m.fetch_lyrics(row)
    assert payload.text == '[00:01.00]原文'
    assert payload.romaji.endswith('romaji')
    assert payload.translation.endswith('译文')


def test_kugou_search_and_base64_lrc(monkeypatch):
    def get(self, url, params=None, **kw):
        if 'search' in url:
            return {'status': 200, 'candidates': [{'id': 1, 'song': 'Lemon', 'singer': '米津玄師',
                    'duration': 255000, 'accesskey': 'test'}]}
        assert params['fmt'] == 'lrc'
        return {'status': 200, 'content': base64.b64encode('[00:01.00]歌詞'.encode()).decode()}
    monkeypatch.setattr(m.Client, 'get', get)
    row = m._search_kugou(TRACK, m.Client())[0]
    assert m.fetch_lyrics(row).text == '[00:01.00]歌詞'


def test_empty_and_malformed_lyrics_are_failures(monkeypatch):
    monkeypatch.setattr(m.Client, 'get', lambda *a, **kw: {'code': 200, 'lrc': {}})
    with pytest.raises(m.LyricsError, match='没有可用歌词'):
        m.fetch_lyrics(candidate())
    monkeypatch.setattr(m.Client, 'get', lambda *a, **kw: {'status': 200, 'content': '%%%bad'})
    row = {**candidate('kugou'), 'accesskey': 'test'}
    with pytest.raises(m.LyricsError, match='解码失败'):
        m.fetch_lyrics(row)


def test_timestamp_alignment_and_duplicate_suppression():
    text = '[ar:Artist]\n[00:01.00]こんにちは\n[00:02.20][00:03.20]音楽'
    layer = '[00:01.010]hello\n[00:02.200]music\n[00:03.200]music\n[00:09.00]orphan'
    combined = m.merge_lrc(text, layer)
    assert '[00:01.00]hello' in combined
    assert '[00:02.20]music' in combined
    assert '[00:03.20]music' in combined
    assert 'orphan' not in combined
    assert m.merge_lrc(text, text) == text


def test_lrclib_falls_back_to_title_query(monkeypatch):
    calls = []
    def get(self, url, params=None, **kw):
        calls.append(params)
        return [] if 'artist_name' in params else [{'id': 2, 'trackName': 'Lemon', 'plainLyrics': 'test'}]
    monkeypatch.setattr(m.Client, 'get', get)
    rows = m._search_lrclib(TRACK, m.Client())
    assert len(rows) == 1 and calls[1] == {'q': 'Lemon'}


def test_kugou_relaxes_artist_when_no_results(monkeypatch):
    calls = []
    def get(self, url, params=None, **kw):
        calls.append(params['keyword'])
        return {'status': 200, 'candidates': [] if len(calls) == 1 else [
            {'id': '2', 'song': 'Lemon', 'accesskey': 'test'}]}
    monkeypatch.setattr(m.Client, 'get', get)
    assert len(m._search_kugou(TRACK, m.Client())) == 1
    assert calls == ['Lemon 米津玄師', 'Lemon']


def test_large_response_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(m, 'CACHE', tmp_path)
    r = Response({})
    r.data = b'x' * (m.MAX_BYTES+1)
    monkeypatch.setattr(m.requests, 'get', lambda *a, **kw: r)
    with pytest.raises(m.LyricsError, match='2 MB'):
        m.Client().get('https://lrclib.net/example')
    assert not list(tmp_path.iterdir())
