"""Compile the opt-in lab overlay; deliberately does not flash or change provisioning."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools-root', type=Path, default=ROOT,
                        help='Existing reviewed B checkout containing its local IDF tools and product config')
    parser.add_argument('--profile', choices=['voice', 'integrated'], default='voice')
    args = parser.parse_args()
    tools = args.tools_root.resolve()
    spec = importlib.util.spec_from_file_location('existing_b_firmware', tools/'b/tools/firmware.py')
    firmware = importlib.util.module_from_spec(spec); spec.loader.exec_module(firmware)
    sdk = tools/'external/vendor-sdk'
    for name in ('b_lab.c', 'b_lab.h'):
        if (sdk/'apps/main/b_lab'/name).read_bytes() != (ROOT/'b/lab/firmware'/name).read_bytes():
            raise SystemExit('SDK lab sources differ; preserve and inspect them before building')
    if 'B_LAB_ENABLE' not in (sdk/'apps/main/CMakeLists.txt').read_text(encoding='utf-8'):
        raise SystemExit('Lab integration is missing')
    python, env = firmware.environment()
    # Older reviewed helpers do not remove diagnostic Python packages themselves.
    env.pop('PYTHONPATH', None)
    pid, secret = firmware.product_identity(tools/'.local/product.json')
    folder = ROOT/'.local'; folder.mkdir(exist_ok=True)
    config = folder/'sdkconfig-lab'
    if not config.exists():
        original = tools/'.local/sdkconfig-device'
        shutil.copy2(original if original.exists() else sdk/'apps/sdkconfig', config)
    log_path = folder/f'lab-build-{args.profile}.log'
    cmd = [str(python), str(sdk/'esp-idf/tools/idf.py'), '-C', str(sdk/'apps'),
           '-B', str(folder/'build-lab'), '-D', 'CMAKE_NINJA_FORCE_RESPONSE_FILE=ON',
           '-D', 'SDKCONFIG='+str(config), '-D', 'B_LAB_ENABLE=ON',
           '-D', 'B_DEVICE_PROFILE='+args.profile, '-D', 'B_DEVICE_LED_ENABLE=OFF',
           '-D', 'C_VISION_PROFILE='+('live' if args.profile == 'integrated' else 'baseline'),
           '-D', 'XJIANG_CLOUD_PID='+str(pid), '-D', 'XJIANG_CLOUD_SECERT='+secret, 'build']
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace')
        for line in process.stdout:
            safe = line.replace(secret, '[REDACTED]')
            log.write(safe); print(safe, end='', flush=True)
        result = process.wait()
    print('Build only; board and provisioning were not touched.')
    raise SystemExit(result)


if __name__ == '__main__':
    main()
