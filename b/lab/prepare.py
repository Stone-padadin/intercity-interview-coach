"""Add the optional lab module to a pinned SDK already integrated with C and B.

Does not run prepare_sdk/prepare_device or replace any existing B/C source.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

PIN = '06065ce9c5aa1e14cfae5c0ad574bad4aaaae34c'
HERE = Path(__file__).resolve().parent


def edits(app):
    cmake, main = app/'CMakeLists.txt', app/'main.c'
    if (app/'b_lab').exists():
        raise ValueError('b_lab already exists: inspect it; never overwrite an installed overlay')
    if not (app/'b_device/b_device_runtime.c').is_file():
        raise ValueError('Prepare and review the existing B integration first')
    changes = {}
    replacements = {
        cmake: (
            ('set(B_DEVICE_PROFILE "off" CACHE STRING "B device profile: off, voice, integrated")',
             'option(B_LAB_ENABLE "Opt-in private lab event/short-speech bridge" OFF)\n'
             'set(B_DEVICE_PROFILE "off" CACHE STRING "B device profile: off, voice, integrated")'),
            ('# 闹钟：平台组件和应用层模块一起开关，CONFIG_QM_ALARM_SUPPORT 0 时两者都不编译',
             'if(B_LAB_ENABLE)\n'
             '    if(B_DEVICE_PROFILE STREQUAL "off")\n'
             '        message(FATAL_ERROR "B_LAB_ENABLE requires the reviewed B device integration")\n'
             '    endif()\n'
             '    list(APPEND COMPONENT_SRCS "./b_lab/b_lab.c")\n'
             'endif()\n\n'
             '# 闹钟：平台组件和应用层模块一起开关，CONFIG_QM_ALARM_SUPPORT 0 时两者都不编译'),
            ('    "./b_device"', '    "./b_device"\n    "./b_lab"'),
            ('if(NOT B_DEVICE_PROFILE STREQUAL "off")\n    target_compile_definitions',
             'if(B_LAB_ENABLE)\n'
             '    target_compile_definitions(${COMPONENT_LIB} PRIVATE CONFIG_B_LAB_SUPPORT=1)\n'
             'endif()\n'
             'if(NOT B_DEVICE_PROFILE STREQUAL "off")\n    target_compile_definitions'),
        ),
        main: (
            ('#include "b_device_runtime.h"\n#endif',
             '#include "b_device_runtime.h"\n#endif\n'
             '#if CONFIG_B_LAB_SUPPORT\n#include "b_lab.h"\n#endif'),
            ('#if defined(CONFIG_APP_CAMERA_TEST) && CONFIG_APP_CAMERA_TEST\n    if (bsp_camera_early_init()',
             '#if CONFIG_B_LAB_SUPPORT\n'
             '    if (b_lab_init()!=QM_EOK) {\n'
             '        QM_LOGE("main","B lab bridge unavailable; voice baseline preserved");\n'
             '    }\n#endif\n'
             '#if defined(CONFIG_APP_CAMERA_TEST) && CONFIG_APP_CAMERA_TEST\n    if (bsp_camera_early_init()'),
        ),
    }
    for path, pairs in replacements.items():
        original = path.read_bytes()
        text = original.decode('utf-8').replace('\r\n', '\n')
        if 'CONFIG_B_LAB_SUPPORT' in text or 'B_LAB_ENABLE' in text:
            raise ValueError('Partial lab integration exists; inspect rather than reapply')
        for before, after in pairs:
            if text.count(before) != 1:
                raise ValueError(f'Unexpected integration anchor in {path.name}; no files changed')
            text = text.replace(before, after, 1)
        newline = '\r\n' if b'\r\n' in original else '\n'
        changes[path] = (original, text.replace('\n', newline).encode('utf-8'))
    return changes


def install(sdk, backup_root, check=False):
    revision = subprocess.check_output(['git', '-C', str(sdk), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PIN:
        raise ValueError('Unexpected SDK revision; nothing changed')
    app = sdk/'apps/main'
    changes = edits(app)  # All anchors checked before any mutation.
    sources = sorted((HERE/'firmware').glob('*.[ch]'))
    if {p.name for p in sources} != {'b_lab.c', 'b_lab.h'}:
        raise ValueError('Incomplete lab firmware source')
    if check:
        return None
    backup = backup_root/uuid.uuid4().hex
    backup.mkdir(parents=True)
    manifest = {}
    for path, (before, after) in changes.items():
        (backup/path.name).write_bytes(before)
        manifest[path.name] = {'before_sha256': hashlib.sha256(before).hexdigest(),
                               'after_sha256': hashlib.sha256(after).hexdigest()}
    (backup/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (app/'b_lab').mkdir()  # Refuses an unexpectedly created overlay.
    for path in sources:
        shutil.copy2(path, app/'b_lab'/path.name)
    for path, (_, after) in changes.items():
        path.write_bytes(after)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        backup = install(args.sdk.resolve(), HERE.parents[1]/'.local/lab-sdk-backups', args.check)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))
    print('All integration anchors match; no SDK changes.' if args.check else f'Lab overlay installed; backup: {backup}')


if __name__ == '__main__':
    main()
