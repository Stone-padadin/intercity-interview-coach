import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("check_device", Path(__file__).resolve().parents[1] / "tools/check_device.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeviceLogTests(unittest.TestCase):
    def test_tagless_qm_status_and_camera_results(self):
        result = module.summarize("[000313]<I> runtime started; visual defaults off\n[000303]<I> status online=0 phase=0 visual=0 pose=0 led_enabled=0 internal=12\nI (10) c_live_pose: CPOSE frame=1\n")
        self.assertEqual(result["runtime_starts"], 1)
        self.assertEqual(result["last_status"]["online"], 0)
        self.assertEqual(result["pose_results"], 1)

    def test_ready_does_not_mean_valid_or_neutral(self):
        result = module.summarize("CCAL frame=1 state=2 samples=10 stable=0 valid=0\nCCAL frame=2 state=2 samples=10 stable=2 valid=1\nCCAL frame=3 state=1 samples=0 stable=1 valid=1\n")
        self.assertEqual(result["ready_results"], 2)
        self.assertEqual(result["invalid_results"], 1)
        self.assertEqual(result["valid_neutral"], 0)
        self.assertEqual(result["valid_deviation"], 1)

    def test_panic_and_restart_remain_visible_after_recovery(self):
        result = module.summarize("runtime started;\nGuru Meditation Error: panic\nruntime started;\nCCAL frame=1 state=2 samples=10 stable=1 valid=1\n")
        self.assertEqual(result["panics"], 1)
        self.assertEqual(result["runtime_starts"], 2)
        self.assertEqual(result["valid_neutral"], 1)

    def test_no_output_does_not_imply_offline_or_calibrated(self):
        result = module.summarize("")
        self.assertIsNone(result["last_status"])
        self.assertEqual(result["ready_results"], 0)
