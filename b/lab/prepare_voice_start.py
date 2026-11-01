"""Install an optional queued manual wake entry, preserving modified SDK files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

PIN='06065ce9c5aa1e14cfae5c0ad574bad4aaaae34c'
ANCHOR='int agent_app_init(void *iot_handle)\n{'
ENTRY='''/* Queue the same worker action as a physical wake; no blocking on CLI. */
int agent_app_request_wakeup(void)
{
    if (!s_worker_ready || s_agent == NULL || !s_cloud_connected) {
        return -QM_EINIT;
    }
    return qm_sem_signal(&s_worker_sem);
}

'''
def edits(app):
    path=app/'agent/agent_app.c';before=path.read_bytes()
    text=before.decode('utf-8').replace('\r\n','\n')
    if 'agent_app_request_wakeup' in text or text.count(ANCHOR)!=1:
        raise ValueError('Existing or unexpected voice-start integration; inspect without overwriting')
    for marker in ('static void agent_handle_wakeup(void)','agent_handle_wakeup();','s_worker_sem','s_cloud_connected'):
        if marker not in text:raise ValueError('Required reviewed agent worker missing')
    after=text.replace(ANCHOR,ENTRY+ANCHOR,1)
    newline='\r\n' if b'\r\n' in before else '\n'
    return path,before,after.replace('\n',newline).encode('utf-8')
def install(sdk,backup_root,check=False):
    head=subprocess.check_output(['git','-C',str(sdk),'rev-parse','HEAD'],text=True).strip()
    if head!=PIN:raise ValueError('Unexpected SDK revision')
    path,before,after=edits(sdk/'apps/main')
    if check:return None
    folder=backup_root/uuid.uuid4().hex;folder.mkdir(parents=True)
    (folder/'agent_app.c').write_bytes(before)
    (folder/'manifest.json').write_text(json.dumps({'path':str(path),'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest()},indent=2))
    path.write_bytes(after)
    return folder
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',type=Path,required=True);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    print(install(args.sdk.resolve(),Path(__file__).resolve().parents[2]/'.local/voice-start-sdk-backups',args.check))
