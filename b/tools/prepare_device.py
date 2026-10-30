"""Apply B only over an exact, unmodified C integration of the pinned SDK."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]

def git(sdk,*args):
    return subprocess.check_output(['git','-C',str(sdk),*args],text=True,encoding='utf-8').strip()

def normalized(text):
    # Hash abbreviation varies with Git's object count; compare every content/mode hunk.
    return '\n'.join(line for line in text.replace('\r\n','\n').splitlines()
                     if not line.startswith('index ')).strip()

def prepare(sdk,check_only=False):
    spec=json.loads((ROOT/'c/firmware/upstream.json').read_text())
    if git(sdk,'rev-parse','HEAD')!=spec['commit']:
        raise SystemExit('SDK revision differs from C pin; no changes')
    if git(sdk,'diff','--cached','--name-only'):
        raise SystemExit('SDK has staged work; no changes')
    expected=(ROOT/'c/firmware/vendor-integration.patch').read_text(encoding='utf-8')
    if normalized(git(sdk,'diff','--binary','HEAD'))!=normalized(expected):
        raise SystemExit('SDK tracked changes must match C integration exactly; preserve/review existing work')
    overlay=ROOT/'c/firmware/apps/main'
    expected_files={('apps/main/'+p.relative_to(overlay).as_posix()):p
                    for p in overlay.rglob('*') if p.is_file()}
    actual=set(git(sdk,'ls-files','--others','--exclude-standard').splitlines())
    if actual!=set(expected_files):
        raise SystemExit('SDK has unexpected or missing untracked files; no changes')
    for name,source in expected_files.items():
        if (sdk/name).read_bytes()!=source.read_bytes():
            raise SystemExit('C overlay differs from reviewed source; no changes')
    target=sdk/'apps/main/b_device'
    if target.exists():
        raise SystemExit('B target already exists; inspect it instead of overwriting')
    patch=ROOT/'b/firmware/vendor-integration.patch'
    subprocess.run(['git','-C',str(sdk),'apply','--check',str(patch)],check=True)
    if check_only:
        print('Exact C baseline and B patch: PASS; no files changed')
        return
    subprocess.run(['git','-C',str(sdk),'apply',str(patch)],check=True)
    target.mkdir()
    for source in (ROOT/'b/firmware').glob('*.[ch]'):
        shutil.copy2(source,target/source.name)
    print('B integration applied; LED disabled by default. Build and physical checks remain separate.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,default=ROOT/'external/vendor-sdk')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    prepare(args.sdk.resolve(),args.check_only)
