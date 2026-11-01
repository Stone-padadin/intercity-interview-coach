"""Single-instance, local Codex continuation keeper. Never reads credentials.

Only an explicitly published checkpoint may resume. Existing live work is never
interrupted. A reset timestamp is a retry time, not proof of recovered capacity.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time


def quota_snapshot(path):
    """Read only token_count quota metadata; never extract user content or keys."""
    last = None
    with Path(path).open('rb') as stream:
        stream.seek(max(0, stream.seek(0, 2) - 4 * 1024 * 1024))
        for line in stream:
            if b'"rate_limits"' not in line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            data = obj.get('payload', {})
            if obj.get('type') == 'event_msg' and data.get('type') == 'token_count' and data.get('rate_limits'):
                last = {'timestamp': obj.get('timestamp'), 'limits': data['rate_limits']}
    return last


def quota_remaining(snapshot):
    if not snapshot:
        return None
    windows = [snapshot['limits'].get(key) for key in ('primary', 'secondary')]
    values = [100 - float(w['used_percent']) for w in windows if w and isinstance(w.get('used_percent'), (int, float))]
    return min(values) if values else None


def next_reset(snapshot, threshold=10):
    if not snapshot:
        return None
    windows = [snapshot['limits'].get(key) for key in ('primary', 'secondary')]
    resets = [w['resets_at'] for w in windows if w and w.get('used_percent', 0) >= 100-threshold
              and isinstance(w.get('resets_at'), (int, float))]
    return max(resets) if resets else None


def ready(state, now):
    return (state.get('enabled') is True and state.get('checkpoint_pushed') is True
            and state.get('status') in ('waiting_quota', 'waiting_time')
            and isinstance(state.get('resume_after'), (int, float))
            and now >= state['resume_after'])


def atomic_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def launch_args(state):
    session = state['session_id']
    import uuid
    uuid.UUID(session)
    return [state['codex_exe'], '--ask-for-approval', 'never', '--sandbox', 'workspace-write',
            'exec', 'resume', session, '-']


def run(path):
    # File handle lock is released even on crash. No stale pid-based exclusion.
    import msvcrt
    lock = path.with_suffix('.lock').open('a+b')
    if lock.tell() == 0:
        lock.write(b'1'); lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return
    while True:
        state = json.loads(path.read_text(encoding='utf-8'))
        if not state.get('enabled') or state.get('status') in ('complete', 'disabled'):
            return
        if ready(state, time.time()):
            prompt = Path(state['prompt_file']).read_text(encoding='utf-8')
            args = launch_args(state)
            state.update(status='resuming', last_attempt_at=datetime.now(timezone.utc).isoformat())
            atomic_json(path, state)
            # Keep raw CLI messages local; the keeper prints no prompts or tokens.
            with path.with_suffix('.stdout.log').open('ab') as out, path.with_suffix('.stderr.log').open('ab') as err:
                proc = subprocess.Popen(args, cwd=state['workspace'], stdin=subprocess.PIPE,
                                        stdout=out, stderr=err,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                proc.communicate(prompt.encode('utf-8'))
            current = json.loads(path.read_text(encoding='utf-8'))
            if current.get('status') == 'resuming':
                if proc.returncode == 0:
                    current.update(status='awaiting_checkpoint', last_exit_code=0)
                else:
                    current.update(status='waiting_quota', last_exit_code=proc.returncode,
                                   resume_after=time.time()+900)
                atomic_json(path, current)
        time.sleep(30)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--quota-file', type=Path)
    args = parser.parse_args()
    if args.quota_file:
        snapshot = quota_snapshot(args.quota_file)
        print(json.dumps({'snapshot': snapshot, 'remaining_percent': quota_remaining(snapshot),
                          'limiting_reset': next_reset(snapshot)}, ensure_ascii=False))
    elif args.state:
        run(args.state.resolve())
    else:
        parser.error('choose --state or --quota-file')
