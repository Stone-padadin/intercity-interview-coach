import unittest
from alert_policy import AlertPolicy, Context, PoseEvent

ON = Context('active', True, True, False)
BUSY = Context('active', True, True, True)
def event(n, ms, state='deviated', valid=True, source='synthetic'):
    return PoseEvent(source, n, ms, state, valid)

class PolicyTests(unittest.TestCase):
    def test_default_voice_off_led_on(self):
        p=AlertPolicy(source='synthetic')
        d=p.update(now_ms=100,context=ON,event=event(1,100))
        self.assertEqual(d.led,'deviated'); self.assertIsNone(d.voice_intent)
        self.assertFalse(d.pending_voice)

    def test_explicit_source_and_cooldown_required(self):
        for kwargs in ({'source':'unknown'}, {'source':'real','cooldown_ms':59999}):
            with self.assertRaises(ValueError):AlertPolicy(**kwargs)

    def test_default_context_suppresses_all(self):
        d=AlertPolicy(source='synthetic',voice_enabled=True).update(
            now_ms=1,context=Context(),event=event(1,1))
        self.assertEqual(d.led,'offline');self.assertIsNone(d.voice_intent)

    def test_phase_and_opt_in_gates(self):
        for c,led in [(Context('review',True,True),'review'),
                      (Context('idle',True,True),'idle'),
                      (Context('active',True,False),'normal')]:
            p=AlertPolicy(source='synthetic',voice_enabled=True)
            d=p.update(now_ms=10,context=c,event=event(1,10))
            self.assertEqual(d.led,led);self.assertFalse(d.pending_voice)
            self.assertIsNone(d.voice_intent)

    def test_one_intent_per_episode(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        first=p.update(now_ms=1,context=ON,event=event(1,1))
        self.assertEqual(first.voice_intent.kind,'posture_deviation')
        # More than cooldown elapsed is still the same episode.
        d=p.update(now_ms=70000,context=ON,event=event(2,70000))
        self.assertIsNone(d.voice_intent)

    def test_recovery_rearms_but_cooldown_blocks(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=100,context=ON,event=event(1,100))
        p.update(now_ms=200,context=ON,event=event(2,200,'normal'))
        d=p.update(now_ms=300,context=ON,event=event(3,300))
        self.assertIsNone(d.voice_intent);self.assertTrue(d.pending_voice)
        d=p.update(now_ms=60099,context=ON,event=event(4,60099))
        self.assertIsNone(d.voice_intent)
        d=p.update(now_ms=60100,context=ON)
        self.assertIsNotNone(d.voice_intent)

    def test_busy_defers_until_silent(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        d=p.update(now_ms=100,context=BUSY,event=event(1,100))
        self.assertTrue(d.pending_voice);self.assertIsNone(d.voice_intent)
        d=p.update(now_ms=200,context=ON)
        self.assertIsNotNone(d.voice_intent);self.assertFalse(d.pending_voice)

    def test_busy_pending_expires_without_dispatch(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=1,context=BUSY,event=event(1,1))
        d=p.update(now_ms=6002,context=ON)
        self.assertEqual(d.led,'unknown');self.assertFalse(d.pending_voice)
        self.assertIsNone(d.voice_intent)

    def test_exact_expiration_boundary(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=10,context=BUSY,event=event(1,10))
        self.assertIsNotNone(p.update(now_ms=6010,context=ON).voice_intent)

    def test_fresh_event_after_expiration_can_remind_unissued_episode(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=1,context=BUSY,event=event(1,1))
        p.update(now_ms=7000,context=ON)
        d=p.update(now_ms=7001,context=ON,event=event(2,7001))
        self.assertIsNotNone(d.voice_intent)

    def test_disconnect_and_opt_out_cancel_immediately(self):
        for c in (Context('active',False,True),Context('active',True,False)):
            p=AlertPolicy(source='synthetic',voice_enabled=True)
            p.update(now_ms=1,context=BUSY,event=event(1,1))
            d=p.update(now_ms=2,context=c)
            self.assertFalse(d.pending_voice);self.assertIsNone(d.voice_intent)
            d=p.update(now_ms=3,context=ON)
            self.assertEqual(d.pose,'unknown');self.assertIsNone(d.voice_intent)
            d=p.update(now_ms=4,context=ON,event=event(1,1))
            self.assertEqual(d.event_status,'duplicate_or_reordered')
            self.assertIsNone(d.voice_intent)

    def test_review_cancels_pending(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=1,context=BUSY,event=event(1,1))
        d=p.update(now_ms=2,context=Context('review',True,True))
        self.assertFalse(d.pending_voice);self.assertIsNone(d.voice_intent)

    def test_voice_disable_cancels_pending(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=1,context=BUSY,event=event(1,1));p.set_voice_enabled(False)
        d=p.update(now_ms=2,context=ON)
        self.assertFalse(d.pending_voice);self.assertIsNone(d.voice_intent)

    def test_invalid_unknown_malformed_cancel(self):
        for bad in (event(2,2,valid=False),event(2,2,'unknown'),event(2,2,'wiring_fault')):
            p=AlertPolicy(source='synthetic',voice_enabled=True)
            p.update(now_ms=1,context=BUSY,event=event(1,1))
            d=p.update(now_ms=2,context=ON,event=bad)
            self.assertEqual(d.pose,'unknown');self.assertFalse(d.pending_voice)
            self.assertIsNone(d.voice_intent)

    def test_unknown_does_not_rearm_issued_episode(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=1,context=ON,event=event(1,1))
        p.update(now_ms=2,context=ON,event=event(2,2,'unknown'))
        d=p.update(now_ms=70000,context=ON,event=event(3,70000))
        self.assertIsNone(d.voice_intent)

    def test_out_of_order_normal_cannot_rearm(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        p.update(now_ms=10,context=ON,event=event(2,10))
        d=p.update(now_ms=11,context=ON,event=event(1,9,'normal'))
        self.assertEqual(d.event_status,'duplicate_or_reordered');self.assertEqual(d.pose,'deviated')
        self.assertIsNone(p.update(now_ms=70000,context=ON,event=event(3,70000)).voice_intent)

    def test_duplicate_frame_cannot_refresh_expiry(self):
        p=AlertPolicy(source='synthetic')
        p.update(now_ms=10,context=ON,event=event(1,10))
        d=p.update(now_ms=6000,context=ON,event=event(1,6000))
        self.assertEqual(d.event_status,'duplicate_or_reordered')
        self.assertEqual(p.update(now_ms=6011,context=ON).pose,'unknown')

    def test_future_and_stale_not_accepted(self):
        p=AlertPolicy(source='synthetic',voice_enabled=True)
        for e,status in [(event(1,10001),'future'),(event(2,1),'stale')]:
            d=p.update(now_ms=10000,context=ON,event=e)
            self.assertEqual(d.event_status,status);self.assertEqual(d.pose,'unknown')
            self.assertIsNone(d.voice_intent)

    def test_source_isolation(self):
        p=AlertPolicy(source='real',voice_enabled=True)
        d=p.update(now_ms=1,context=ON,event=event(1,1))
        self.assertEqual(d.event_status,'wrong_source');self.assertIsNone(d.voice_intent)
        d=p.update(now_ms=2,context=ON,event=event(1,2,source='real'))
        self.assertEqual(d.voice_intent.source,'real')

    def test_bad_clock_and_context_raise(self):
        p=AlertPolicy(source='synthetic')
        p.update(now_ms=20,context=ON)
        with self.assertRaises(ValueError):p.update(now_ms=19,context=ON)
        with self.assertRaises(ValueError):p.update(now_ms=20,context=Context('bad',True,True))

    def test_intent_has_source_frame_expiry_and_no_wiring_claim(self):
        d=AlertPolicy(source='synthetic',voice_enabled=True).update(
            now_ms=10,context=ON,event=event(1,10))
        i=d.to_dict()['voice_intent']
        self.assertEqual(i['source'],'synthetic');self.assertEqual(i['frame_id'],1)
        self.assertEqual(i['expires_ms'],6010);self.assertNotIn('接线',i['text'])

if __name__=='__main__':unittest.main()
