from dataclasses import dataclass
import struct
import zlib

MAGIC=b'CVJPG001'
HEADER=struct.Struct('<8sIHHII')
MAX_JPEG=65536

@dataclass(frozen=True)
class Frame:
    sequence:int
    width:int
    height:int
    jpeg:bytes

class FrameParser:
    def __init__(self): self.buffer=bytearray(); self.bad_crc=0
    def feed(self,data):
        self.buffer.extend(data); frames=[]
        while True:
            start=self.buffer.find(MAGIC)
            if start<0:
                if len(self.buffer)>=len(MAGIC): del self.buffer[:-(len(MAGIC)-1)]
                break
            if start: del self.buffer[:start]
            if len(self.buffer)<HEADER.size: break
            _,seq,width,height,size,crc=HEADER.unpack_from(self.buffer)
            if not (0<width<=640 and 0<height<=480 and 4<=size<=MAX_JPEG):
                del self.buffer[0]; continue
            if len(self.buffer)<HEADER.size+size: break
            jpeg=bytes(self.buffer[HEADER.size:HEADER.size+size])
            if zlib.crc32(jpeg)!=crc:
                self.bad_crc+=1; del self.buffer[0]; continue
            del self.buffer[:HEADER.size+size]
            if jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9'):
                frames.append(Frame(seq,width,height,jpeg))
        return frames
