"""NEW review cut (v2, with human characters). Does not touch AIU_TRAILER_REVIEW_FINAL.mp4 / ASSEMBLY_PREVIEW. Silent.
Output: AIU_TRAILER_REVIEW_v2_HUMANS.mp4   Sources are existing renders only (no scene re-render here)."""
import subprocess, os
from PIL import Image, ImageDraw, ImageFont
R=os.path.abspath(os.path.join(os.path.dirname(__file__),'..')); O=os.path.dirname(os.path.abspath(__file__)); Wk=O+'/work_v2'; os.makedirs(Wk,exist_ok=True)
DOOR_FR=R+'/blender/human_entry/renders/preview_v2/f_%04d.png'; DOOR_OV=R+'/blender/human_entry/overlay/frames_human/ov_%04d.png'
CLS_FR=R+'/blender/human_classroom/renders/preview_v1/f_%04d.png'
DASH=R+'/recordings/AIU_OCCUPANCY_DASHBOARD_PROVISIONAL.mp4'; PROTO=R+'/after_effects/prototype_reveal/AIU_PROTOTYPE_REVEAL_PREVIEW.mp4'
C=lambda s,b=False:ImageFont.truetype('/usr/share/fonts/truetype/crosextra/Carlito-%s.ttf'%('Bold' if b else 'Regular'),s)
NAVY=(7,12,24); WHITE=(238,242,250); BLUE=(120,160,225); GREY=(150,160,180)
def spaced(d,xy,s,font,fill,sp=0,anchor='l'):
    w=sum(d.textlength(ch,font=font)+sp for ch in s)-sp; x,y=xy
    if anchor=='c': x-=w/2
    for ch in s: d.text((x,y),ch,font=font,fill=fill); x+=d.textlength(ch,font=font)+sp
def label_png(path,chapter,sub=None,bottom=None):
    im=Image.new('RGBA',(1920,1080),(0,0,0,0)); d=ImageDraw.Draw(im)
    if chapter:
        d.rectangle((96,64,100,112),fill=BLUE+(255,)); spaced(d,(120,64),chapter,C(30,True),WHITE+(235,),4)
        if sub: spaced(d,(120,100),sub,C(18),GREY+(235,),3)
    if bottom:
        w=sum(d.textlength(ch,font=C(19))+2 for ch in bottom); d.rounded_rectangle((90,960,90+w+44,1006),radius=8,fill=(7,12,24,170))
        spaced(d,(112,971),bottom,C(19),(235,238,245,230),2)
    im.save(path)
def card_png(path,title,sub,uni=None,size=(1920,1080)):
    im=Image.new('RGB',size,NAVY); d=ImageDraw.Draw(im)
    for i in range(0,540,3):   # soft radial-ish vignette lift in the centre
        a=int(14*(1-i/540)); d.ellipse((960-i*2.2,540-i,960+i*2.2,540+i),outline=(7+a,12+a,24+int(a*1.6)))
    spaced(d,(960,430),title,C(128,True),WHITE,10,'c')
    d.rectangle((760,585,1160,588),fill=BLUE)
    spaced(d,(960,620),sub,C(34,True),BLUE,9,'c')
    if uni: spaced(d,(960,700),uni,C(30),WHITE,6,'c')
    im.save(path)
def run(a): subprocess.run(['ffmpeg','-y','-loglevel','error']+a,check=True)
FMT='fps=30,format=yuv420p,setsar=1'
GRADE='eq=contrast=1.05:saturation=1.04:gamma=0.98,vignette=PI/6'
# labels
label_png(Wk+'/lab_door.png','01  ACCESS CONTROL','CONCEPT VISUALISATION — CINEMATIC DEMONSTRATION')
label_png(Wk+'/lab_cls.png','02  SMART CLASSROOM','ANIMATED CHARACTERS — NOT LIVE CAMERA DETECTION',None)
label_png(Wk+'/lab_cls_b.png',None,None,'CONCEPT VISUALISATION  ·  ANIMATED PEOPLE  ·  NO OCCUPANCY DATA SHOWN')
label_png(Wk+'/lab_dash.png','03  CAMPUS DASHBOARD','SIMULATED OCCUPANCY DATA — NOT LIVE HARDWARE TELEMETRY')
label_png(Wk+'/lab_proto.png','04  ENGINEERING PROTOTYPE','PHYSICAL SCALE MODEL')
card_png(Wk+'/card_open.png','AIU SMART CAMPUS','CYBER-PHYSICAL CONTROL SYSTEM','ALAMEIN INTERNATIONAL UNIVERSITY')
card_png(Wk+'/card_end.png','AIU SMART CAMPUS','CYBER-PHYSICAL CONTROL SYSTEM','ALAMEIN INTERNATIONAL UNIVERSITY  ·  GRADUATION PROJECT')
LAB=lambda png,st,d,fi=0.5,fo=0.5:f"movie={png},format=rgba,fade=t=in:st={st}:d={fi}:alpha=1,fade=t=out:st={st+d-fo}:d={fo}:alpha=1[l]"
def with_label(inp,out,png,st,d,pre,extra_in=[]):
    fc=f"[0:v]{pre}[b];{LAB(png,st,d)};[b][l]overlay,{FMT}[v]"
    run(extra_in+inp+['-filter_complex',fc,'-map','[v]','-c:v','libx264','-crf','16','-an',out])
