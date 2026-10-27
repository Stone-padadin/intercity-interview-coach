"""Build/flash B profiles using the project-local, pinned ESP-IDF toolchain."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SDK=ROOT/'external/vendor-sdk'

def environment():
    tools=ROOT/'.local/idf-tools'
    env=os.environ.copy()
    env.update(ADF_PATH=str(SDK),IDF_PATH=str(SDK/'esp-idf'),IDF_TOOLS_PATH=str(tools),
               IDF_COMPONENT_CACHE_PATH=str(ROOT/'.local/component-cache'),PYTHONIOENCODING='utf-8')
    metadata=json.loads((SDK/'esp-idf/tools/tools.json').read_text())
    paths=[]
    for tool in metadata['tools']:
        for version in tool['versions']:
            if version['status']!='recommended': continue
            installed=tools/'tools'/tool['name']/version['name']
            if installed.exists():
                paths.extend(str(installed.joinpath(*p)) for p in tool.get('export_paths',[]))
                for key,value in tool.get('export_vars',{}).items():
                    env[key]=value.replace('${TOOL_PATH}',str(installed))
    candidates=sorted((tools/'python_env').glob('idf5.4_py*_env/Scripts/python.exe'))
    if not candidates: raise SystemExit('Missing project-local IDF Python; see b/README.md')
    python=candidates[-1]
    env['IDF_PYTHON_ENV_PATH']=str(python.parent.parent)
    env['PATH']=os.pathsep.join([str(python.parent),*paths,env.get('PATH','')])
    return python,env

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['build','flash','monitor'])
    parser.add_argument('--profile',choices=['voice','integrated'],default='voice')
    parser.add_argument('--port')
    parser.add_argument('--led',action='store_true',help='Only after checking the real LED wiring/power')
    args=parser.parse_args()
    if args.action!='build' and (not args.port or not re.fullmatch(r'COM[1-9][0-9]*',args.port,re.I)):
        parser.error('Identify the actual board and supply --port COM7')
    python,env=environment()
    for source in (ROOT/'b/firmware').glob('*.[ch]'):
        target=SDK/'apps/main/b_device'/source.name
        if not target.exists() or target.read_bytes()!=source.read_bytes():
            raise SystemExit('SDK B overlay differs from reviewed source; inspect/synchronize it before building')
    # Reuse SDK libraries when switching voice/integrated; keep releases as snapshots.
    build=ROOT/'.local/build-device'
    config=ROOT/'.local/sdkconfig-device'
    if not config.exists(): shutil.copy2(SDK/'apps/sdkconfig',config)
    product=ROOT/'.local/product.json'
    identity=json.loads(product.read_text(encoding='utf-8-sig')) if product.exists() else {'pid':0,'secret':'UNCONFIGURED'}
    pid=identity.get('pid'); secret=identity.get('secret')
    if not isinstance(pid,int) or not 0<=pid<=0xffffffff or not isinstance(secret,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',secret):
        raise SystemExit('Invalid local product configuration')
    if pid==0: print('No team product configured: offline bring-up only; cloud pairing is not ready.')
    cmd=[str(python),str(SDK/'esp-idf/tools/idf.py'),'-C',str(SDK/'apps'),'-B',str(build),
         '-D','CMAKE_NINJA_FORCE_RESPONSE_FILE=ON',
         '-D','SDKCONFIG='+str(config),'-D','C_VISION_PROFILE='+('live' if args.profile=='integrated' else 'baseline'),
         '-D','B_DEVICE_PROFILE='+args.profile,'-D','B_DEVICE_LED_ENABLE='+('ON' if args.led else 'OFF'),
         '-D','XJIANG_CLOUD_PID='+str(pid),'-D','XJIANG_CLOUD_SECERT='+secret]
    if args.port: cmd+=['-p',args.port]
    cmd.append(args.action)
    if args.action=='monitor':
        # Monitor does not configure/build; avoid echoing product overrides there.
        cmd=[str(python),str(SDK/'esp-idf/tools/idf.py'),'-C',str(SDK/'apps'),'-B',str(build),'-p',args.port,'monitor']
        raise SystemExit(subprocess.call(cmd,env=env))
    logs=ROOT/'.local/build-logs';logs.mkdir(exist_ok=True)
    with (logs/(args.profile+'-'+args.action+'.log')).open('w',encoding='utf-8') as log:
        process=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in process.stdout:
            log.write(line)
            print(line.replace(secret,'[REDACTED]'),end='',flush=True)
        raise SystemExit(process.wait())

if __name__=='__main__': main()
