import struct
import unittest
import zlib
from preview_protocol import FrameParser, MAGIC

def packet(seq=1,payload=b'\xff\xd8test\xff\xd9'):
    return struct.pack('<8sIHHII',MAGIC,seq,240,320,len(payload),zlib.crc32(payload))+payload

class PreviewProtocolTests(unittest.TestCase):
    def test_one_frame(self):
        result=FrameParser().feed(packet())
        self.assertEqual(len(result),1)
        self.assertEqual((result[0].sequence,result[0].width,result[0].height),(1,240,320))
        self.assertEqual(result[0].jpeg,b'\xff\xd8test\xff\xd9')
    def test_fragmented_usb_reads(self):
        parser=FrameParser(); result=[]
        for byte in packet(): result+=parser.feed(bytes([byte]))
        self.assertEqual(len(result),1)
    def test_boot_noise(self):
        self.assertEqual(len(FrameParser().feed(b'boot log\r\n'+packet())),1)
    def test_multiple_frames(self):
        self.assertEqual([f.sequence for f in FrameParser().feed(packet(1)+packet(2))],[1,2])
    def test_crc_corruption_recovers(self):
        broken=bytearray(packet()); broken[-3]^=1
        parser=FrameParser(); result=parser.feed(bytes(broken)+packet(2))
        self.assertEqual([f.sequence for f in result],[2]); self.assertEqual(parser.bad_crc,1)
    def test_invalid_length_recovers(self):
        broken=bytearray(packet()); struct.pack_into('<I',broken,16,0xffffffff)
        self.assertEqual([f.sequence for f in FrameParser().feed(bytes(broken)+packet(2))],[2])
    def test_invalid_dimensions_recovers(self):
        broken=bytearray(packet()); struct.pack_into('<H',broken,12,0)
        self.assertEqual([f.sequence for f in FrameParser().feed(bytes(broken)+packet(2))],[2])
    def test_non_jpeg_rejected(self):
        self.assertEqual(FrameParser().feed(packet(payload=b'not jpeg')),[])
    def test_partial_header_preserved(self):
        parser=FrameParser()
        self.assertEqual(parser.feed(b'noise'+packet()[:5]),[])
        self.assertEqual(len(parser.feed(packet()[5:])),1)
    def test_noise_does_not_grow_memory(self):
        parser=FrameParser(); parser.feed(b'x'*1000000)
        self.assertLessEqual(len(parser.buffer),len(MAGIC))

if __name__=='__main__': unittest.main()
