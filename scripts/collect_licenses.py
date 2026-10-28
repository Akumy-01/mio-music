"""Preserve upstream notices in portable distribution."""
from pathlib import Path
import importlib.metadata as metadata
import shutil
import subprocess
import sys
import imageio_ffmpeg

target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'dist' / 'MioMusic' / 'licenses'
target.mkdir(parents=True, exist_ok=True)
for dist in metadata.distributions():
    name = dist.metadata.get('Name', 'unknown')
    for file in dist.files or []:
        if any(token in file.name.lower() for token in ('license', 'copying', 'notice')):
            src = Path(dist.locate_file(file))
            if src.is_file() and src.stat().st_size < 3_000_000:
                dest = target / name / str(file).replace('..', '_').replace(':', '_')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license, target / 'Python-LICENSE.txt')
version = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-version'], capture_output=True,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
(target / 'ffmpeg-version.txt').write_bytes(version.stdout + version.stderr)
print('Third-party notices copied to', target)
