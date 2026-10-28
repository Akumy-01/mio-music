"""Adapter for a user-owned akashrchandran/spotify-lyrics-api deployment.

Mio never reads browser cookies. Authentication belongs to the configured service.
"""
from __future__ import annotations
import json
import re
from urllib.parse import urlparse
import requests
from .lyrics import LyricsPayload, LyricsError, MAX_BYTES


def track_id(value):
    value = value.strip()
    if re.fullmatch(r'[A-Za-z0-9]{22}', value):
        return value
    if value.startswith('spotify:track:'):
        return track_id(value[14:])
    u = urlparse(value)
    if u.scheme == 'https' and u.hostname == 'open.spotify.com':
        match = re.fullmatch(r'/(?:intl-[a-zA-Z-]+/)?track/([A-Za-z0-9]{22})/?', u.path)
        if match:
            return match[1]
    raise LyricsError('请输入完整 Spotify 歌曲链接、spotify:track: URI 或 22 位 Track ID；不支持歌单链接。')


def endpoint_url(value):
    u = urlparse(value.strip())
    if not u.hostname or u.username or u.password or u.query or u.fragment:
        raise LyricsError('服务地址不能包含账号、密码、查询参数或片段；登录会话请配置在你自己的服务端。')
    if u.scheme != 'https' and not (u.scheme == 'http' and u.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise LyricsError('本机服务可使用 HTTP，远程服务必须使用 HTTPS。')
    try:
        u.port
    except ValueError as e:
        raise LyricsError('服务端口无效') from e
    return u.geturl()


def parse_response(data):
    if not isinstance(data, dict) or data.get('error'):
        raise LyricsError('Spotify 服务未返回歌词，请检查该曲是否有歌词以及服务端登录会话是否有效。')
    body = data.get('lyrics', data)
    lines = body.get('lines') if isinstance(body, dict) else None
    synced = body.get('syncType') == 'LINE_SYNCED' if isinstance(body, dict) else False
    if isinstance(lines, str):
        if not lines.strip():
            raise LyricsError('此歌曲暂无可用歌词')
        return LyricsPayload(lines)
    if not isinstance(lines, list) or not lines:
        raise LyricsError('此歌曲暂无可用歌词')
    output = []
    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get('words'), str):
            raise LyricsError('Spotify 歌词响应格式不兼容')
        words = line['words'].replace('\r', '')
        if synced:
            tag = line.get('timeTag')
            if tag is not None:
                if not re.fullmatch(r'\d{1,3}:\d{2}\.\d{2,3}', str(tag)):
                    raise LyricsError('Spotify 时间戳无效')
            else:
                try:
                    ms = int(line['startTimeMs'])
                    if not 0 <= ms <= 359999999:
                        raise ValueError()
                except (KeyError, TypeError, ValueError) as e:
                    raise LyricsError('Spotify 时间戳无效') from e
                tag = f'{ms//60000:02d}:{ms//1000%60:02d}.{ms%1000//10:02d}'
            output.append(f'[{tag}]' + words)
        else:
            output.append(words)
    if not any(s.strip() for s in output):
        raise LyricsError('此歌曲暂无可用歌词')
    return LyricsPayload('\n'.join(output))


def fetch_spotify(endpoint, song):
    endpoint, song = endpoint_url(endpoint), track_id(song)
    try:
        with requests.get(endpoint, params={'trackid': song, 'format': 'lrc'},
                          timeout=(4, 12), stream=True, allow_redirects=False,
                          headers={'Accept': 'application/json', 'User-Agent': 'MioMusic/1.2'}) as r:
            messages = {400: '请求无效，请确认歌曲链接', 401: '服务端 Spotify 登录会话无效或已过期',
                        403: '该账号或地区无法获取此歌词', 404: 'Spotify 没有提供此歌曲的歌词',
                        429: 'Spotify 请求过于频繁，请稍后重试'}
            if r.status_code != 200:
                raise LyricsError(messages.get(r.status_code, f'Spotify 歌词服务暂不可用（HTTP {r.status_code}），请检查本地服务与登录会话'))
            raw = bytearray()
            for chunk in r.iter_content(65536):
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise LyricsError('Spotify 响应超过 2 MB，已停止读取')
            try:
                data = json.loads(raw.decode('utf-8-sig'))
            except (ValueError, UnicodeDecodeError) as e:
                raise LyricsError('服务没有返回 JSON；请确认填写的是 spotify-lyrics-api 服务地址') from e
            return parse_response(data)
    except requests.exceptions.SSLError as e:
        raise LyricsError('Spotify 服务证书校验失败，请配置有效的 HTTPS 证书') from e
    except requests.exceptions.Timeout as e:
        raise LyricsError('Spotify 服务连接超时，其他歌词来源仍可使用') from e
    except requests.RequestException as e:
        raise LyricsError('无法连接 Spotify 歌词服务，请先启动本地服务或检查服务地址') from e
