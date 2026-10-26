"""Validate the CPOSE serial event contract and summarize a short hardware run."""
import argparse
import json
from pathlib import Path
import re

PATTERN=re.compile(r'CPOSE frame=(\d+) capture_ms=(\d+) infer_ms=(\d+) '
    r'status=(\d+) error=(\d+) stable=(\d+) valid=(\d+) err=(-?\d+) internal=(\d+) psram=(\d+)')
FIELDS=('frame','capture_ms','infer_ms','status','error','stable','valid','err','internal','psram')

def check(text):
    if re.search(r'task_wdt|Guru Meditation|assert failed|panic.ed',text):
        raise ValueError('Watchdog or crash diagnostics found')
    events=[]
    for line in text.splitlines():
        if 'CPOSE frame=' not in line: continue
        match=PATTERN.search(line)
        if not match: raise ValueError('Malformed CPOSE fields: '+line[:200])
        event=dict(zip(FIELDS,map(int,match.groups())))
        if event['err'] or event['internal']<=0 or event['psram']<=0:
            raise ValueError('Inference error or invalid memory measurement: '+str(event))
        if event['status'] in (0,3) and event['valid']:
            raise ValueError('No-person or unknown frame was marked valid')
        events.append(event)
    if len(events)<3: raise ValueError('Need at least three complete inference events')
    return {
        'events':len(events),
        'inference_ms_min':min(e['infer_ms'] for e in events),
        'inference_ms_max':max(e['infer_ms'] for e in events),
        'no_person_events':sum(e['status']==0 for e in events),
        'internal_free_min':min(e['internal'] for e in events),
        'psram_free_min':min(e['psram'] for e in events),
    }

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path)
    args=parser.parse_args()
    print(json.dumps(check(args.log.read_text(encoding='utf-8',errors='replace')),indent=2))
