"""Closing card animation: real AIU photo (supplied by project team) blurred+darkened, title cues on the VO tagline. 9.3 s = 279 frames."""
import cairo, sys, os, numpy as np
from PIL import Image, ImageFilter
sys.path.insert(0,'/sessions/great-sleepy-rubin/mnt/Desktop/AIU_SMART_CAMPUS_FINAL/blender/attendance_scene/overlay')
from uilib import *
R='/sessions/great-sleepy-rubin/mnt/Desktop/AIU_SMART_CAMPUS_FINAL/'
OUT=R+'final_trailer/voiceover_final/work/close'; N=279
ph=Image.open(R+'assets/collected_references/aiu_exterior_03_flags_logo.png').convert('RGB')
def cover(im,w,h,z):
    s=max(w/im.width,h/im.height)*z; r=im.resize((int(im.width*s)+1,int(im.height*s)+1),Image.LANCZOS); x=(r.width-w)//2; y=(r.height-h)//2; return r.crop((x,y,x+w,y+h))
logo=Image.open('/sessions/great-sleepy-rubin/mnt/Desktop/TOP PR/GRADUATION PROJECT/Source Code/dashboard/public/aiu-logo.png').convert('RGBA')
lg=logo.copy(); lg.thumbnail((190,190))
def frame(i):
    z=1.0+0.07*i/N
    bg=cover(ph,W,H,z).filter(ImageFilter.GaussianBlur(14)); a=np.asarray(bg).astype(float)*0.33+np.array([5,9,20])*0.4
    s=cairo.ImageSurface.create_for_data(bytearray(np.dstack([a[...,2],a[...,1],a[...,0],np.full(a.shape[:2],255)]).clip(0,255).astype('uint8').tobytes()),cairo.FORMAT_ARGB32,W,H); c=cairo.Context(s)
    fi=ease(i/12); fo=1-ease((i-262)/16)
    # logo (existing AIU identity from the application)
    lp=Image.new('RGBA',(W,H),(0,0,0,0)); lp.paste(lg,(W//2-lg.width//2,300-lg.height//2+0),lg)
    la=np.asarray(lp).astype(float); la[...,3]*=ease((i-2)/14)*fo
    lsurf=cairo.ImageSurface.create_for_data(bytearray(np.dstack([la[...,2]*la[...,3]/255,la[...,1]*la[...,3]/255,la[...,0]*la[...,3]/255,la[...,3]]).clip(0,255).astype('uint8').tobytes()),cairo.FORMAT_ARGB32,W,H)
    c.set_source_surface(lsurf,0,0); c.paint()
    text(c,'AIU SMART CAMPUS',W/2,520,112,WHITE,ease((i-3)/14)*fo,True,12,'c')
    c.set_source_rgba(*BLUE,ease((i-14)/14)*fo); c.rectangle(W/2-200,548,400,3); c.fill()
    text(c,'ALAMEIN INTERNATIONAL UNIVERSITY',W/2,616,38,BLUE,ease((i-27)/14)*fo,True,9,'c')
    text(c,'Connecting Spaces.',W/2,720,44,WHITE,ease((i-43)/12)*fo,False,3,'c')
    text(c,'Enabling Smarter Campus Management.',W/2,780,44,WHITE,ease((i-75)/12)*fo,False,3,'c')
    text(c,'CYBER-PHYSICAL CONTROL SYSTEM  ·  GRADUATION PROJECT',W/2,900,22,GREY,ease((i-118)/16)*fo,False,5,'c')
    return s
if '--test' in sys.argv:
    frame(200).write_to_png(OUT+'/test.png'); sys.exit()
for i in range(N): frame(i).write_to_png(f'{OUT}/c_{i+1:04d}.png')
print('done')
