# Upstream and modifications

Source: https://github.com/akashrchandran/spotify-lyrics-api

Pinned commit: `e158b96b854778d8ff51a3c9544ebb4f68b64907`.

Copyright remains with upstream authors; GPL-3.0-only, full LICENSE retained. This folder is a modified distribution, not an official Spotify service.

Mio changes: enabled TLS certificate/hostname verification; bounded connection/read timeouts; restricted cached token permissions; suppressed raw exception text in HTTP responses; validated track IDs; removed wildcard CORS; used a minimal local autoloader for the two upstream classes. The container binds only to 127.0.0.1, runs as non-root, has a read-only filesystem and ephemeral token cache.

The upstream token flow still depends on Spotify internal endpoints and a third-party protocol-parameter file. It may stop working and must not be treated as an official supported API. No account cookies, access tokens, lyrics or music are distributed here. Source compatibility tests are not a substitute for live account verification.
