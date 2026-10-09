"""Preview of the Physical Prototype Reveal (sandbox render: numpy/OpenCV/PIL + ffmpeg, NOT an After Effects render).
Uses the supplied image unaltered (only scaled/tilted). 1920x1080 @30, 8 s."""
import numpy as np, cv2, subprocess, os
from PIL import Image, ImageDraw, ImageFont
H=os.path.dirname(os.path.abspath(__file__)); W,Hh=1920,1080; N=240; F=30
src=cv2.cvtColor(cv2.imread(H+'/prototype_reference.jpg'),cv2.COLOR_BGR2RGB); sh,sw=src.shape[:2]
CAR='/usr/share/fonts/truetype/crosextra/Carlito-%s.ttf'
def font(s,b=False):
    try:return ImageFont.truetype(CAR%('Bold' if b else 'Regular'),s)
    except:return ImageFont.load_default()
ease=lambda t:t*t*(3-2*t); clamp=lambda t:min(1,max(0,t)); seg=lambda f,a,b:clamp((f/F-a)/(b-a))
# highlight boxes in source px (x0,y0,x1,y1,label,colour)
BL=(120,190,255); AM=(255,158,26)
HL={'rooms':[(170,335,300,365,'ROOM 3031 — LECTURE ROOM'),(520,335,650,365,'ROOM 3032 — SMART LAB'),(840,335,970,365,'ROOM 3033 — OFFICE / ADMIN')],
    'hvac':[(370,120,500,205,'CENTRAL HVAC UNIT'),(200,140,365,245,'MAIN DUCTS')],
    'cam':[(145,235,185,270,'OCCUPANCY CAMERA'),(435,235,475,270,'OCCUPANCY CAMERA'),(780,235,820,270,'OCCUPANCY CAMERA')],
    'tech':[(975,160,1260,395,'TECHNICAL COMPARTMENT')]}
yy,xx=np.mgrid[0:Hh,0:W]; r=np.hypot((xx-W/2)/W,(yy-Hh/2)/Hh)
bg=np.zeros((Hh,W,3),np.float32); g=np.clip(1-r*1.5,0,1)[...,None]; bg[:]=np.array([8,13,26])*(0.4+g*0.9)+np.array([0,0,0])
def render(f):
    t=f/F; fin=ease(seg(f,0,1.6)); fin_end=ease(seg(f,5.6,6.6))
    scale=(1500/sw)*(0.97+0.05*(t/8))*(1-0.28*fin_end); cx=W/2-fin_end*0+(-0*1); cy=Hh/2-fin_end*165
    yaw=(0.5-t/8)*0.05*(1-fin_end)   # tiny perspective tilt
    w,h=sw*scale,sh*scale; x0,y0=cx-w/2,cy-h/2
    dst=np.float32([[x0,y0+h*yaw*0.5*-1],[x0+w,y0+h*yaw*0.5],[x0+w,y0+h-h*yaw*0.5],[x0,y0+h+h*yaw*0.5*0]])
    dst=np.float32([[x0,y0-h*yaw*.3],[x0+w,y0+h*yaw*.3],[x0+w,y0+h-h*yaw*.3],[x0,y0+h+h*yaw*.3]])
    M=cv2.getPerspectiveTransform(np.float32([[0,0],[sw,0],[sw,sh],[0,sh]]),dst)
    im=cv2.warpPerspective(src,M,(W,Hh),flags=cv2.INTER_CUBIC,borderValue=(0,0,0)).astype(np.float32)
    mask=cv2.warpPerspective(np.full((sh,sw),255,np.uint8),M,(W,Hh))[...,None]/255.0
    # dim image while a highlight is active so the highlight reads
    act=max(seg(f,1.8,2.4)*(1-seg(f,6.3,6.6)),0)*0.0
    # soft shadow
    sd=cv2.GaussianBlur(mask[...,0],(0,0),40)[...,None]*0.5
    out=bg*(1-sd)*1.0; out=out*(1-mask)+im*mask*fin
    out=np.clip(out,0,255).astype(np.uint8); pil=Image.fromarray(out); d=ImageDraw.Draw(pil,'RGBA')
    def tx(sx,sy):
        p=cv2.perspectiveTransform(np.float32([[[sx,sy]]]),M)[0,0]; return float(p[0]),float(p[1])
    def box(b,a,col,label,above=True):
        if a<=0:return
        X0,Y0=tx(b[0],b[1]);X1,Y1=tx(b[2],b[3]); L=14*a+4; al=int(255*a)
        for (px,py,dx,dy) in((X0,Y0,1,1),(X1,Y0,-1,1),(X0,Y1,1,-1),(X1,Y1,-1,-1)):
            d.line([(px,py),(px+dx*L*2,py)],fill=col+(al,),width=3); d.line([(px,py),(px,py+dy*L*2)],fill=col+(al,),width=3)
        d.rectangle([X0,Y0,X1,Y1],fill=col+(int(26*a),))
        fnt=font(20,True); tw=d.textlength(label,font=fnt); lx=(X0+X1)/2-tw/2; ly=Y0-44 if above else Y1+14
        d.rounded_rectangle([lx-12,ly-4,lx+tw+12,ly+30],6,fill=(8,13,26,int(225*a)),outline=col+(al,),width=2); d.text((lx,ly),label,font=fnt,fill=(245,248,252,al))
    def grp(key,t0,dur,col,above=True,alt=False):
        for i,b in enumerate(HL[key]):
            a=ease(seg(f,t0+i*0.22,t0+i*0.22+0.4))*(1-ease(seg(f,t0+dur,t0+dur+0.4)))
            box(b[:4],a,col,b[4] if len(b)>4 else '',(above if not alt else i==0))
    grp('rooms',1.9,1.6,BL,False); grp('hvac',3.6,1.4,BL,True,True); grp('cam',4.0,1.4,BL,False); grp('tech',4.6,1.0,BL,False)
    # end title
    a=ease(seg(f,6.2,7.0))
    if a>0:
        d.text((W/2,Hh-150),'AIU SMART CAMPUS',font=font(64,True),fill=(245,248,252,int(255*a)),anchor='mm')
        d.text((W/2,Hh-92),'C Y B E R - P H Y S I C A L   C O N T R O L   S Y S T E M',font=font(26,True),fill=(120,190,255,int(255*a)),anchor='mm')
        d.text((W/2,Hh-52),'ALAMEIN INTERNATIONAL UNIVERSITY',font=font(22),fill=(235,240,248,int(200*a)),anchor='mm')
    o=np.asarray(pil).astype(np.float32); o*= (1-ease(seg(f,7.7,8.0))*0) ; return np.clip(o,0,255).astype(np.uint8)
if __name__=='__main__':
    import sys
    fr=H+'/frames'
    for f in range(N): cv2.imwrite(f'{fr}/p_{f:04d}.png',cv2.cvtColor(render(f),cv2.COLOR_RGB2BGR))
    subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate','30','-i',fr+'/p_%04d.png','-c:v','libx264','-pix_fmt','yuv420p','-crf','18',H+'/AIU_PROTOTYPE_REVEAL_PREVIEW.mp4'],check=True); print('ok')
