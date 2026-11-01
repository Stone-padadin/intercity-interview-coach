"""Build a private SPI candidate with existing IDF tools. No flash/monitor actions."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def build(sdk,output,tools_root,identity=None,rebuild=False):
    sdk=Path(sdk).resolve(); output=Path(output).resolve(); tools_root=Path(tools_root).resolve()
    if not (sdk/'.spi-workflow-installed').is_file():
        raise ValueError('Prepare the disposable SDK first')
    if output.exists() and not rebuild:
        raise ValueError('Keep existing build output; choose a new candidate directory')
    if rebuild and not (output/'validation.json').is_file():
        raise ValueError('Rebuild requires a completed candidate validation manifest')
    if identity:
        obj=json.loads(Path(identity).read_text(encoding='utf-8-sig'))
        if obj.get('pid')!=11919 or not isinstance(obj.get('secret'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,32}',obj['secret']):
            raise ValueError('Expected a local PID11919 identity with a valid 8..32 byte secret')
        pid,secret=11919,obj['secret']
    else:
        pid,secret=0,'UNCONFIGURED'
    if rebuild:
        previous=json.loads((output/'validation.json').read_text(encoding='utf-8'))
        if previous.get('pid')!=pid or previous.get('device_written') is not False:
            raise ValueError('Rebuild cannot change a deployed image or switch product identity')
    # Candidate-only header injection, never credentials in a process command line.
    cloud=sdk/'apps/main/cloud/ljyd_cloud.h'
    source=cloud.read_text(encoding='utf-8')
    for macro,value in [('CONFIG_XJIANG_CLOUD_PID',str(pid)),('CONFIG_XJIANG_CLOUD_SECERT','"'+secret+'"')]:
        source,count=re.subn(r'(?m)^\s*#define\s+'+macro+r'\s+[^\r\n]+', '#define '+macro+' '+value,source)
        if count!=1: raise ValueError('Unknown candidate identity header layout')
    env=dict(os.environ)
    env.pop('PYTHONPATH',None)
    env.update(PYTHONNOUSERSITE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',
               ADF_PATH=str(sdk),IDF_PATH=str(sdk/'esp-idf'),
               IDF_TOOLS_PATH=str(tools_root/'idf-tools'),
               IDF_PYTHON_ENV_PATH=str(tools_root/'idf-python'),IDF_CCACHE_ENABLE='0')
    python=tools_root/'idf-python/Scripts/python.exe'
    if not python.is_file(): raise ValueError('Existing IDF Python required; no toolchain installation is performed')
    metadata=json.loads((sdk/'esp-idf/tools/tools.json').read_text(encoding='utf-8'))
    paths=[str(python.parent)]
    for tool in metadata['tools']:
        for version in tool['versions']:
            if version['status']!='recommended': continue
            installed=tools_root/'idf-tools/tools'/tool['name']/version['name']
            if installed.exists():
                paths += [str(installed.joinpath(*path)) for path in tool.get('export_paths',[])]
                for key,value in tool.get('export_vars',{}).items():
                    env[key]=value.replace('${TOOL_PATH}',str(installed))
    # This machine may keep CMake/Ninja in the existing Conda distribution.
    for path in [tools_root/'conda-env/Library/bin',tools_root/'conda-env/Scripts',
                 tools_root/'conda-env/Lib/site-packages/cmake/data/bin']:
        if path.is_dir(): paths.append(str(path))
    output.mkdir(parents=True,exist_ok=rebuild)
    env.update(IDF_COMPONENT_CACHE_PATH=str(output/'component-cache'))
    env['PATH']=os.pathsep.join(paths+[env.get('PATH','')])
    config=output/'sdkconfig'
    if not rebuild:
        shutil.copy2(sdk/'apps/sdkconfig',config)
    cloud.write_text(source,encoding='utf-8',newline='\n')
    args=[str(python),str(sdk/'esp-idf/tools/idf.py'),'-C',str(sdk/'apps'),
          '-B',str(output/'build'),'-D','CMAKE_NINJA_FORCE_RESPONSE_FILE=ON',
          '-D','SDKCONFIG='+str(config),'-D','B_DEVICE_PROFILE=integrated',
          '-D','C_VISION_PROFILE=live','-D','B_SPI_WORKFLOW_ENABLE=ON',
          '-D','B_DEVICE_LED_ENABLE=OFF','-D','B_LAB_ENABLE=OFF','build']
    print('Building SPI candidate; '+('PID11919 identity configured' if identity else 'OFFLINE PID0 validation only')+'; no device writes',flush=True)
    with (output/'build.private.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in proc.stdout:
            safe=line.replace(secret,'[REDACTED]')
            log.write(safe)
            if any(word in safe.lower() for word in ['error:','fatal error','failed','project build complete','warning:']):
                print(safe.rstrip()[:700],flush=True)
        code=proc.wait()
    result={'build_exit_code':code,'pid':pid,'offline_validation_only':identity is None,
            'profile':'integrated','spi_workflow':True,'led_enabled':False,
            'device_written':False,'hardware_validated':False,'platform_mapping_enabled':
            '#define B_SPI_MAPPING_ENABLED 1' in (sdk/'apps/main/b_device/b_spi_mapping.h').read_text(encoding='utf-8')}
    (output/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return code


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tools-root',type=Path,required=True)
    p.add_argument('--identity',type=Path)
    p.add_argument('--rebuild',action='store_true')
    a=p.parse_args()
    raise SystemExit(build(a.sdk,a.output,a.tools_root,a.identity,a.rebuild))
