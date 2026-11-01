"""Install the SPI workflow only in a disposable, already integrated C+B SDK copy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
ROLES = ('command', 'state', 'pose', 'calibration', 'samples', 'result')


def mapping_header(path):
    if path is None:
        return (ROOT / 'b/spi/b_spi_mapping.disabled.h').read_text(encoding='utf-8')
    obj = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if obj.get('pid') != 11919:
        raise ValueError('Mapping must be exported/checked for PID 11919')
    if type(obj.get('siid')) is not int or not 1 <= obj['siid'] <= 255:
        raise ValueError('siid must be an actual product service id, 1..255')
    ids = [obj.get(role) for role in ROLES]
    if any(type(x) is not int or not 1 <= x <= 65535 for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('All six property IDs must be distinct actual product IDs')
    lines = ['/* Generated from the checked PID 11919 mapping. */', '#ifndef B_SPI_MAPPING_H',
             '#define B_SPI_MAPPING_H', '#define B_SPI_MAPPING_ENABLED 1',
             '#define B_SPI_SIID ' + str(obj['siid'])]
    lines += ['#define B_SPI_' + role.upper() + '_PIID ' + str(obj[role]) for role in ROLES]
    return '\n'.join(lines + ['#endif', ''])


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError('Unexpected SDK insertion point: ' + label + '; no changes')
    return text.replace(old, new, 1)


def prepare(sdk, mapping=None, check=False):
    sdk = Path(sdk).resolve()
    if not (sdk / '.spi-workflow-disposable').is_file():
        raise ValueError('Only a disposable SDK copy marked .spi-workflow-disposable may be installed')
    if (sdk / '.spi-workflow-installed').exists():
        raise ValueError('Already installed; preserve it and stage a new copy for a new revision')
    main = sdk / 'apps/main'
    hashes=json.loads((ROOT/'b/spi/baseline-sha256.json').read_text(encoding='utf-8'))
    for source, expected in hashes.items():
        name=Path(source).name
        target=main/('b_device' if source.startswith('b/') else 'pose')/name
        # Git baseline is LF; check text content independent of checkout newlines.
        content=target.read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(content).hexdigest()!=expected:
            raise ValueError('Unreviewed source changes would be overwritten: '+name)
    # Plan every edit and validate all anchors before writing anything.
    header = mapping_header(mapping)
    if (main/'b_device/b_spi_mapping.h').exists():
        raise ValueError('Existing platform mapping would be overwritten; use a new disposable copy')
    edits = {}
    cmake = (main / 'CMakeLists.txt').read_text(encoding='utf-8')
    if 'set(B_DEVICE_PROFILE ' not in cmake or '"./b_device/b_device_runtime.c"' not in cmake:
        raise ValueError('Reviewed B integration is required; no changes')
    sources = '''if(B_SPI_WORKFLOW_ENABLE)
    if(NOT B_DEVICE_PROFILE STREQUAL "integrated" OR NOT C_VISION_PROFILE STREQUAL "live")
        message(FATAL_ERROR "SPI workflow requires B integrated and C live")
    endif()
    list(APPEND COMPONENT_SRCS "./b_device/b_spi_workflow.c" "./b_device/b_spi_runtime.c")
endif()

'''
    cmake = replace_once(cmake, 'set(B_DEVICE_PROFILE ',
                         'option(B_SPI_WORKFLOW_ENABLE "SPI control and feedback workflow" OFF)\nset(B_DEVICE_PROFILE ', 'B profile')
    cmake = replace_once(cmake, 'set(COMPONENT_ADD_INCLUDEDIRS', sources + 'set(COMPONENT_ADD_INCLUDEDIRS', 'source list')
    cmake = replace_once(cmake, 'register_component()', '''register_component()
if(B_SPI_WORKFLOW_ENABLE)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE CONFIG_B_SPI_WORKFLOW_SUPPORT=1)
endif()''', 'compile definitions')
    edits[main / 'CMakeLists.txt'] = cmake
    app = (main / 'main.c').read_text(encoding='utf-8')
    app = replace_once(app, '''QM_LOGE("main","live pose init failed");
        return;''', '''QM_LOGE("main","live pose unavailable; continuing voice/cloud startup");''', 'voice fallback')
    app = replace_once(app, '#elif defined(CONFIG_QM_POSE_SUPPORT) && CONFIG_QM_POSE_SUPPORT',
                       '#if CONFIG_B_SPI_WORKFLOW_SUPPORT\n    c_live_pose_set_enabled(false);\n#endif\n#elif defined(CONFIG_QM_POSE_SUPPORT) && CONFIG_QM_POSE_SUPPORT', 'default off before camera startup')
    app = replace_once(app, '''QM_LOGE("main","B runtime init failed");
        return;''', '''QM_LOGE("main","B runtime unavailable; continuing voice/cloud startup");''', 'B runtime fallback')
    app = replace_once(app, 'if (bsp_camera_stream_start()!=ESP_OK)',
                       'if (c_live_pose_is_ready() && bsp_camera_stream_start()!=ESP_OK)', 'camera startup')
    # Avoid allocating camera buffers when the model could not initialize.
    app = replace_once(app, 'if (bsp_camera_early_init() != ESP_OK)',
                       'if (\n#if CONFIG_C_LIVE_POSE_SUPPORT\n        c_live_pose_is_ready() &&\n#endif\n        bsp_camera_early_init() != ESP_OK)', 'early camera')
    edits[main / 'main.c'] = app
    cloud = (main / 'cloud/ljyd_cloud.c').read_text(encoding='utf-8')
    cloud = replace_once(cloud, '#include "ljyd_cloud.h"',
                         '#include "ljyd_cloud.h"\n#if CONFIG_C_LIVE_POSE_SUPPORT\n#include "c_live_pose.h"\n#endif', 'cloud include')
    cloud = replace_once(cloud, 'if (bsp_camera_stream_start() != ESP_OK)',
                         'if (\n#if CONFIG_C_LIVE_POSE_SUPPORT\n                c_live_pose_is_ready() &&\n#endif\n                bsp_camera_stream_start() != ESP_OK)', 'cloud camera startup')
    edits[main / 'cloud/ljyd_cloud.c'] = cloud
    ctrl = (main / 'lj_components/iot_control/iot_control.c').read_text(encoding='utf-8')
    ctrl = replace_once(ctrl, '#include "iot_control.h"',
                        '#include "iot_control.h"\n#if CONFIG_B_SPI_WORKFLOW_SUPPORT\n#include "b_spi_runtime.h"\n#endif', 'IoT include')
    ctrl = replace_once(ctrl, '    for (i = 0; i < QM_ARRAY_SIZE(s_table); i++)',
                        '    #if CONFIG_B_SPI_WORKFLOW_SUPPORT\n    if (b_spi_iot_handle(property)) { return; }\n    #endif\n    for (i = 0; i < QM_ARRAY_SIZE(s_table); i++)', 'IoT dispatch')
    edits[main / 'lj_components/iot_control/iot_control.c'] = ctrl
    # Require exact prior B source, preserving unrelated team changes.
    for name in ('b_device_state.c', 'b_device_state.h', 'b_c_vision.c', 'b_c_vision.h'):
        if (main / 'b_device' / name).read_bytes() != (ROOT / 'b/firmware' / name).read_bytes():
            raise ValueError('B source differs from reviewed version: ' + name)
    for target in edits:
        if target.with_suffix(target.suffix + '.before-spi').exists():
            raise ValueError('Existing backup would be overwritten; use a new disposable copy')
    overlay=[]
    for source in (ROOT/'b/firmware').glob('*.[ch]'):
        target=main/'b_device'/source.name
        if source.name.startswith('b_spi_') and target.exists():
            raise ValueError('Existing SPI module would be overwritten: '+source.name)
        overlay.append((source,target))
    overlay += [(ROOT/'c/firmware/apps/main/pose'/name,main/'pose'/name)
                for name in ('c_live_pose.c','c_live_pose.h')]
    for _,target in overlay:
        if target.with_suffix(target.suffix+'.before-spi').exists():
            raise ValueError('Existing source backup would be overwritten')
    if check:
        return {'checked': True, 'platform_mapping_enabled': mapping is not None}
    for target, text in edits.items():
        shutil.copy2(target, target.with_suffix(target.suffix + '.before-spi'))
        target.write_text(text, encoding='utf-8', newline='\n')
    for source,target in overlay:
        if target.exists():
            shutil.copy2(target,target.with_suffix(target.suffix+'.before-spi'))
        shutil.copy2(source,target)
    (main / 'b_device/b_spi_mapping.h').write_text(header, encoding='utf-8', newline='\n')
    (sdk / '.spi-workflow-installed').write_text('PID11919 candidate; no device writes\n', encoding='utf-8')
    return {'installed': True, 'platform_mapping_enabled': mapping is not None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.sdk, args.mapping, args.check)))
