from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from urllib.parse import parse_qs, urlparse
import pytest
from mio.spotify import track_id, endpoint_url, parse_response, fetch_spotify

ID = '5f8eCNwTlr0RJopE9vQ6mB'


@pytest.mark.parametrize('value', [ID, 'spotify:track:' + ID,
    'https://open.spotify.com/track/' + ID + '?si=example',
    'https://open.spotify.com/intl-zh/track/' + ID])
def test_track_input(value):
    assert track_id(value) == ID


@pytest.mark.parametrize('value', ['https://evil.example/track/' + ID,
    'https://open.spotify.com/playlist/' + ID, 'file:///secret', 'too-short'])
def test_reject_invalid_track(value):
    with pytest.raises(ValueError):
        track_id(value)


@pytest.mark.parametrize('value', ['http://remote.example/', 'https://user:secret@example.com/',
    'https://example.com/?token=secret', 'https://example.com/#secret'])
def test_endpoint_no_credentials_or_insecure_remote(value):
    with pytest.raises(ValueError):
        endpoint_url(value)


def test_lrc_and_raw_millisecond_formats_and_unsynced():
    data = {'error': False, 'syncType': 'LINE_SYNCED', 'lines': [
        {'timeTag': '01:02.34', 'words': 'original example'}]}
    assert parse_response(data).text == '[01:02.34]original example'
    data['lines'] = [{'startTimeMs': '62345', 'words': 'original example'}]
    assert parse_response(data).text == '[01:02.34]original example'
    data['syncType'] = 'UNSYNCED'
    assert parse_response(data).text == 'original example'


def test_error_payload_not_treated_as_empty_success():
    for d in [{'error': True, 'message': 'private cookie details'}, {'error': False, 'lines': []}]:
        with pytest.raises(ValueError) as error:
            parse_response(d)
        assert 'private cookie' not in str(error.value)


@contextmanager
def service(status=200):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.query = parse_qs(urlparse(self.path).query)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': status != 200, 'syncType': 'LINE_SYNCED',
                'lines': [{'timeTag': '00:01.23', 'words': 'original fixture'}]}).encode())
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_http_adapter_contract():
    with service() as (server, endpoint):
        assert fetch_spotify(endpoint, ID).text == '[00:01.23]original fixture'
        assert server.query == {'trackid': [ID], 'format': ['lrc']}


@pytest.mark.parametrize('status,message', [(401, '会话'), (404, '没有提供'), (429, '过于频繁'), (503, '暂不可用')])
def test_http_errors_are_actionable(status, message):
    with service(status) as (_, endpoint):
        with pytest.raises(ValueError, match=message):
            fetch_spotify(endpoint, ID)
