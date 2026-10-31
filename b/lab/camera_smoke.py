"""Private, bounded PC-camera recording check; not the product recorder or an AI detector."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid


def capture(index, seconds, root):
    import cv2
    folder = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    writer = None
    frames, failures, stamps, started = 0, 0, [], time.monotonic()
    movie = folder/'camera.avi'
    try:
        if not camera.isOpened():
            raise RuntimeError('Camera could not be opened; check permissions/other camera processes')
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        camera.set(cv2.CAP_PROP_FPS, 15)
        ok, image = False, None
        for _ in range(10):
            ok, image = camera.read()
        if not ok:
            raise RuntimeError('Camera opened but did not produce a warm-up frame')
        height, width = image.shape[:2]
        writer = cv2.VideoWriter(str(movie), cv2.VideoWriter_fourcc(*'MJPG'), 15, (width, height))
        if not writer.isOpened():
            raise RuntimeError('MJPG recording could not be opened')
        cv2.imwrite(str(folder/'first.jpg'), image)
        started = time.monotonic()
        with (folder/'frame-times.jsonl').open('w', encoding='utf-8') as timeline:
            while time.monotonic()-started < seconds:
                before = time.monotonic()
                ok, image = camera.read()
                stamp = time.monotonic()
                if not ok:
                    failures += 1
                    raise RuntimeError('Camera stopped producing frames; recording is incomplete')
                if image.shape[:2] != (height, width):
                    raise RuntimeError('Camera resolution changed during capture')
                writer.write(image); frames += 1; stamps.append(stamp)
                timeline.write(json.dumps(dict(frame=frames, received_at=datetime.now(timezone.utc).isoformat(),
                                               elapsed_ms=(stamp-started)*1000))+'\n')
                time.sleep(max(0, 1/15-(time.monotonic()-before)))
        elapsed = time.monotonic()-started
        cv2.imwrite(str(folder/'last.jpg'), image)
    finally:
        camera.release()
        if writer:
            writer.release()
    replay = cv2.VideoCapture(str(movie)); decoded = 0
    try:
        while replay.isOpened():
            ok, _ = replay.read()
            if not ok:
                break
            decoded += 1
    finally:
        replay.release()
    gaps = [b-a for a, b in zip(stamps, stamps[1:])]
    result = dict(camera_index=index, backend='DirectShow', width=width, height=height,
                  requested_seconds=seconds, observed_seconds=elapsed, written_frames=frames,
                  decoded_frames=decoded, read_failures=failures, observed_host_fps=frames/elapsed,
                  max_read_gap_ms=max(gaps, default=0)*1000, file_bytes=movie.stat().st_size,
                  verified=decoded == frames and frames > 0, audio_recorded=False,
                  timing='host reception, not sensor exposure', video=str(movie.resolve()),
                  first_image=str((folder/'first.jpg').resolve()), last_image=str((folder/'last.jpg').resolve()))
    (folder/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--seconds', type=int, default=30)
    parser.add_argument('--output', type=Path, default=Path('.local/lab/camera'))
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error('This check is bounded to 1-60 seconds')
    result = capture(args.index, args.seconds, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['verified']:
        raise SystemExit('Recording could not be fully decoded')


if __name__ == '__main__':
    main()
