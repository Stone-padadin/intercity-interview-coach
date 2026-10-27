import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('prepare_b',ROOT/'b/tools/prepare_device.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PrepareTests(unittest.TestCase):
    def setUp(self):
        fixtures=ROOT/'.local/b-prepare-tests';fixtures.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=fixtures)
        self.root=Path(self.temp.name)
        assert self.root.resolve().is_relative_to(fixtures.resolve())
        self.addCleanup(self.temp.cleanup)
        self.sdk=self.root/'external/vendor-sdk';self.sdk.mkdir(parents=True)
        self.command('init','-q');self.command('config','core.autocrlf','false')
        self.main=self.sdk/'apps/main/main.c';self.main.parent.mkdir(parents=True)
        self.main.write_text('original\n',encoding='utf-8',newline='\n')
        self.command('add','.');self.command('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','baseline')
        head=self.command('rev-parse','HEAD')
        cdir=self.root/'c/firmware';cdir.mkdir(parents=True)
        (cdir/'upstream.json').write_text(json.dumps({'commit':head}),encoding='utf-8')
        self.main.write_text('original\nC integration\n',encoding='utf-8',newline='\n')
        (cdir/'vendor-integration.patch').write_text(self.command('diff','--binary')+'\n',encoding='utf-8',newline='\n')
        cfile=cdir/'apps/main/pose/c_overlay.c';cfile.parent.mkdir(parents=True)
        cfile.write_bytes(b'C overlay\n')
        target=self.sdk/'apps/main/pose/c_overlay.c';target.parent.mkdir();target.write_bytes(cfile.read_bytes())
        bdir=self.root/'b/firmware';bdir.mkdir(parents=True)
        (bdir/'b_runtime.h').write_bytes(b'B overlay\n')
        (bdir/'vendor-integration.patch').write_text(
            'diff --git a/apps/main/main.c b/apps/main/main.c\n'
            '--- a/apps/main/main.c\n+++ b/apps/main/main.c\n'
            '@@ -1,2 +1,3 @@\n original\n C integration\n+B integration\n',encoding='utf-8',newline='\n')
        override=patch.object(module,'ROOT',self.root);override.start();self.addCleanup(override.stop)

    def command(self,*args):
        return subprocess.check_output(['git','-C',str(self.sdk),*args],text=True,encoding='utf-8',stderr=subprocess.DEVNULL).strip()

    def test_check_only_then_apply_and_reject_repeat(self):
        module.prepare(self.sdk,True)
        self.assertFalse((self.sdk/'apps/main/b_device').exists())
        module.prepare(self.sdk)
        self.assertIn('B integration',self.main.read_text())
        owned=self.sdk/'apps/main/b_device/b_runtime.h'
        self.assertEqual(owned.read_bytes(),b'B overlay\n')
        with self.assertRaises(SystemExit):module.prepare(self.sdk)
        self.assertEqual(owned.read_bytes(),b'B overlay\n')

    def test_changed_tracked_file_preserved(self):
        content=self.main.read_bytes()+b'user work\n';self.main.write_bytes(content)
        with self.assertRaises(SystemExit):module.prepare(self.sdk)
        self.assertEqual(self.main.read_bytes(),content)

    def test_unknown_untracked_file_preserved(self):
        own=self.sdk/'keep.txt';own.write_bytes(b'keep')
        with self.assertRaises(SystemExit):module.prepare(self.sdk)
        self.assertEqual(own.read_bytes(),b'keep')

    def test_changed_c_overlay_preserved(self):
        target=self.sdk/'apps/main/pose/c_overlay.c';target.write_bytes(b'user C edits')
        with self.assertRaises(SystemExit):module.prepare(self.sdk)
        self.assertEqual(target.read_bytes(),b'user C edits')

    def test_staged_work_preserved(self):
        self.command('add','apps/main/main.c')
        before=self.command('diff','--cached')
        with self.assertRaises(SystemExit):module.prepare(self.sdk)
        self.assertEqual(before,self.command('diff','--cached'))

    def test_hash_abbreviation_only_does_not_change_content_comparison(self):
        self.assertEqual(module.normalized('index abc..def 100644\n+text'),module.normalized('index abc0..def0 100644\n+text'))
        self.assertNotEqual(module.normalized('index abc..def 100644\n+text'),module.normalized('index abc..def 100644\n+changed'))

if __name__=='__main__':unittest.main()
