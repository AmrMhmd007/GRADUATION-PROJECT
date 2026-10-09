"""Records the REAL running dashboard (Chrome, headless, 1920x1080, CSS zoom 1.5) with Chrome DevTools Page.startScreencast:
every frame the browser actually paints is saved with its timestamp; encoded afterwards to constant 30 fps H.264. No simulated cursor, no animation added."""
import sys, os, json, time, shutil, base64, subprocess
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
from playwright.sync_api import sync_playwright
ZOOM=1.5; FFMPEG='/opt/homebrew/bin/ffmpeg'
def jpeg_size(path):
    d=open(path,'rb').read(); i=2
    while i<len(d):
        if d[i]!=0xFF: i+=1; continue
        m=d[i+1]
        if m in (0xC0,0xC1,0xC2): return (int.from_bytes(d[i+7:i+9],'big'),int.from_bytes(d[i+5:i+7],'big'))
        i+=2+int.from_bytes(d[i+2:i+4],'big')
    return None
class Take:
    def __init__(self,p,name):
        self.name=name; self.fdir=f'{S}/raw/{name}_frames'; shutil.rmtree(self.fdir,ignore_errors=True); os.makedirs(self.fdir)
        self.b,self.ctx=new_context(p); self.ctx.add_init_script("document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.zoom='%s'})"%ZOOM)
        self.pg=self.ctx.new_page(); self.cdp=self.ctx.new_cdp_session(self.pg); self.frames=[]; self.marks={}
        self.cdp.on('Page.screencastFrame',self._frame)
        self.cdp.send('Page.startScreencast',{'format':'jpeg','quality':92,'maxWidth':1920,'maxHeight':1080,'everyNthFrame':1})
        self.t0=time.time()
    def _frame(self,params):
        i=len(self.frames); open(f'{self.fdir}/{i:05d}.jpg','wb').write(base64.b64decode(params['data'])); self.frames.append(params['metadata']['timestamp'])
        try: self.cdp.send('Page.screencastFrameAck',{'sessionId':params['sessionId']})
        except Exception: pass
    def t(self): return round(time.time()-self.t0,2)
    def mark(self,k): self.marks[k]=time.time()
    def wait(self,s): self.pg.wait_for_timeout(int(s*1000))
    def goto(self,hash_): self.pg.goto(APP+'/'+hash_)
    def scroll(self,dy_total,secs,sel=None):
        if sel:
            bb=self.pg.locator(sel).first.bounding_box(); self.pg.mouse.move(bb['x']+bb['width']/2,bb['y']+bb['height']/2)
        else: self.pg.mouse.move(1100,600)
        n=max(1,int(secs*25)); step=dy_total/n
        for _ in range(n): self.pg.mouse.wheel(0,step); self.pg.wait_for_timeout(40)
    def finish(self):
        self.wait(0.4); self.end_epoch=time.time(); self.cdp.send('Page.stopScreencast'); self.pg.close(); self.ctx.close(); self.b.close()
        keep=[i for i in range(len(self.frames)) if jpeg_size(f'{self.fdir}/{i:05d}.jpg')==(1920,1080)]
        ts=[self.frames[i] for i in keep]; lst=f'{S}/raw/{self.name}_concat.txt'
        with open(lst,'w') as f:
            for k,i in enumerate(keep):
                d=(ts[k+1]-ts[k]) if k+1<len(ts) else max(0.04,self.end_epoch-ts[k])
                f.write(f"file '{self.fdir}/{i:05d}.jpg'\nduration {max(d,0.001):.4f}\n")
            f.write(f"file '{self.fdir}/{keep[-1]:05d}.jpg'\n")
        self.first_kept_ts=ts[0]
        dst=f'{S}/raw/{self.name}.mp4'
        subprocess.run([FFMPEG,'-y','-loglevel','error','-f','concat','-safe','0','-i',lst,'-vf','fps=30,format=yuv420p','-c:v','libx264','-crf','12','-preset','medium',dst],check=True)
        # marks are relative to our wall-clock t0; convert to video time using the first frame's timestamp
        json.dump({'marks':{k:round(v-self.first_kept_ts,2) for k,v in self.marks.items()},'frames_kept':len(ts),'frames_dropped':len(self.frames)-len(ts),'first_ts':ts[0],'last_ts':ts[-1],'duration':round(ts[-1]-ts[0],2)},open(f'{S}/raw/{self.name}.marks.json','w'),indent=1)
        return dst
