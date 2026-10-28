"""Optional live diagnostics. Writes metadata/status only, never full lyrics."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mio.core import Track
from mio.lyrics import search_lyrics, fetch_lyrics

parser = argparse.ArgumentParser(description='诊断三种在线歌词来源（只记录状态和文本长度）')
parser.add_argument('--title')
parser.add_argument('--artist', default='')
parser.add_argument('--duration', type=float, default=0)
parser.add_argument('--output', default='build/lyrics-network-v1.1.json')
args = parser.parse_args()
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
samples = [(args.title, args.artist, args.duration)] if args.title else [
    ('Lemon', '米津玄師', 255), ('晴天', '周杰伦', 269), ('Hello', 'Adele', 295)]
report = []
for title, artist, duration in samples:
    start = time.monotonic()
    result = search_lyrics(Track('', title, artist, duration=duration), refresh=True)
    record = {'title': title, 'artist': artist, 'search_seconds': round(time.monotonic()-start, 2),
              'candidates': len(result.rows), 'statuses': result.statuses, 'fetches': []}
    for source in ('netease', 'kugou', 'lrclib'):
        row = next((r for r in result.rows if r['source'] == source and not r.get('instrumental')), None)
        if not row:
            continue
        start = time.monotonic()
        try:
            p = fetch_lyrics(row, refresh=True)
            record['fetches'].append({'source': source, 'id': row['id'], 'ok': True,
                'seconds': round(time.monotonic()-start, 2), 'text_chars': len(p.text),
                'translation_chars': len(p.translation), 'romaji_chars': len(p.romaji),
                'cached': p.cached, 'stale': p.stale})
        except Exception as e:
            record['fetches'].append({'source': source, 'id': row['id'], 'ok': False, 'error': str(e)})
    report.append(record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
path = Path(args.output)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('Report:', path)
