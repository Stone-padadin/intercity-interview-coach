"""Safety-relevant tests for passive diagnostic observation, not model accuracy."""
import json
import unittest
from observe_device import LIMIT, Observation, parse_line


def pose(frame=1, **changes):
    values = dict(frame=frame, capture_ms=1000*frame, infer_ms=2500, status=1,
                  error=0, stable=1, valid=1, err=0, internal=100000, psram=1000000)
    values.update(changes)
    return 'I CPOSE ' + ' '.join(f'{k}={v}' for k, v in values.items()) + '\n'


def cal(frame=1, **changes):
    values = dict(frame=frame, people=1, state=2, samples=10, raw=1, stable=1,
                  valid=1, angle_md=-100, delta_md=0, base_md=-100,
                  enter_md=12000, noise_md=0)
    values.update(changes)
    return 'I CCAL ' + ' '.join(f'{k}={v}' for k, v in values.items()) + '\n'


class ObservationTests(unittest.TestCase):
    def test_empty_is_not_success(self):
        self.assertFalse(Observation().summary()['diagnostic_capture_passed'])

    def test_unknown_and_unrelated_logs_do_not_leak(self):
        o = Observation()
        o.feed(b'ASR final=1 text=private words\npassword=secret\n')
        self.assertEqual(o.events, [])
        self.assertNotIn('private words', json.dumps(o.summary()))

    def test_whitelist_extra_fields(self):
        line = pose().strip() + ' token=123\n'
        self.assertNotIn('token', parse_line(line)['fields'])

    def test_fragmented_utf8_and_lines(self):
        data = ('诊断 ' + pose()).encode()
        o = Observation()
        for byte in data:
            o.feed(bytes([byte]), 10, 'fixed-time')
        self.assertEqual(len(o.events), 1)
        self.assertEqual(o.events[0]['host_utc'], 'fixed-time')

    def test_missing_field_is_not_silently_accepted(self):
        self.assertEqual(parse_line(pose().replace('valid=1 ', ''))['kind'], 'malformed_diagnostic')

    def test_invalid_enum_is_malformed(self):
        self.assertEqual(parse_line(cal(people=2))['kind'], 'malformed_diagnostic')

    def test_unknown_is_never_counted_usable(self):
        o = Observation()
        o.feed((pose(valid=0, stable=0) + cal(valid=0, raw=0, stable=0)).encode())
        self.assertEqual(o.summary()['semantically_usable_samples'], 0)

    def test_pose_alone_does_not_prove_calibrated(self):
        o = Observation()
        o.feed(pose().encode())
        self.assertEqual(o.summary()['semantically_usable_samples'], 0)
        # The firmware getter and B adapter also reject a zero frame identifier.
        zero = Observation()
        zero.feed((pose(0) + cal(0)).encode())
        self.assertEqual(zero.summary()['semantically_usable_samples'], 0)

    def test_valid_but_no_person_is_inconsistent(self):
        o = Observation()
        o.feed((pose() + cal(people=0)).encode())
        self.assertIn('inconsistent_validity', o.summary()['issues'])

    def test_pair_must_have_same_frame(self):
        o = Observation()
        o.feed((pose(1) + cal(2)).encode())
        self.assertEqual(o.summary()['paired_samples'], 0)

    def test_duplicate_does_not_inflate_samples(self):
        o = Observation()
        o.feed((pose() + cal() + pose() + cal()).encode())
        self.assertEqual(o.summary()['unique_pose_samples'], 1)
        self.assertEqual(o.summary()['semantically_usable_samples'], 1)

    def test_sequence_regression_never_pairs_old_calibration(self):
        o = Observation()
        o.feed((cal(1) + pose(20) + pose(1)).encode())
        self.assertEqual(o.summary()['paired_samples'], 0)
        self.assertIn('frame_sequence_regression', o.summary()['issues'])

    def test_crash_is_not_hidden_by_later_recovery(self):
        o = Observation()
        o.feed(('Guru Meditation private data\n' + pose() + cal()).encode())
        self.assertIn('crash_diagnostic', o.summary()['issues'])
        self.assertNotIn('private data', json.dumps(o.events))

    def test_overlong_line_tail_is_not_treated_as_sample(self):
        o = Observation()
        o.feed(b'x' * (LIMIT + 1) + pose().encode() + pose(2).encode())
        self.assertEqual(o.summary()['unique_pose_samples'], 1)
        self.assertEqual(o.summary()['overlong_lines'], 1)

    def test_complete_capture_with_deviation(self):
        o = Observation('experiment')
        for frame in range(1, 4):
            state = 2 if frame == 3 else 1
            o.feed((pose(frame, stable=state) + cal(frame, stable=state, raw=state)).encode())
        s = o.summary()
        self.assertTrue(s['diagnostic_capture_passed'])
        self.assertEqual(s['neutral_samples'], 2)
        self.assertEqual(s['deviation_samples'], 1)

    def test_negative_error_and_bad_memory_fail(self):
        o = Observation()
        o.feed(pose(err=-1, internal=0).encode())
        self.assertIn('inference_or_memory_error', o.summary()['issues'])

    def test_device_status_does_not_substitute_pose(self):
        o = Observation()
        o.feed(b'B status online=1 phase=0 visual=0 pose=0 led_enabled=0 internal=1 largest=1 psram=1\n')
        self.assertEqual(o.summary()['latest_device_status']['online'], 1)
        self.assertFalse(o.summary()['diagnostic_capture_passed'])


if __name__ == '__main__':
    unittest.main()
