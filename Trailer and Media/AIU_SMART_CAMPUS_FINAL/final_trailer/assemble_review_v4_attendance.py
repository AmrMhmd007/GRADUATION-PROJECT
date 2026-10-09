"""Review cut v4: adds the indoor-camera + attendance-workflow scene between the classroom and the dashboard.
Silent -> AIU_SMART_CAMPUS_FINAL_SILENT.mp4 ; with original synthesized soundtrack -> AIU_SMART_CAMPUS_FINAL_REVIEW.mp4.
Does not touch any earlier review cut. Reuses work_v3 s0 (opening) and s1 (door) which are already verified."""
import subprocess, os, shutil, sys
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'audio_v4'))
from timeline_v4 import DUR,ORDER,OFF,TOTAL
O=os.path.dirname(os.path.abspath(__file__)); R=os.path.abspath(O+'/..'); Wk=O+'/work_v4'; os.makedirs(Wk,exist_ok=True)
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
        w=sum(d.textlength(ch,font=C(19))+2 for ch in bottom); d.rounded_rectangle((90,960,90+w+44,1006),radius=8,fill=(7,12,24,170)); spaced(d,(112,971),bottom,C(19),(235,238,245,230),2)
    im.save(path)
def run(a): subprocess.run(['ffmpeg','-y','-loglevel','error']+a,check=True)
FMT='fps=30,format=yuv420p,setsar=1'; GRADE='eq=contrast=1.05:saturation=1.04:gamma=0.98,vignette=PI/6'
V3=O+'/work_v3'
CLS_FR=R+'/blender/human_classroom/renders/native_1080/f_%04d.png'; ATT=R+'/blender/attendance_scene'
DASH=R+'/recordings/AIU_OCCUPANCY_DASHBOARD_PROVISIONAL.mp4'; PROTO=R+'/after_effects/prototype_reveal/AIU_PROTOTYPE_REVEAL_PREVIEW_v2.mp4'
ENC=['-c:v','libx264','-crf','16','-an']
only=sys.argv[1:]
def want(k): return not only or k in only
# s0, s1 reused (verified in v3)
for k,src in (('s0','s0.mp4'),('s1','s1.mp4')): shutil.copy(V3+'/'+src,Wk+'/'+k+'.mp4')
# s2 classroom 8.8 s (frames 1-264)
label_png(Wk+'/lab_cls.png','02  SMART CLASSROOM','ANIMATED CHARACTERS — NOT LIVE CAMERA DETECTION')
label_png(Wk+'/lab_cls_b.png',None,None,'CONCEPT VISUALISATION  ·  ANIMATED PEOPLE  ·  NO OCCUPANCY DATA SHOWN')
if want('s2'): run(['-framerate','30','-start_number','1','-i',CLS_FR,'-i',Wk+'/lab_cls.png','-i',Wk+'/lab_cls_b.png','-filter_complex',
     f"[0:v]scale=1920:1080:flags=lanczos,{GRADE},format=rgba[a];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=3.0:d=0.5:alpha=1[l1];[2:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=8.0:d=0.5:alpha=1[l2];[a][l1]overlay[x];[x][l2]overlay,{FMT}[v]",
     '-map','[v]','-frames:v','264']+ENC+[Wk+'/s2.mp4'])
# s3 attendance camera: Blender 1-300 then POV ping-pong back 299->241 (idle motion plays in reverse), + transparent overlay (360 frames = 12 s)
if want('s3'):
    lst=Wk+'/att_list.txt'; order=list(range(1,301))+list(range(299,240,-1))
    with open(lst,'w') as f:
        for n in order: f.write("file '%s/renders/native_1080/f_%04d.png'\nduration 0.0333333\n"%(ATT,n))
    run(['-f','concat','-safe','0','-i',lst,'-framerate','30','-i',ATT+'/overlay/frames_att/ov_%04d.png','-filter_complex',
         f"[0:v]fps=30,scale=1920:1080:flags=lanczos,{GRADE},format=rgba[a];[1:v]format=rgba[o];[a][o]overlay,{FMT}[v]",'-map','[v]','-frames:v','360']+ENC+[Wk+'/s3.mp4'])
if want('s3b'):
    run(['-framerate','30','-i',ATT+'/overlay/frames_results/rs_%04d.png','-vf',FMT,'-frames:v','165']+ENC+[Wk+'/s3b.mp4'])
# s4 dashboard, s5 prototype, s6 closing
label_png(Wk+'/lab_dash.png','05  CAMPUS DASHBOARD','SIMULATED OCCUPANCY DATA — NOT LIVE HARDWARE TELEMETRY')
label_png(Wk+'/lab_proto.png','06  ENGINEERING PROTOTYPE','PHYSICAL SCALE MODEL')
if want('s4'): run(['-t','7','-i',DASH,'-i',Wk+'/lab_dash.png','-filter_complex',f"[0:v]format=rgba[a];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=3.5:d=0.5:alpha=1[l];[a][l]overlay,{FMT}[v]",'-map','[v]']+ENC+[Wk+'/s4.mp4'])
if want('s5'): run(['-t','6','-i',PROTO,'-i',Wk+'/lab_proto.png','-filter_complex',f"[0:v]format=rgba[a];[1:v]format=rgba,fade=t=in:st=0.3:d=0.5:alpha=1,fade=t=out:st=2.8:d=0.5:alpha=1[l];[a][l]overlay,{FMT}[v]",'-map','[v]']+ENC+[Wk+'/s5.mp4'])
shutil.copy(V3+'/s5.mp4',Wk+'/s6.mp4')   # closing card (4.5 s) from v3
if only: sys.exit()
# assemble
segs=['s0','s1','s2','s3','s3b','s4','s5','s6']; durs=[DUR[k] for k in ORDER]; D=0.5
trans=['fade','fade','fade','fade','smoothleft','fade','fade']
offs=[]; t=0
for i in range(7): t+=durs[i]-D; offs.append(t)
fc=''; prev='[0]'
for i in range(7):
    out='[v]' if i==6 else f'[x{i+1}]'; fc+=f'{prev}[{i+1}]xfade=transition={trans[i]}:duration={D}:offset={offs[i]}{out};'; prev=out
fc=fc.rstrip(';'); sil=O+'/AIU_SMART_CAMPUS_FINAL_SILENT.mp4'
run(sum([['-i',Wk+f'/{s}.mp4'] for s in segs],[])+['-filter_complex',fc,'-map','[v]','-c:v','libx264','-pix_fmt','yuv420p','-crf','18','-r','30','-an','-movflags','+faststart',sil])
wav=O+'/audio_v4/AIU_TRAILER_v4_soundtrack.wav'
if os.path.exists(wav):
    run(['-i',sil,'-i',wav,'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',O+'/AIU_SMART_CAMPUS_FINAL_REVIEW.mp4'])
print('done, expected duration',sum(durs)-D*7,TOTAL)
