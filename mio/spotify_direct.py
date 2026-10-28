"""In-process port of spotify-lyrics-api's own-session flow, GPL-3.0-only.

Protocol reference: akashrchandran/spotify-lyrics-api, e158b96b854778d8ff51a3c9544ebb4f68b64907.
No browser credential extraction; the user explicitly supplies their own session.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import re
import struct
import threading
import time
import requests
from .credentials import CredentialStore
from .lyrics import LyricsError, MAX_BYTES
from .spotify import parse_response, track_id

TIME_URL = 'https://open.spotify.com/api/server-time'
PARAMETERS_URL = 'https://raw.githubusercontent.com/xyloflake/spot-secrets-go/main/secrets/secretDict.json'
TOKEN_URL = 'https://open.spotify.com/api/token'
LYRICS_URL = 'https://spclient.wg.spotify.com/color-lyrics/v2/track/'
_store = CredentialStore()
_session = None
_tokens = {}
_lock = threading.RLock()


def validate_session(value):
    value = value.strip()
    if not re.fullmatch(r'[!-~]{16,1200}', value) or any(c in value for c in ';\"\\') or value.lower().startswith('sp_dc='):
        raise LyricsError('请只粘贴 SP_DC 的值，不要粘贴 Cookie 请求头、引号或其他字段。')
    return value


def get_session():
    global _session
    with _lock:
        if _session is None:
            _session = _store.read()
        return _session


def configure_session(value, persist=True):
    global _session
    value = validate_session(value)
    with _lock:
        if persist:
            _store.write(value)
        _session = value
        _tokens.clear()


def forget_session():
    global _session
    with _lock:
        _store.delete()
        _session = None
        _tokens.clear()


def totp(secret: bytes, seconds: int):
    digest = hmac.new(secret, struct.pack('>Q', int(seconds)//30), hashlib.sha1).digest()
    offset = digest[-1] & 15
    code = (struct.unpack('>I', digest[offset:offset+4])[0] & 0x7fffffff) % 1000000
    return f'{code:06d}'


class _HTTPError(LyricsError):
    def __init__(self, status):
        self.status = status
        messages = {401: 'Spotify 会话已失效，请在 Mio 更新登录会话',
                    403: 'Spotify 拒绝了请求，请检查账号、地区或会话状态',
                    404: 'Spotify 未提供此曲歌词，或内部接口已变化',
                    429: 'Spotify 请求过于频繁，请稍后重试'}
        super().__init__(messages.get(status, f'Spotify 直连暂不可用（HTTP {status}），其他来源仍可使用'))


def request_json(url, params=None, headers=None):
    try:
        with requests.get(url, params=params, headers=headers or {'Accept': 'application/json'},
                          timeout=(4, 12), stream=True, allow_redirects=False) as r:
            if r.status_code != 200:
                raise _HTTPError(r.status_code)
            raw = bytearray()
            for chunk in r.iter_content(65536):
                raw.extend(chunk)
                if len(raw) > MAX_BYTES:
                    raise LyricsError('Spotify 响应过大，已停止读取')
            try:
                data = json.loads(raw.decode('utf-8-sig'))
                if not isinstance(data, dict):
                    raise ValueError()
                return data
            except (ValueError, UnicodeDecodeError) as e:
                raise LyricsError('Spotify 直连接口响应发生变化，请更新 Mio 或改用其他歌词来源') from e
    except requests.exceptions.SSLError as e:
        raise LyricsError('Spotify 连接证书校验失败，请检查系统时间与网络') from e
    except requests.exceptions.Timeout as e:
        raise LyricsError('Spotify 连接超时，请检查本机能否访问 Spotify') from e
    except requests.RequestException as e:
        raise LyricsError('无法连接 Spotify，请检查网络；不会自动切换公共账号代理') from e


def _get_token(cookie, renew=False):
    fingerprint = hashlib.sha256(cookie.encode()).hexdigest()
    with _lock:
        saved = _tokens.get(fingerprint)
        if not renew and saved and saved[1] > time.time() + 30:
            return saved[0]
        clock = request_json(TIME_URL)
        parameters = request_json(PARAMETERS_URL)
        try:
            seconds = int(clock['serverTime'])
            version = max(int(k) for k in parameters if str(k).isdigit())
            values = parameters[str(version)]
            if not 0 <= seconds <= 2**63-1 or not isinstance(values, list) or not 1 <= len(values) <= 256:
                raise ValueError()
            if any(type(v) is not int or not 0 <= v <= 255 for v in values):
                raise ValueError()
            key = ''.join(str(v ^ ((i % 33) + 9)) for i, v in enumerate(values)).encode('ascii')
        except (KeyError, TypeError, ValueError, OverflowError) as e:
            raise LyricsError('Spotify 登录协议参数已变化，请更新 Mio 或使用自建服务模式') from e
        params = {'reason': 'transport', 'productType': 'web-player', 'totp': totp(key, seconds),
                  'totpVer': str(version), 'ts': str(int(time.time()))}
        result = request_json(TOKEN_URL, params, {
            'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
            'Cookie': 'sp_dc=' + cookie})
        token = result.get('accessToken')
        if result.get('isAnonymous') or not isinstance(token, str) or not token:
            raise LyricsError('Spotify 未接受此登录会话，请在 Mio 更新 SP_DC 后重试')
        try:
            expiry = float(result.get('accessTokenExpirationTimestampMs', 0)) / 1000
        except (TypeError, ValueError):
            expiry = 0
        _tokens[fingerprint] = token, expiry
        return token


def fetch_direct(song):
    song = track_id(song)
    cookie = get_session()
    if not cookie:
        raise LyricsError('首次使用请在 Spotify 窗口配置你自己的登录会话；无需 Docker 或额外服务')
    cookie = validate_session(cookie)
    for renew in (False, True):
        token = _get_token(cookie, renew)
        try:
            data = request_json(LYRICS_URL + song, {'format': 'json', 'market': 'from_token'},
                {'Accept': 'application/json', 'App-platform': 'WebPlayer', 'Authorization': 'Bearer ' + token})
            return parse_response(data)
        except _HTTPError as e:
            if e.status == 401 and not renew:
                continue
            raise