# s0 opening card: 3 s, fade in from black
run(['-loop','1','-t','3','-i',Wk+'/card_open.png','-vf',f'fade=t=in:st=0:d=1.0,fade=t=out:st=2.5:d=0.5,{FMT}','-c:v','libx264','-crf','16','-an',Wk+'/s0.mp4'])
# s1 human door entry (frames 45..398 @30fps = 11.8 s), upscaled to 1080p, verification overlay at native 1080p
run(['-framerate','30','-start_number','45','-i',DOOR_FR,'-framerate','30','-start_number','45','-i',DOOR_OV,
     '-i',Wk+'/lab_door.png','-filter_complex',f"[0:v]scale=1920:1080:flags=lanczos,{GRADE},format=rgba[a];[1:v]format=rgba[o];[a][o]overlay[ab];[2:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=2.8:d=0.5:alpha=1[l];[ab][l]overlay,{FMT}[v]",
     '-map','[v]','-c:v','libx264','-crf','16','-an',Wk+'/s1.mp4'])
# s2 classroom with people (300 frames = 10 s)
run(['-framerate','30','-start_number','1','-i',CLS_FR,'-i',Wk+'/lab_cls.png','-i',Wk+'/lab_cls_b.png','-filter_complex',
     f"[0:v]scale=1920:1080:flags=lanczos,{GRADE},format=rgba[a];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=3.0:d=0.5:alpha=1[l1];[2:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=9.0:d=0.5:alpha=1[l2];[a][l1]overlay[x];[x][l2]overlay,{FMT}[v]",
     '-map','[v]','-c:v','libx264','-crf','16','-an',Wk+'/s2.mp4'])
# s3 dashboard (provisional, still-based; carries its own SIMULATED caption) first 9 s
run(['-t','9','-i',DASH,'-i',Wk+'/lab_dash.png','-filter_complex',f"[0:v]format=rgba[a];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=3.5:d=0.5:alpha=1[l];[a][l]overlay,{FMT}[v]",'-map','[v]','-c:v','libx264','-crf','16','-an',Wk+'/s3.mp4'])
# s4 prototype reveal, first 8 s
run(['-t','6.5','-i',PROTO,'-i',Wk+'/lab_proto.png','-filter_complex',f"[0:v]format=rgba[a];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=3.0:d=0.5:alpha=1[l];[a][l]overlay,{FMT}[v]",'-map','[v]','-c:v','libx264','-crf','16','-an',Wk+'/s4.mp4'])
# s5 closing card 4.5 s
run(['-loop','1','-t','4.5','-i',Wk+'/card_end.png','-vf',f'fade=t=in:st=0:d=0.8,fade=t=out:st=3.7:d=0.8,{FMT}','-c:v','libx264','-crf','16','-an',Wk+'/s5.mp4'])
durs=[3.0,11.8,10.0,9.0,6.5,4.5]; D=0.5; offs=[]; t=0
for i in range(5): t+=durs[i]-D; offs.append(t)
fc=''; prev='[0]'
for i in range(5):
    out='[v]' if i==4 else f'[x{i+1}]'
    fc+=f'{prev}[{i+1}]xfade=transition=fade:duration={D}:offset={offs[i]}{out};'; prev=out
fc=fc.rstrip(';')
run(sum([['-i',Wk+f'/s{i}.mp4'] for i in range(6)],[])+['-filter_complex',fc,'-map','[v]','-c:v','libx264','-pix_fmt','yuv420p','-crf','18','-r','30','-an','-movflags','+faststart',O+'/AIU_TRAILER_REVIEW_v2_HUMANS.mp4'])
print('done, expected duration',sum(durs)-D*5)
