from mio.core import Track
from mio import providers


def test_lyrics_ranking(monkeypatch):
    monkeypatch.setattr(providers, 'get_json', lambda *a: [
        {'id': 1, 'trackName': 'Song', 'artistName': 'Someone', 'duration': 300, 'plainLyrics': 'one'},
        {'id': 2, 'trackName': 'Song', 'artistName': 'Artist', 'duration': 180, 'syncedLyrics': 'two'},
        {'id': 3, 'trackName': 'Song', 'artistName': 'Artist', 'duration': 180}])
    rows = providers.find_lyrics(Track('x.flac', 'Song', 'Artist', duration=180))
    assert [r['id'] for r in rows] == [2, 1]
    assert rows[0]['match'] == 100


def test_cover_requires_album_artist():
    import pytest
    with pytest.raises(ValueError, match='专辑与歌手'):
        providers.find_covers(Track('x.flac', 'Song'))
