"""Decode one CRC-checked UYVY snapshot from camera-profile serial logs."""
import argparse
from pathlib import Path
import re
import struct
import zlib

def parse_snapshot(text):
    header=re.search(r'CFRAME_BEGIN width=(\d+) height=(\d+) format=UYVY bytes=(\d+)',text)
    if not header: raise ValueError('No UYVY snapshot header found')
    width,height,size=map(int,header.groups())
    if width<2 or width%2 or height<1 or width>640 or height>480 or size!=width*height*2:
        raise ValueError('Invalid snapshot dimensions or size')
    body=text[header.end():]
    end=re.search(r'CFRAME_END crc32=([0-9a-fA-F]{8})',body)
    if not end: raise ValueError('Snapshot incomplete: end marker missing')
    chunks=re.findall(r'CFRAME_DATA seq=(\d+) ([0-9a-fA-F]+)',body[:end.start()])
    raw=bytearray()
    for index,(seq,chunk) in enumerate(chunks):
        if int(seq)!=index: raise ValueError('Missing or duplicate snapshot chunk')
        try: raw.extend(bytes.fromhex(chunk))
        except ValueError as exc: raise ValueError('Malformed hex payload') from exc
        if len(raw)>size: raise ValueError('Snapshot larger than declared size')
    if len(raw)!=size: raise ValueError('Snapshot incomplete: byte count mismatch')
    if zlib.crc32(raw)!=int(end.group(1),16): raise ValueError('Snapshot CRC mismatch')
    return width,height,bytes(raw)

def uyvy_to_rgb(raw,width,height):
    if width<2 or width%2 or height<1 or len(raw)!=width*height*2:
        raise ValueError('Invalid UYVY frame')
    rgb=bytearray(width*height*3)
    def clamp(value): return min(255,max(0,value))
    for offset in range(0,len(raw),4):
        u,y0,v,y1=raw[offset:offset+4]
        for pixel,y in enumerate((y0,y1)):
            c=y-16; dv=v-128; du=u-128
            start=(offset//2+pixel)*3
            rgb[start:start+3]=bytes((clamp((298*c+409*dv+128)>>8),
                clamp((298*c-100*du-208*dv+128)>>8),clamp((298*c+516*du+128)>>8)))
    return bytes(rgb)

def rotate_cw90(rgb,width,height):
    if width<1 or height<1 or len(rgb)!=width*height*3: raise ValueError('Invalid RGB frame')
    result=bytearray(len(rgb))
    for y in range(height):
        for x in range(width):
            source=(y*width+x)*3
            target=(x*height+height-1-y)*3
            result[target:target+3]=rgb[source:source+3]
    return height,width,bytes(result)

def save_bmp(path,rgb,width,height):
    stride=(width*3+3)&~3
    pixels=bytearray(stride*height)
    for y in range(height):
        for x in range(width):
            source=(y*width+x)*3; target=y*stride+x*3
            pixels[target:target+3]=rgb[source:source+3][::-1]
    header=struct.pack('<2sIHHI',b'BM',54+len(pixels),0,0,54)
    info=struct.pack('<IiiHHIIiiII',40,width,-height,1,24,0,len(pixels),2835,2835,0,0)
    Path(path).write_bytes(header+info+pixels)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='Output prefix, no extension')
    args=parser.parse_args()
    log_bytes=args.log.read_bytes()
    text=log_bytes.decode('utf-16' if log_bytes.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8',errors='replace')
    width,height,raw=parse_snapshot(text)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    prefix=str(args.output)
    Path(prefix+'.uyvy').write_bytes(raw)
    rgb=uyvy_to_rgb(raw,width,height)
    save_bmp(prefix+'-native.bmp',rgb,width,height)
    rw,rh,rotated=rotate_cw90(rgb,width,height)
    save_bmp(prefix+'-cw90.bmp',rotated,rw,rh)
    print(f'CRC verified: {width}x{height}, {len(raw)} bytes; wrote native and cw90 BMPs')

if __name__=='__main__': main()
