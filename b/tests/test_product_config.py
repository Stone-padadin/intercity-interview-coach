import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("firmware", ROOT / "b/tools/firmware.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProductConfigTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".local").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".local")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".local").mkdir()
        self.path = self.root / ".local/product.json"

    def save(self, length, encoding="utf-8"):
        self.path.write_text(json.dumps({"pid": 11814, "secret": "A" * length}), encoding=encoding)

    def test_vendor_boundary_accepts_32_and_rejects_33_without_truncating(self):
        self.save(32)
        self.assertEqual(module.product_identity(self.path), (11814, "A" * 32))
        self.save(33)
        original = self.path.read_bytes()
        with self.assertRaises(SystemExit):
            module.product_identity(self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_bad_identity_stops_before_toolchain_or_flash(self):
        self.save(33)
        with patch.object(module, "ROOT", self.root), patch.object(module, "environment") as environment, patch.object(module.subprocess, "Popen") as process, patch("sys.argv", ["firmware.py", "flash", "--port", "COM7"]):
            with self.assertRaises(SystemExit):
                module.main()
            environment.assert_not_called()
            process.assert_not_called()

    def test_powershell_bom_identity_is_accepted(self):
        self.save(32, "utf-8-sig")
        self.assertEqual(module.product_identity(self.path)[0], 11814)

    def test_missing_product_remains_explicit_offline_identity(self):
        self.assertEqual(module.product_identity(self.path), (0, "UNCONFIGURED"))

    def test_idf_environment_excludes_diagnostic_pythonpath(self):
        sdk = self.root / "external/vendor-sdk"
        (sdk / "esp-idf/tools").mkdir(parents=True)
        (sdk / "esp-idf/tools/tools.json").write_text('{"tools": []}', encoding="utf-8")
        python = self.root / ".local/idf-tools/python_env/idf5.4_py3.12_env/Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.touch()
        with patch.object(module, "ROOT", self.root), patch.object(module, "SDK", sdk), patch.dict(module.os.environ, {"PYTHONPATH": "unrelated-device-packages"}):
            selected, env = module.environment()
        self.assertEqual(selected, python)
        self.assertNotIn("PYTHONPATH", env)
