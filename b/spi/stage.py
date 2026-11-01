"""Copy an SDK into a new private candidate directory; never changes the source."""
import argparse
import json
import os
from pathlib import Path
import shutil


def stage(source,target):
    source=Path(source).resolve(); target=Path(target).resolve()
    if target.exists() or source==target or source in target.parents:
        raise ValueError('Use a new directory outside the source SDK')
    if not (source/'esp-idf/tools/idf.py').is_file() or not (source/'apps/main/b_device').is_dir():
        raise ValueError('Source must contain an existing reviewed C+B SDK')
    target.parent.mkdir(parents=True,exist_ok=True)
    # No resetting or cleanup of the source. Incomplete copies are left for review.
    # Windows extended paths are needed by the SDK's nested bundled test files.
    copy_source='\\\\?\\'+str(source) if os.name=='nt' else str(source)
    copy_target='\\\\?\\'+str(target) if os.name=='nt' else str(target)
    shutil.copytree(copy_source,copy_target,ignore=shutil.ignore_patterns(
        '.git','.local','__pycache__','build','build-*','.cache','*.pyc'))
    (target/'.spi-workflow-disposable').write_text('Disposable SPI workflow copy\n',encoding='utf-8')
    return {'copied':True,'target':str(target)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-sdk',type=Path,required=True)
    p.add_argument('--target',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(stage(a.source_sdk,a.target)))
