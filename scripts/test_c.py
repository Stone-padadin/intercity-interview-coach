"""Run Python protocol tests and compile/run portable C calibration/filter tests."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
                str(ROOT / 'c/tools/cvision'), '-p', 'test_*.py', '-v'], check=True)
out = ROOT / '.local/host-tests'
out.mkdir(parents=True, exist_ok=True)
pose = ROOT / 'c/firmware/apps/main/pose'
compiler = os.environ.get('CC') or next((c for c in ('cl','cc','gcc','clang') if shutil.which(c)), None)
if not compiler:
    raise SystemExit('C compiler missing: on Windows use scripts/Test-C.cmd with Build Tools installed')
for name in ('filter', 'calibration'):
    sources = [ROOT / ('c/tests/c_posture_' + name + '_test.c'), pose / 'c_posture_filter.c']
    if name == 'calibration':
        sources.append(pose / 'c_posture_calibration.c')
    exe = out / (name + ('-test.exe' if os.name == 'nt' else '-test'))
    if Path(compiler).stem.lower() == 'cl':
        cmd = [compiler, '/nologo', '/W4', '/WX', '/std:c11', '/I' + str(pose),
               *map(str, sources), '/Fe:' + str(exe)]
    else:
        cmd = [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(pose),
               *map(str, sources), '-lm', '-o', str(exe)]
    subprocess.run(cmd, cwd=out, check=True)
    subprocess.run([str(exe)], cwd=out, check=True)
print('PASS: 19 Python tests and both C test executables')
