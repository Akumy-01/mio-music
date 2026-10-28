import os
import time
import uuid
import pytest
import requests
from mio import spotify_direct as m
from mio.credentials import CredentialStore

ID = '5f8eCNwTlr0RJopE9vQ6mB'
COOKIE = 'fixture-session-not-a-real-cookie'


@pytest.fixture(autouse=True)
def memory_isolation(monkeypatch):
    class Store:
        value = None
        def read(self): return self.value
        def write(self, value): self.value = value
        def delete(self): self.value = None
    monkeypatch.setattr(m, '_store', Store())
    monkeypatch.setattr(m, '_session', None)
    monkeypatch.setattr(m, '_tokens', {})


def protocol(monkeypatch, fail_first=False, fail_status=None):
    calls = []
    def request(url, params=None, headers=None):
        calls.append((url, params, headers))
        if url == m.TIME_URL:
            return {'serverTime': 59}
        if url == m.PARAMETERS_URL:
            return {'60': [1, 2, 3], '61': [2, 5, 8]}
        if url == m.TOKEN_URL:
            assert headers['Cookie'] == 'sp_dc=' + COOKIE
            assert params['totpVer'] == '61'
            assert params['totp'] == m.totp(b'11153', 59)  # decimal concatenation: (2^9)=11, (5^10)=15, (8^11)=3
            return {'accessToken': 'fixture-token', 'accessTokenExpirationTimestampMs': (time.time()+3600)*1000,
                    'isAnonymous': False}
        if url.startswith(m.LYRICS_URL):
            if fail_status:
                raise m._HTTPError(fail_status)
            if fail_first and sum(c[0].startswith(m.LYRICS_URL) for c in calls) == 1:
                raise m._HTTPError(401)
            assert headers['Authorization'] == 'Bearer fixture-token'
            return {'lyrics': {'syncType': 'LINE_SYNCED', 'lines': [{'startTimeMs': '1230', 'words': 'fixture'}]}}
        raise AssertionError('Unexpected endpoint')
    monkeypatch.setattr(m, 'request_json', request)
    return calls


def test_totp_known_vector():
    assert m.totp(b'12345678901234567890', 59) == '287082'


def test_session_persistence_and_forget():
    m.configure_session(COOKIE, persist=True)
    assert m._store.value == COOKIE and m.get_session() == COOKIE
    m._tokens['fake'] = ('fake-token', 1234)
    m.forget_session()
    assert m.get_session() is None and not m._tokens and m._store.value is None


def test_memory_only_does_not_write_or_replace_saved_credential():
    m._store.value = 'previous-fixture-session'
    m.configure_session(COOKIE, persist=False)
    assert m.get_session() == COOKIE and m._store.value == 'previous-fixture-session'


@pytest.mark.parametrize('value', ['sp_dc=' + COOKIE, COOKIE+'\r\nX: bad', COOKIE+';other=bad', 'short'])
def test_reject_cookie_headers_and_header_injection(value):
    with pytest.raises(ValueError):
        m.validate_session(value)


def test_direct_fetch_and_memory_token_cache(monkeypatch):
    m.configure_session(COOKIE, False)
    calls = protocol(monkeypatch)
    assert m.fetch_direct(ID).text == '[00:01.23]fixture'
    assert m.fetch_direct(ID).text == '[00:01.23]fixture'
    assert sum(url == m.TOKEN_URL for url, _, _ in calls) == 1
    for url, _, headers in calls:
        if url != m.TOKEN_URL:
            assert not headers or 'Cookie' not in headers
        if not url.startswith(m.LYRICS_URL):
            assert not headers or 'Authorization' not in headers


def test_401_renews_once_and_403_does_not_bypass(monkeypatch):
    m.configure_session(COOKIE, False)
    calls = protocol(monkeypatch, fail_first=True)
    assert m.fetch_direct(ID).text.endswith('fixture')
    assert sum(url == m.TOKEN_URL for url, _, _ in calls) == 2
    m._tokens.clear()
    calls = protocol(monkeypatch, fail_status=403)
    with pytest.raises(ValueError, match='拒绝'):
        m.fetch_direct(ID)
    assert sum(url.startswith(m.LYRICS_URL) for url, _, _ in calls) == 1


def test_absent_and_anonymous_sessions_fail_cleanly(monkeypatch):
    with pytest.raises(ValueError, match='首次使用'):
        m.fetch_direct(ID)
    m.configure_session(COOKIE, False)
    def request(url, params=None, headers=None):
        if url == m.TIME_URL: return {'serverTime': 59}
        if url == m.PARAMETERS_URL: return {'61': [1,2]}
        return {'isAnonymous': True, 'accessToken': 'do-not-use'}
    monkeypatch.setattr(m, 'request_json', request)
    with pytest.raises(ValueError, match='未接受'):
        m.fetch_direct(ID)
    assert not m._tokens


def test_sensitive_exception_details_not_exposed(monkeypatch):
    def fail(*a, **kw): raise requests.ConnectionError(COOKIE + ' fixture-token')
    monkeypatch.setattr(m.requests, 'get', fail)
    with pytest.raises(ValueError) as error:
        m.request_json(m.TOKEN_URL)
    assert COOKIE not in str(error.value) and 'fixture-token' not in str(error.value)


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows credentials')
def test_windows_credential_roundtrip_uses_separate_test_target():
    store = CredentialStore('MioMusic/Tests/' + str(uuid.uuid4()))
    try:
        try:
            store.write(COOKIE)
        except ValueError as e:
            if '1312' in str(e): pytest.skip('No Windows logon session in this runner')
            raise
        assert store.read() == COOKIE
    finally:
        store.delete()
    assert store.read() is None
