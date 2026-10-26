import unittest
import zlib
from snapshot import parse_snapshot, uyvy_to_rgb, rotate_cw90

def log_for(raw=b'\x80\x10\x80\xeb', width=2,height=1):
    return (f'CFRAME_BEGIN width={width} height={height} format=UYVY bytes={len(raw)}\n'
            f'CFRAME_DATA seq=0 {raw.hex()}\n'
            f'CFRAME_END crc32={zlib.crc32(raw):08x}\n')

class SnapshotTests(unittest.TestCase):
    def test_roundtrip_with_unrelated_logs(self):
        self.assertEqual(parse_snapshot('boot log\n'+log_for()+'other logs\n'),
                         (2,1,b'\x80\x10\x80\xeb'))
    def test_missing_bytes_rejected(self):
        with self.assertRaises(ValueError): parse_snapshot(log_for().replace('801080eb','8010'))
    def test_crc_mismatch_rejected(self):
        with self.assertRaises(ValueError): parse_snapshot(log_for().replace('801080eb','801080ea'))
    def test_missing_end_rejected(self):
        with self.assertRaises(ValueError): parse_snapshot(log_for().split('CFRAME_END')[0])
    def test_sequence_error_rejected(self):
        with self.assertRaises(ValueError): parse_snapshot(log_for().replace('seq=0','seq=1'))
    def test_invalid_dimensions_rejected(self):
        with self.assertRaises(ValueError): parse_snapshot(log_for(width=3))
    def test_black_white(self):
        self.assertEqual(uyvy_to_rgb(b'\x80\x10\x80\xeb',2,1),bytes([0,0,0,255,255,255]))
    def test_color_channels(self):
        red=uyvy_to_rgb(bytes([90,82,240,82]),2,1)
        self.assertGreater(red[0],240); self.assertLess(red[1],10); self.assertLess(red[2],10)
    def test_rotation(self):
        self.assertEqual(rotate_cw90(bytes(range(12)),2,2),
                         (2,2,bytes([6,7,8,0,1,2,9,10,11,3,4,5])))

if __name__=='__main__': unittest.main()
