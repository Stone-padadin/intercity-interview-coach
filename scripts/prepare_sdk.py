"""Prepare a clean, pinned upstream SDK without touching existing dirty work."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def git(sdk, *args):
    return subprocess.check_output(['git', '-C', str(sdk), *args], text=True).strip()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk', type=Path, default=ROOT / 'external/vendor-sdk')
    p.add_argument('--clone', action='store_true')
    p.add_argument('--check-only', action='store_true')
    args = p.parse_args()
    spec = json.loads((ROOT / 'c/firmware/upstream.json').read_text())
    sdk = args.sdk.resolve()
    if args.clone:
        if sdk.exists():
            raise SystemExit('Clone target already exists; refusing to overwrite it')
        subprocess.run(['git', 'clone', spec['url'], str(sdk)], check=True)
        subprocess.run(['git', '-C', str(sdk), 'checkout', '--detach', spec['commit']], check=True)
    if git(sdk, 'rev-parse', 'HEAD') != spec['commit']:
        raise SystemExit('SDK version differs from locked commit; no files changed')
    if git(sdk, 'status', '--porcelain'):
        raise SystemExit('SDK is dirty; review existing work before integrating')
    patch = ROOT / 'c/firmware/vendor-integration.patch'
    subprocess.run(['git', '-C', str(sdk), 'apply', '--check', str(patch)], check=True)
    overlay = ROOT / 'c/firmware/apps/main'
    for source in overlay.rglob('*'):
        if source.is_file() and (sdk / 'apps/main' / source.relative_to(overlay)).exists():
            raise SystemExit('Overlay target already exists; refusing to overwrite it')
    if args.check_only:
        print('Pinned SDK and integration patch: PASS (no changes)')
        return
    subprocess.run(['git', '-C', str(sdk), 'apply', str(patch)], check=True)
    shutil.copytree(overlay, sdk / 'apps/main', dirs_exist_ok=True)
    print('C integration applied. Build/flash and physical tests are separate steps.')

if __name__ == '__main__':
    main()
