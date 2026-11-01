import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('spi_prepare',ROOT/'b/spi/prepare.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SpiPrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def mapping(self,**kwargs):
        # Synthetic test identifiers only; not an actual product export.
        obj=dict(pid=11919,siid=250,command=1,state=2,pose=3,calibration=4,samples=5,result=6)
        obj.update(kwargs)
        p=self.root/'mapping.json';p.write_text(json.dumps(obj),encoding='utf-8')
        return p

    def test_mapping_requires_actual_product_and_distinct_ids(self):
        self.assertIn('B_SPI_MAPPING_ENABLED 1',module.mapping_header(self.mapping()))
        for kwargs in [dict(pid=11920),dict(siid=0),dict(siid=True),dict(state=1),dict(samples=None)]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                module.mapping_header(self.mapping(**kwargs))

    def test_no_mapping_disables_cloud_dispatch(self):
        self.assertIn('#define B_SPI_MAPPING_ENABLED 0',module.mapping_header(None))

    def fixture(self):
        root=self.root/'repo';sdk=self.root/'sdk';main=sdk/'apps/main'
        for folder in ['b/firmware','b/spi','c/firmware/apps/main/pose']:
            (root/folder).mkdir(parents=True)
        for folder in ['b_device','pose','cloud','lj_components/iot_control']:
            (main/folder).mkdir(parents=True)
        hashes={}
        for p in ['b/firmware/b_device_runtime.c','b/firmware/b_device_runtime.h',
                  'c/firmware/apps/main/pose/c_live_pose.c','c/firmware/apps/main/pose/c_live_pose.h']:
            content=('baseline '+Path(p).name+'\n').encode()
            target=main/('b_device' if p.startswith('b/') else 'pose')/Path(p).name
            target.write_bytes(content)
            (root/p).write_bytes(content+b'updated\n')
            hashes[p]=hashlib.sha256(content).hexdigest()
        for name in ('b_device_state.c','b_device_state.h','b_c_vision.c','b_c_vision.h'):
            (root/'b/firmware'/name).write_bytes(b'reviewed\n')
            (main/'b_device'/name).write_bytes(b'reviewed\n')
        (root/'b/spi/baseline-sha256.json').write_text(json.dumps(hashes))
        (root/'b/spi/b_spi_mapping.disabled.h').write_text('#define B_SPI_MAPPING_ENABLED 0\n')
        (sdk/'.spi-workflow-disposable').write_text('test only')
        (main/'CMakeLists.txt').write_text('set(B_DEVICE_PROFILE "off")\n"./b_device/b_device_runtime.c"\nset(COMPONENT_ADD_INCLUDEDIRS x)\nregister_component()\n')
        (main/'main.c').write_text('''QM_LOGE("main","live pose init failed");
        return;
QM_LOGE("main","B runtime init failed");
        return;
#elif defined(CONFIG_QM_POSE_SUPPORT) && CONFIG_QM_POSE_SUPPORT
if (bsp_camera_stream_start()!=ESP_OK)
if (bsp_camera_early_init() != ESP_OK)
''')
        (main/'cloud/ljyd_cloud.c').write_text('#include "ljyd_cloud.h"\nif (bsp_camera_stream_start() != ESP_OK)\n')
        (main/'lj_components/iot_control/iot_control.c').write_text('#include "iot_control.h"\n    for (i = 0; i < QM_ARRAY_SIZE(s_table); i++)\n')
        return root,sdk

    def test_check_then_install_and_repeat_refusal(self):
        root,sdk=self.fixture()
        with patch.object(module,'ROOT',root):
            module.prepare(sdk,check=True)
            self.assertFalse((sdk/'.spi-workflow-installed').exists())
            before=(sdk/'apps/main/main.c').read_bytes()
            module.prepare(sdk)
            self.assertEqual((sdk/'apps/main/main.c.before-spi').read_bytes(),before)
            self.assertIn('continuing voice/cloud startup',(sdk/'apps/main/main.c').read_text())
            with self.assertRaises(ValueError): module.prepare(sdk)

    def test_unknown_source_or_bad_anchor_never_partially_writes(self):
        root,sdk=self.fixture()
        source=sdk/'apps/main/b_device/b_device_runtime.c'
        source.write_bytes(b'teammate work\n')
        cmake=sdk/'apps/main/CMakeLists.txt';before=cmake.read_bytes()
        with patch.object(module,'ROOT',root),self.assertRaises(ValueError): module.prepare(sdk)
        self.assertEqual(source.read_bytes(),b'teammate work\n')
        self.assertEqual(cmake.read_bytes(),before)
        self.assertFalse((sdk/'.spi-workflow-installed').exists())

    def test_requires_disposable_marker(self):
        with self.assertRaises(ValueError): module.prepare(self.root)

    def test_existing_spi_module_is_preserved(self):
        root,sdk=self.fixture()
        (root/'b/firmware/b_spi_runtime.c').write_text('new module')
        own=sdk/'apps/main/b_device/b_spi_runtime.c';own.write_text('teammate module')
        before=(sdk/'apps/main/main.c').read_bytes()
        with patch.object(module,'ROOT',root),self.assertRaises(ValueError): module.prepare(sdk)
        self.assertEqual(own.read_text(),'teammate module')
        self.assertEqual((sdk/'apps/main/main.c').read_bytes(),before)


if __name__=='__main__': unittest.main()
