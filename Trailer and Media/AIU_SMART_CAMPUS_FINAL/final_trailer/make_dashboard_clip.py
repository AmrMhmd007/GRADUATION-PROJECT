"""PROVISIONAL dashboard clip. Built ONLY from real pixels captured from the running app (localhost:5174, Occupancy tab, sim backend :8001) via the Chrome tool.
It is NOT a screen recording: two real captures (top / scrolled) are stitched into one tall page and panned. Cursor is visible in the captures."""
import numpy as np, subprocess, os, cv2
from PIL import Image, ImageDraw, ImageFont
R=os.path.abspath(os.path.join(os.path.dirname(__file__),'..')); S=R+'/recordings/source_frames'
top=np.array(Image.open(S+'/occ_top.png').convert('RGB')); sc=np.array(Image.open(S+'/occ_scrolled.png').convert('RGB'))
# measure scroll offset between the two captures with the sidebar column (x 0..220) using template matching
t=top[300:420,0:230]; res=cv2.matchTemplate(sc[:, :230],t,cv2.TM_CCOEFF_NORMED); _,mx,_,loc=cv2.minMaxLoc(res); off=300-loc[1]; print('scroll offset px',off,'match',round(mx,3))
alt=np.array(Image.open(S+'/occ_page_top.png').convert('RGB'))   # earlier real capture (cursor elsewhere), page offset +105 px
top=top.copy(); top[488:532,892:932]=alt[488+105:532+105,892:932]   # cosmetic: replace the mouse-cursor patch with the same area from a cursor-free real capture
H,W=top.shape[:2]; tall=np.vstack([top, sc[H-off:H]]) if off>0 else top
print('tall',tall.shape)
sc_f=1920/W; out='/sessions/great-sleepy-rubin/mnt/Desktop/AIU_SMART_CAMPUS_FINAL/recordings'; fr='/tmp/dfr'; os.makedirs(fr,exist_ok=True)
F=30; N=8*F; ease=lambda x:x*x*(3-2*x)
big=cv2.resize(tall,(1920,int(tall.shape[0]*sc_f)),interpolation=cv2.INTER_CUBIC); vh=int(H*sc_f); maxoff=big.shape[0]-vh
fnt=ImageFont.truetype('/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf',26)
for f in range(N):
    t_=f/F; p=ease(min(1,max(0,(t_-1.0)/4.0))); y=int(maxoff*p)
    z=1+0.035*(f/N); win=big[y:y+vh]; hh,ww=win.shape[:2]; M=cv2.getRotationMatrix2D((ww*0.5,hh*0.45),0,z); win=cv2.warpAffine(win,M,(ww,hh),flags=cv2.INTER_CUBIC); canvas=np.zeros((1080,1920,3),np.uint8); canvas[:]=(8,13,26); y0=(1080-vh)//2; canvas[y0:y0+vh]=win[:1080-y0*0 if vh<=1080 else 1080][:min(vh,1080)]
    im=Image.fromarray(canvas); d=ImageDraw.Draw(im)
    d.text((960,1080-26),'SIMULATED DATA — NOT LIVE CAMERA OR SENSOR TELEMETRY',font=fnt,fill=(255,158,26),anchor='mm')
    a=min(1,t_/0.5,(8-t_)/0.5); im=Image.blend(Image.new('RGB',(1920,1080),(8,13,26)),im,max(0,a)); im.save(f'{fr}/d_{f:04d}.png')
mp4=out+'/AIU_OCCUPANCY_DASHBOARD_PROVISIONAL.mp4'
subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate','30','-i',fr+'/d_%04d.png','-c:v','libx264','-pix_fmt','yuv420p','-crf','16',mp4],check=True); print(mp4)
