# Third-party notices

Mio Music is distributed under GNU GPL v3. Copyright (c) 2026 Mio Music contributors.

The software depends on the following upstream projects. Their authors retain all copyrights. Exact versions are recorded in requirements-lock.txt. The packaged `licenses/` folder contains license/notice files copied from installed distributions, and PyInstaller also collects available package metadata.

| Component | License | Upstream source |
|---|---|---|
| Python | PSF | https://github.com/python/cpython |
| PySide6 / Qt | GPL v3 option used by this application; upstream also offers LGPL/commercial options | https://code.qt.io/cgit/pyside/pyside-setup.git/ ; https://code.qt.io/cgit/qt/ |
| NumPy | BSD-3-Clause and bundled component notices | https://github.com/numpy/numpy |
| SciPy | BSD-3-Clause and bundled component notices | https://github.com/scipy/scipy |
| Mutagen | GPL-2.0-or-later | https://github.com/quodlibet/mutagen |
| pykakasi | GPL-3.0-or-later | https://github.com/miurahr/pykakasi |
| jaconv | MIT | https://github.com/ikegami-yukino/jaconv |
| Requests | Apache-2.0 | https://github.com/psf/requests |
| Pillow | MIT-CMU | https://github.com/python-pillow/Pillow |
| imageio-ffmpeg Python wrapper | BSD-2-Clause | https://github.com/imageio/imageio-ffmpeg |
| FFmpeg bundled executable | GPL v3 enabled build, see details below | https://ffmpeg.org/ ; https://www.gyan.dev/ffmpeg/builds/ |
| PyInstaller bootloader | GPL with bootloader exception | https://github.com/pyinstaller/pyinstaller |

## FFmpeg

The imageio-ffmpeg 0.6.0 Windows wheel bundles `ffmpeg 7.1-essentials_build-www.gyan.dev`, configured with `--enable-gpl --enable-version3` and other external codec libraries. FFmpeg is invoked as a separate executable. It is not re-encoded or modified by Mio. Its upstream release sources are at https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz ; the builder's corresponding configuration, build information and source links are at https://www.gyan.dev/ffmpeg/builds/ and https://github.com/GyanD/codexffmpeg . Consult those for the bundled external libraries and corresponding source, rather than assuming the Python wrapper's BSD license covers FFmpeg.

The portable distribution retains license files from imageio-ffmpeg and includes the FFmpeg version/configuration output in `licenses/ffmpeg-version.txt`. If redistributing a modified build, provide complete corresponding source and notices for that exact build and its bundled dependencies as required by their licenses.

## Network content

NetEase Cloud Music: https://music.163.com/

KuGou Music: https://www.kugou.com/

Provider protocol references inspected during implementation: https://github.com/Ferry-200/music_api_dart (NetEase lyric fields and KuGou lyrics search/download); https://github.com/Ferry-200/coriander_player . Mio's Python adapters use public line-synced text responses and do not reuse the QRC/KRC decryption implementations or retrieve audio.

LRCLIB: https://lrclib.net/docs

MusicBrainz: https://musicbrainz.org/doc/About/Data_License

Cover Art Archive: https://musicbrainz.org/doc/Cover_Art_Archive

These services are independent of Mio. Service availability is not guaranteed. Lyrics and cover art remain subject to their respective rights and source terms. Source code licensing does not grant rights to redistribute fetched lyrics or artwork. No commercial music, full lyrics or album covers are included in the repository or application package.

The Mio icon and documentation example text/audio are generated specifically for this project and are distributed under the project's GPL v3 license.

## Optional Spotify service

Includes modified source from https://github.com/akashrchandran/spotify-lyrics-api at commit e158b96b854778d8ff51a3c9544ebb4f68b64907, licensed GPL-3.0-only. Copyright Akash R Chandran and upstream contributors. Full upstream LICENSE, source and modification notice retained in integrations/spotify-lyrics-api. No Spotify account credentials are distributed. The upstream is unofficial and warns about service terms. See docs/SPOTIFY.md for configuration and validation limits.
