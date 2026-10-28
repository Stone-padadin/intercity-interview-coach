"""Local-only USB JPEG preview. No frame upload or recording."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
import serial
from esptool.reset import HardReset
from preview_protocol import FrameParser

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--listen',type=int,default=8765)
    parser.add_argument('--reset',action='store_true')
    args=parser.parse_args()
    stop=threading.Event(); lock=threading.Lock()
    state={'frames':0,'connected':False,'error':'','sequence':0,'width':0,'height':0,'updated':0.,'jpeg':None,'bad_crc':0}
    def reader():
        reset_pending=args.reset
        while not stop.is_set():
            port=serial.Serial(port=None,baudrate=921600,timeout=.2)
            port.dtr=False; port.rts=False; port.port=args.port
            try:
                port.open(); decoder=FrameParser()
                with lock: state.update(connected=True,error='')
                if reset_pending: HardReset(port)(); reset_pending=False
                diagnostic=b''
                while not stop.is_set():
                    block=port.read(max(1,min(port.in_waiting,65536)))
                    if not block: continue
                    diagnostic=(diagnostic+block)[-4096:]
                    error=re.search(rb'CPREVIEW_ERROR ([a-zA-Z0-9_=-]+)',diagnostic)
                    if error:
                        with lock: state['error']=error.group(1).decode('ascii')
                    for frame in decoder.feed(block):
                        with lock:
                            state.update(frames=state['frames']+1,sequence=frame.sequence,
                                width=frame.width,height=frame.height,updated=time.monotonic(),
                                jpeg=frame.jpeg,bad_crc=decoder.bad_crc,error='')
            except (serial.SerialException,OSError) as exc:
                with lock: state.update(connected=False,error=str(exc))
                stop.wait(1)
            finally: port.close()
        with lock: state['connected']=False
    html=(Path(__file__).parent/'preview.html').read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,code,content_type,data):
            self.send_response(code); self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError): pass
        def do_GET(self):
            route=self.path.split('?',1)[0]
            if route=='/': return self.reply(200,'text/html; charset=utf-8',html)
            if route=='/frame.jpg':
                with lock: jpeg=state['jpeg']
                return self.reply(200 if jpeg else 503,'image/jpeg',jpeg or b'')
            if route=='/status':
                with lock: result={k:v for k,v in state.items() if k!='jpeg'}
                result['age']=time.monotonic()-result.pop('updated') if result['frames'] else 0
                return self.reply(200,'application/json',json.dumps(result).encode())
            self.reply(404,'text/plain',b'Not found')
        def do_POST(self):
            if self.path!='/stop': return self.reply(404,'text/plain',b'Not found')
            self.reply(200,'text/plain',b'Stopping')
            stop.set(); threading.Thread(target=server.shutdown,daemon=True).start()
    server=ThreadingHTTPServer(('127.0.0.1',args.listen),Handler)
    thread=threading.Thread(target=reader,daemon=True); thread.start()
    print(f'Preview ready at http://127.0.0.1:{args.listen}',flush=True)
    try: server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: pass
    finally: stop.set(); server.server_close(); thread.join(timeout=3)

if __name__=='__main__': main()
