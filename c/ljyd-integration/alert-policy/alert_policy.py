"""Software-only posture reminder policy. No device, network, audio, or browser I/O."""
from dataclasses import dataclass, asdict
from typing import Literal

Source = Literal['synthetic', 'real']
State = Literal['normal', 'deviated', 'unknown']
Phase = Literal['active', 'review', 'idle']

@dataclass(frozen=True)
class PoseEvent:
    source: Source
    frame_id: int
    captured_ms: int
    state: State
    valid: bool

@dataclass(frozen=True)
class Context:
    phase: Phase = 'idle'
    online: bool = False
    visual_opt_in: bool = False
    assistant_speaking: bool = False

@dataclass(frozen=True)
class VoiceIntent:
    kind: str
    source: Source
    frame_id: int
    captured_ms: int
    expires_ms: int
    text: str

@dataclass(frozen=True)
class Decision:
    led: str
    pose: State
    event_status: str
    pending_voice: bool
    voice_intent: VoiceIntent | None = None
    cancel_voice: bool = False

    def to_dict(self):
        return asdict(self)

class AlertPolicy:
    """One instance per source and session; caller supplies a monotonic clock.

    Returning an intent consumes the episode's one-shot allowance, not proof of
    speech. A future scheduler must revalidate the latest context and expiration.
    """
    STALE_MS = 6000
    MIN_COOLDOWN_MS = 60000

    def __init__(self, *, source: Source, voice_enabled: bool = False,
                 cooldown_ms: int = MIN_COOLDOWN_MS):
        if source not in ('synthetic', 'real'):
            raise ValueError('source must be explicit: synthetic or real')
        if type(voice_enabled) is not bool:
            raise ValueError('voice_enabled must be boolean')
        if type(cooldown_ms) is not int or cooldown_ms < self.MIN_COOLDOWN_MS:
            raise ValueError('cooldown must be at least 60000 ms')
        self.source = source
        self.voice_enabled = voice_enabled
        self.cooldown_ms = cooldown_ms
        self._last_now = -1
        self._last_capture = -1
        self._last_frame = 0
        self._pose: PoseEvent | None = None
        self._episode = False
        self._issued = False
        self._pending: PoseEvent | None = None
        self._last_intent_ms: int | None = None

    def set_voice_enabled(self, enabled: bool):
        if type(enabled) is not bool:
            raise ValueError('enabled must be boolean')
        self.voice_enabled = enabled
        if not enabled:
            self._pending = None

    @staticmethod
    def _event_shape(e):
        return (isinstance(e, PoseEvent) and e.source in ('synthetic', 'real')
                and type(e.frame_id) is int and e.frame_id > 0
                and type(e.captured_ms) is int and e.captured_ms >= 0
                and e.state in ('normal', 'deviated', 'unknown')
                and type(e.valid) is bool)

    def update(self, *, now_ms: int, context: Context,
               event: PoseEvent | None = None) -> Decision:
        if type(now_ms) is not int or now_ms < 0 or now_ms < self._last_now:
            raise ValueError('now_ms must be a nondecreasing monotonic millisecond clock')
        if not isinstance(context, Context) or context.phase not in ('active', 'review', 'idle'):
            raise ValueError('invalid context phase')
        if any(type(v) is not bool for v in (context.online, context.visual_opt_in,
                                             context.assistant_speaking)):
            raise ValueError('context flags must be boolean')
        self._last_now = now_ms
        allowed = context.online and context.visual_opt_in and context.phase == 'active'
        status = 'no_event'
        # Disabling/disconnecting invalidates cached observations and pending
        # reminders; reopening requires a genuinely newer event.
        if not allowed:
            self._pose = None
            self._pending = None
            if event is not None:
                status = 'suppressed'
            led = 'offline' if not context.online else context.phase if context.phase != 'active' else 'normal'
            return Decision(led, 'unknown', status, False)

        if event is not None:
            if not self._event_shape(event):
                status = 'malformed'
                self._pose = self._pending = None
            elif event.source != self.source:
                status = 'wrong_source'
            elif event.captured_ms > now_ms:
                status = 'future'
            elif now_ms - event.captured_ms > self.STALE_MS:
                status = 'stale'
            elif event.frame_id <= self._last_frame or event.captured_ms <= self._last_capture:
                status = 'duplicate_or_reordered'
            else:
                self._last_frame = event.frame_id
                self._last_capture = event.captured_ms
                if not event.valid or event.state == 'unknown':
                    status = 'invalid_or_unknown'
                    self._pose = self._pending = None
                    # Unknown cannot prove recovery and rearm an issued episode.
                else:
                    status = 'accepted'
                    self._pose = event
                    if event.state == 'normal':
                        self._episode = self._issued = False
                        self._pending = None
                    elif not self._episode:
                        self._episode = True
                        self._issued = False

        if self._pose is not None and now_ms - self._pose.captured_ms > self.STALE_MS:
            self._pose = self._pending = None
        pose = self._pose.state if self._pose is not None else 'unknown'
        if not self.voice_enabled or pose != 'deviated':
            self._pending = None
        elif not self._issued:
            # Only a currently usable stable deviation can create/refresh work.
            self._pending = self._pose
        intent = None
        if self._pending is not None:
            e = self._pending
            if now_ms > e.captured_ms + self.STALE_MS:
                self._pending = None
            elif not context.assistant_speaking and (
                    self._last_intent_ms is None or
                    now_ms - self._last_intent_ms >= self.cooldown_ms):
                intent = VoiceIntent('posture_deviation', e.source, e.frame_id,
                                     e.captured_ms, e.captured_ms + self.STALE_MS,
                                     '检测到持续肩线侧倾，可以调整一下坐姿。')
                self._issued = True
                self._last_intent_ms = now_ms
                self._pending = None
        return Decision(pose, pose, status, self._pending is not None, intent)
