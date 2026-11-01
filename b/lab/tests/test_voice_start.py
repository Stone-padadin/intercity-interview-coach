"""Manual wake installer safety and optional firmware command contract."""
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_voice_start as install
class ManualWakeTests(unittest.TestCase):
    def test_bad_anchor_preserves_sdk(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Path(folder);(app/'agent').mkdir();p=app/'agent/agent_app.c';p.write_bytes(b'modified source')
            with self.assertRaises(ValueError):install.edits(app)
            self.assertEqual(p.read_bytes(),b'modified source')
    def test_existing_entry_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Path(folder);(app/'agent').mkdir();p=app/'agent/agent_app.c';p.write_text(install.ENTRY+install.ANCHOR)
            before=p.read_bytes()
            with self.assertRaises(ValueError):install.edits(app)
            self.assertEqual(p.read_bytes(),before)
    def test_missing_worker_is_rejected_before_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Path(folder);(app/'agent').mkdir();p=app/'agent/agent_app.c';p.write_text(install.ANCHOR)
            with self.assertRaises(ValueError):install.edits(app)
    def test_valid_insertion_preserves_existing_edits_and_crlf(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Path(folder);(app/'agent').mkdir();p=app/'agent/agent_app.c'
            original=('/* existing team changes */\nstatic void agent_handle_wakeup(void);\n'
                      '/* s_worker_sem s_cloud_connected agent_handle_wakeup(); */\n'+install.ANCHOR+'\n}\n').replace('\n','\r\n').encode()
            p.write_bytes(original);path,before,after=install.edits(app)
            self.assertEqual(before,original);self.assertEqual(p.read_bytes(),original)
            self.assertEqual(after.replace(install.ENTRY.replace('\n','\r\n').encode(),b'',1),original)
if __name__=='__main__':unittest.main()
