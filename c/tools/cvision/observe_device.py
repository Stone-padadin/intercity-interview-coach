"""Passively collect numeric pose diagnostics; never reset, calibrate or send commands.

Raw serial lines (which may contain speech or credentials) are deliberately not saved.
Use one serial owner only; this tool is not a production A/B/D transport.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

POSE = ('frame', 'capture_ms', 'infer_ms', 'status', 'error', 'stable',
        'valid', 'err', 'internal', 'psram')
CAL = ('frame', 'people', 'state', 'samples', 'raw', 'stable', 'valid',
       'angle_md', 'delta_md', 'base_md', 'enter_md', 'noise_md')
B_STATE = ('online', 'phase', 'visual', 'pose', 'led_enabled',
           'internal', 'largest', 'psram')
LIMIT = 8192
CRASH = re.compile(r'Guru Meditation|task_wdt|assert failed|panic(?:ed|:)', re.I)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def parse_line(line):
    """Return whitelisted numeric fields only; never echo an arbitrary log line."""
    if CRASH.search(line):
        return {'kind': 'crash_diagnostic', 'fields': {}}
    if 'CPOSE frame=' in line:
        marker, kind, required = 'CPOSE ', 'pose', POSE
    elif 'CCAL frame=' in line:
        marker, kind, required = 'CCAL ', 'calibration', CAL
    elif 'status online=' in line:
        marker, kind, required = 'status ', 'device_status', B_STATE
    else:
        return None
    tail = line.split(marker, 1)[1]
    pairs = re.findall(r'(\w+)=(-?\d+)(?=\s|$)', tail)
    fields = {key: int(value) for key, value in pairs if key in required}
    if len(fields) != len(required):
        return {'kind': 'malformed_diagnostic', 'fields': {}, 'expected_kind': kind}
    if kind == 'pose':
        valid = (fields['frame'] >= 0 and 0 <= fields['capture_ms'] <= 0xffffffff
                 and fields['infer_ms'] >= 0 and fields['stable'] in (0, 1, 2)
                 and fields['valid'] in (0, 1))
    elif kind == 'calibration':
        valid = (fields['frame'] >= 0 and fields['people'] in (0, 1)
                 and fields['state'] in (0, 1, 2, 3)
                 and fields['samples'] >= 0 and fields['raw'] in (0, 1, 2)
                 and fields['stable'] in (0, 1, 2) and fields['valid'] in (0, 1))
    else:
        valid = (fields['online'] in (0, 1) and fields['visual'] in (0, 1)
                 and fields['led_enabled'] in (0, 1) and fields['pose'] in (0, 1, 2))
    if not valid:
        return {'kind': 'malformed_diagnostic', 'fields': {}, 'expected_kind': kind}
    return {'kind': kind, 'fields': fields}


class Observation:
    def __init__(self, experiment_id=''):
        self.experiment_id = experiment_id
        self.buffer = bytearray()
        self.bytes_received = 0
        self.ignored_lines = 0
        self.overlong_lines = 0
        self.discarding_line = False
        self.events = []
        self.samples = {}
        self.epoch = 0
        self.last_frame = None
        self.frame_regressions = 0

    def feed(self, data, elapsed_ms=0, host_utc=None):
        self.bytes_received += len(data)
        emitted = []
        # Bound a noisy or unterminated log without accepting its tail as a record.
        for byte in data:
            if byte != 10:
                if not self.discarding_line:
                    self.buffer.append(byte)
                    if len(self.buffer) > LIMIT:
                        self.buffer.clear()
                        self.discarding_line = True
                        self.overlong_lines += 1
                continue
            if self.discarding_line:
                self.discarding_line = False
                self.buffer.clear()
                continue
            line = self.buffer.decode('utf-8', errors='replace').rstrip('\r')
            self.buffer.clear()
            parsed = parse_line(line)
            if parsed is None:
                self.ignored_lines += 1
                continue
            fields = parsed['fields']
            if 'frame' in fields:
                frame = fields['frame']
                if self.last_frame is not None and frame < self.last_frame:
                    # May be a reboot or out-of-order diagnostics; do not pair across it.
                    self.epoch += 1
                    self.frame_regressions += 1
                self.last_frame = frame
                self.samples.setdefault((self.epoch, frame), {})[parsed['kind']] = fields
            event = dict(schema_version=1, source='device_numeric_diagnostic',
                         experiment_id=self.experiment_id, host_utc=host_utc or utc_now(),
                         host_elapsed_ms=elapsed_ms, observation_epoch=self.epoch, **parsed)
            self.events.append(event)
            emitted.append(event)
        return emitted

    def summary(self):
        poses = [row['pose'] for row in self.samples.values() if 'pose' in row]
        paired = [row for row in self.samples.values()
                  if 'pose' in row and 'calibration' in row]
        usable = []
        inconsistent = 0
        for row in paired:
            p, c = row['pose'], row['calibration']
            ready = (p['frame'] > 0 and p['valid'] == c['valid'] == 1 and p['err'] == 0
                     and c['people'] == 1 and c['state'] == 2
                     and p['stable'] == c['stable'] and p['stable'] in (1, 2)
                     and c['raw'] in (1, 2))
            if ready:
                usable.append(p)
            elif p['valid'] or c['valid']:
                inconsistent += 1
        counts = {kind: sum(e['kind'] == kind for e in self.events)
                  for kind in ('pose', 'calibration', 'device_status',
                               'malformed_diagnostic', 'crash_diagnostic')}
        issues = []
        if len(poses) < 3:
            issues.append('insufficient_pose_samples')
        if counts['malformed_diagnostic']:
            issues.append('malformed_diagnostic')
        if counts['crash_diagnostic']:
            issues.append('crash_diagnostic')
        if any(p['err'] or p['internal'] <= 0 or p['psram'] <= 0 for p in poses):
            issues.append('inference_or_memory_error')
        if inconsistent:
            issues.append('inconsistent_validity')
        if self.frame_regressions:
            issues.append('frame_sequence_regression')
        statuses = [e['fields'] for e in self.events if e['kind'] == 'device_status']
        return dict(
            schema_version=1, experiment_id=self.experiment_id,
            bytes_received=self.bytes_received, event_counts=counts,
            unique_pose_samples=len(poses), paired_samples=len(paired),
            semantically_usable_samples=len(usable),
            neutral_samples=sum(p['stable'] == 1 for p in usable),
            deviation_samples=sum(p['stable'] == 2 for p in usable),
            unknown_or_unverified_samples=len(poses) - len(usable),
            inconsistent_validity_samples=inconsistent,
            inference_ms_min=min((p['infer_ms'] for p in poses), default=None),
            inference_ms_max=max((p['infer_ms'] for p in poses), default=None),
            frame_sequence_regressions=self.frame_regressions,
            ignored_lines=self.ignored_lines, overlong_lines=self.overlong_lines,
            latest_device_status=statuses[-1] if statuses else None,
            diagnostic_capture_passed=not issues, issues=issues,
            limits=['host_utc is receive time, not camera capture time',
                    'capture_ms is device low-32-bit time, not UTC',
                    'numeric validity does not prove real-person classification accuracy',
                    'no raw logs, images, audio or free-form speech are exported'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--seconds', type=float, default=45)
    parser.add_argument('--experiment-id', default='')
    parser.add_argument('--output-dir', type=Path, default=Path('.local/c-observations'))
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        parser.error('--seconds must be in [1, 3600]')
    import serial  # Optional for offline parsing/tests; pip requirements-preview.txt.
    run = args.output_dir / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True, exist_ok=False)
    observation = Observation(args.experiment_id)
    port = serial.Serial(port=None, baudrate=115200, timeout=.2)
    port.dtr = False
    port.rts = False
    port.port = args.port
    started = time.monotonic()
    capture_error = None
    try:
        port.open()
        with (run / 'events.jsonl').open('w', encoding='utf-8') as output:
            while time.monotonic() - started < args.seconds:
                chunk = port.read(min(max(port.in_waiting, 1), 16384))
                for event in observation.feed(chunk, round((time.monotonic() - started)*1000)):
                    output.write(json.dumps(event, ensure_ascii=False) + '\n')
                output.flush()
    except (serial.SerialException, OSError) as exc:
        # Do not dump arbitrary serial/driver diagnostics into public reports.
        capture_error = type(exc).__name__
    finally:
        port.close()
    result = observation.summary()
    result.update(port=args.port, observed_seconds=round(time.monotonic() - started, 2),
                  commands_sent=0, capture_error=capture_error)
    if capture_error:
        result['diagnostic_capture_passed'] = False
        result['issues'].append('serial_capture_error')
    (run / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(result, output_dir=str(run)), ensure_ascii=False, indent=2))
    return 0 if result['diagnostic_capture_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
