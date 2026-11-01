"""Compile and run B's state and C snapshot adapter tests with a C11 compiler."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'b/tests'),
                '-p','test_*.py','-v'],check=True)
out = ROOT / '.local/b-host-tests'
out.mkdir(parents=True, exist_ok=True)
compiler = os.environ.get('CC') or next((c for c in ('cl', 'cc', 'gcc', 'clang') if shutil.which(c)), None)
if not compiler:
    raise SystemExit('C compiler missing: use a C11 developer terminal or set CC to its executable')
pose = ROOT / 'c/firmware/apps/main/pose'
firmware = ROOT / 'b/firmware'
for name in ('device_state', 'c_vision', 'spi_workflow', 'spi_runtime', 'spi_live'):
    includes = [firmware, pose]
    sources = [ROOT / ('b/tests/b_' + name + '_test.c'), firmware / 'b_device_state.c']
    if name == 'spi_workflow':
        sources = [ROOT/'b/tests/b_spi_workflow_test.c',firmware/'b_spi_workflow.c']
    if name == 'spi_runtime':
        includes = [ROOT/'b/tests/spi_stubs',ROOT/'b/tests/stubs',firmware,pose]
        sources = [ROOT/'b/tests/b_spi_runtime_test.c',firmware/'b_spi_runtime.c',firmware/'b_spi_workflow.c']
    if name == 'spi_live':
        includes = [ROOT/'b/tests/live_stubs',pose]
        sources = [ROOT/'b/tests/b_spi_live_test.c',pose/'c_live_pose.c',
                   pose/'c_posture_calibration.c',pose/'c_posture_filter.c']
    if name == 'c_vision':
        includes.insert(0, ROOT / 'b/tests/stubs')
        sources += [firmware / 'b_c_vision.c', pose / 'c_posture_calibration.c', pose / 'c_posture_filter.c']
    exe = out / (name + ('-test.exe' if os.name == 'nt' else '-test'))
    if Path(compiler).stem.lower() == 'cl':
        command = [compiler, '/nologo', '/W4', '/WX', '/std:c11',
                   *['/I' + str(i) for i in includes], *map(str, sources), '/Fe:' + str(exe)]
    else:
        command = [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                   *[item for i in includes for item in ('-I', str(i))],
                   *map(str, sources), '-lm', '-o', str(exe)]
    if name == 'spi_runtime':
        command[1:1] = (['/DCONFIG_C_LIVE_POSE_SUPPORT=1','/DCONFIG_B_SPI_WORKFLOW_SUPPORT=1']
            if Path(compiler).stem.lower()=='cl' else
            ['-DCONFIG_C_LIVE_POSE_SUPPORT=1','-DCONFIG_B_SPI_WORKFLOW_SUPPORT=1'])
    if name == 'spi_live':
        command[1:1] = (['/DCONFIG_C_POSE_ROTATE_CW90=0'] if Path(compiler).stem.lower()=='cl'
                         else ['-DCONFIG_C_POSE_ROTATE_CW90=0'])
    subprocess.run(command, cwd=out, check=True)
    subprocess.run([str(exe)], cwd=out, check=True)
print('PASS: B state, C adapter and SPI workflow/runtime test executables; no hardware validation')
