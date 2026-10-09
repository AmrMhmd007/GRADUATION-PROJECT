"""Narrated 115 s trailer. Clip i occupies film [T_i - XF, T_{i+1}] (first XF seconds cross-dissolve with the previous clip; content starts at T_i via a held first frame).
Usage: python3 assemble_final_vo.py [clipname ...]   (only rebuild those clips)   |  python3 assemble_final_vo.py --all
Outputs: AIU_SMART_CAMPUS_FINAL_SILENT.mp4 (silent) and AIU_SMART_CAMPUS_FINAL_TRAILER.mp4 (with AIU_SMART_CAMPUS_FINAL_MIX.wav, AAC)."""
import subprocess, os, sys, json, shutil, math
from PIL import Image, ImageDraw, ImageFont
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
from timeline_vo import *
R=os.path.abspath(HERE+'/../..'); WK=HERE+'/work/clips'; os.makedirs(WK,exist_ok=True); CUE=HERE+'/work/cues'; os.makedirs(CUE,exist_ok=True)
C=lambda s,b=False:ImageFont.truetype('/usr/share/fonts/truetype/crosextra/Carlito-%s.ttf'%('Bold' if b else 'Regular'),s)
NAVY=(7,12,24); WHITE=(238,242,250); BLUE=(120,160,225); GREY=(150,160,180); AMBER=(255,168,40); GREEN=(60,200,115)
def run(a): subprocess.run(['ffmpeg','-y','-loglevel','error']+a,check=True)
def spaced(d,xy,s,font,fill,sp=0,anchor='l'):
    w=sum(d.textlength(ch,font=font)+sp for ch in s)-sp; x,y=xy
    if anchor=='c': x-=w/2
    for ch in s: d.text((x,y),ch,font=font,fill=fill); x+=d.textlength(ch,font=font)+sp
def chapter_png(path,ch,sub=None,bottom=None):
    im=Image.new('RGBA',(1920,1080),(0,0,0,0)); d=ImageDraw.Draw(im)
    if ch:
        d.rectangle((96,64,100,112),fill=BLUE+(255,)); spaced(d,(120,64),ch,C(30,True),WHITE+(235,),4)
        if sub: spaced(d,(120,100),sub,C(18),GREY+(235,),3)
    if bottom: chip(d,bottom)
    im.save(path)
def chip(d,s,x=90,y=960,col=(235,238,245),size=19,accent=None):
    w=sum(d.textlength(ch,font=C(size))+2 for ch in s)*1.04+8; d.rounded_rectangle((x,y,x+w+44,y+46),radius=8,fill=(7,12,24,185))
    if accent: d.rounded_rectangle((x,y,x+6,y+46),radius=3,fill=accent+(255,))
    spaced(d,(x+22,y+11),s,C(size),col+(235,),2)
def cue_png(path,items):
    """items: list of (text,x,y,size,color,bold,chip?)"""
    im=Image.new('RGBA',(1920,1080),(0,0,0,0)); d=ImageDraw.Draw(im)
    for t,x,y,size,col,bold,ch in items:
        if ch:
            w=sum(d.textlength(c_,font=C(size,bold))+2.5 for c_ in t)+48; d.rounded_rectangle((x,y,x+w,y+size+30),radius=10,fill=(7,12,24,205),outline=col+(255,),width=2); spaced(d,(x+24,y+13),t,C(size,bold),col+(255,),2.5)
        else: spaced(d,(x,y),t,C(size,bold),col+(255,),3)
    im.save(path)
def overlay_chain(inp_label, cues, L):
    """cues: [(png,t0,t1)] -> returns (extra_inputs, filter string fragment taking [base] and giving [vout]); png alpha fades 0.3 s"""
    ins=[]; fc=''; prev='[base]'
    for k,(png,a,b) in enumerate(cues):
        ins+=['-loop','1','-t',f'{L:.3f}','-i',png]
        idx=k+1+inp_label
        fc+=f"[{idx}:v]format=rgba,fade=t=in:st={a:.3f}:d=0.3:alpha=1,fade=t=out:st={max(a,b-0.3):.3f}:d=0.3:alpha=1[c{k}];{prev}[c{k}]overlay=format=auto[o{k}];"; prev=f'[o{k}]'
    return ins,fc,prev
FMT='fps=30,format=yuv420p,setsar=1'
GRADE='eq=contrast=1.05:saturation=1.04:gamma=0.98,vignette=PI/6'
def times(name):
    a,b=seg(name); i=[n for n,_,_ in SEG].index(name); first=(i==0)
    L=(b-a)+(0 if first else XF); return a,b,L,first
def pad_start(first): return '' if first else f',tpad=start_duration={XF}:start_mode=clone'
def build(name, inputs, vf, cues=(), extra_fc=''):
    """inputs: ffmpeg input args for source 0 (list); vf: filter on [0:v] (must output a video named by caller adding pad). cues local to NOMINAL start (add XF shift)."""
    a,b,L,first=times(name); sh=0 if first else XF
    cl=[(p,t0+sh,t1+sh) for p,t0,t1 in cues]
    ins,fc,prev=overlay_chain(0,cl,L)
    graph=f"[0:v]{vf}{pad_start(first)},trim=duration={L:.3f},setpts=PTS-STARTPTS,format=rgba[base];{fc}{prev}{FMT}[v]"
    run(inputs+ins+['-filter_complex',graph,'-map','[v]','-frames:v',str(math.ceil(L*30-1e-6)),'-c:v','libx264','-crf','15','-an','-pix_fmt','yuv420p',f'{WK}/{name}.mp4'])
    return f'{WK}/{name}.mp4'
def seqin(pattern,start,n=None,fps=30): return ['-framerate',str(fps),'-start_number',str(start)]+(['-t',f'{n/fps:.4f}'] if n else [])+['-i',pattern]
DOOR_FR=R+'/blender/human_entry/renders/native_1080/f_%04d.png'; DOOR_OV=R+'/blender/human_entry/overlay/frames_human/ov_%04d.png'
CLS_FR=R+'/blender/human_classroom/renders/native_1080/f_%04d.png'; ATT=R+'/blender/attendance_scene'
SW=R+'/recordings/software/edited'
def swclip(name,takefile,t0,cues=(),zoom=None):
    """real screen-recording take -> clip window starting at source time t0 (s)."""
    a,b,L,first=times(name); p=f'{SW}/{takefile}'
    if not os.path.exists(p): raise SystemExit(f'MISSING recording {p}')
    return build(name,['-ss',f'{t0:.3f}','-i',p],f'scale=1920:1080:flags=lanczos,{GRADE}',cues)

# ---------------- clip builders (non-software) ----------------
def b_open():
    A=R+'/animation/A.mp4'
    P=lambda n:f'{CUE}/{n}.png'
    cue_png(P('open_vision'),[('A NEW LEVEL OF UNIVERSITY MANAGEMENT',96,900,28,WHITE,True,True)])
    base=[('TECHNOLOGY',96,900,28,BLUE,True,True)]
    states=[base,base+[('SECURITY',96+330,900,28,BLUE,True,True)],base+[('SECURITY',96+330,900,28,BLUE,True,True),('SMART AUTOMATION',96+620,900,28,BLUE,True,True)],
            base+[('SECURITY',96+330,900,28,BLUE,True,True),('SMART AUTOMATION',96+620,900,28,BLUE,True,True),('=  ONE INTEGRATED SYSTEM',96+1000,900,28,WHITE,True,True)]]
    ts=[11.9,12.8,13.6,14.4,15.3]
    cues=[(P('open_vision'),7.0,10.4)]
    for k,st in enumerate(states): cue_png(P(f'open_s{k}'),st); cues.append((P(f'open_s{k}'),ts[k],ts[k+1]+(0.0 if k<3 else 0.0)))
    return build('open',['-ss','5.5','-i',A],'scale=1920:1080,'+GRADE.split(',vignette')[0],cues)
def b_doorA():
    P=f'{CUE}/doorA.png'; chapter_png(P,'ACCESS CONTROL','CONCEPT VISUALISATION — ANIMATED CHARACTER',None)
    c2=f'{CUE}/doorA_b.png'; cue_png(c2,[('INSTRUCTOR APPROACHES A SECURED CLASSROOM DOOR',96,900,26,WHITE,True,True)])
    return build('doorA',seqin(DOOR_FR,45,75),f'scale=1920:1080:flags=lanczos,{GRADE}',[(P,0.2,2.5),(c2,0.4,2.4)])
def b_doorB():
    P=f'{CUE}/doorB_bottom.png'; chapter_png(P,None,None,'CONCEPT VISUALISATION  ·  ANIMATED CHARACTER  ·  NOT LIVE HARDWARE')
    a,b,L,first=times('doorB')
    sh=XF
    ins=seqin(DOOR_FR,120,278)+seqin(DOOR_OV,120,278)+['-loop','1','-t',f'{L:.2f}','-i',P]
    g=f"[0:v]scale=1920:1080:flags=lanczos,{GRADE},format=rgba[a];[1:v]format=rgba[o];[a][o]overlay[ab];[2:v]format=rgba,fade=t=in:st={0.3+sh}:d=0.4:alpha=1,fade=t=out:st={8.4+sh}:d=0.4:alpha=1[l];[ab][l]overlay,tpad=start_duration={XF}:start_mode=clone,trim=duration={L:.3f},setpts=PTS-STARTPTS,{FMT}[v]"
    run(ins+['-filter_complex',g,'-map','[v]','-frames:v',str(math.ceil(L*30-1e-6)),'-c:v','libx264','-crf','15','-an',f'{WK}/doorB.mp4']); return f'{WK}/doorB.mp4'
def b_classroom():
    P=f'{CUE}/cls.png'; chapter_png(P,'SMART CLASSROOM','ANIMATED CHARACTERS — NOT LIVE CAMERA DETECTION',None)
    c2=f'{CUE}/cls_b.png'; cue_png(c2,[('LECTURER AND SEATED STUDENTS  ·  CONCEPT VISUALISATION',96,900,26,WHITE,True,True)])
    return build('classroom',seqin(CLS_FR,1,85),f'scale=1920:1080:flags=lanczos,{GRADE}',[(P,0.1,2.6),(c2,0.3,2.6)])
def b_camera():
    fm=json.load(open(ATT+'/overlay/frame_map.json')); lst=f'{HERE}/work/att_list.txt'
    with open(lst,'w') as f:
        for n in fm: f.write("file '%s/renders/native_1080/f_%04d.png'\nduration 0.0333333\n"%(ATT,n))
    a,b,L,first=times('camera')
    g=f"[0:v]fps=30,scale=1920:1080:flags=lanczos,{GRADE},format=rgba[a];[1:v]format=rgba[o];[a][o]overlay,tpad=start_duration={XF}:start_mode=clone,trim=duration={L:.3f},setpts=PTS-STARTPTS,{FMT}[v]"
    run(['-f','concat','-safe','0','-i',lst]+seqin(ATT+'/overlay/frames_att/ov_%04d.png',1,len(fm))+['-filter_complex',g,'-map','[v]','-frames:v',str(math.ceil(L*30-1e-6)),'-c:v','libx264','-crf','15','-an',f'{WK}/camera.mp4']); return f'{WK}/camera.mp4'
def b_results():
    return build('att_results',seqin(ATT+'/overlay/frames_results/rs_%04d.png',1,129),FMT)
def b_proto():
    P=f'{CUE}/proto.png'; cue_png(P,[('SUPPLIED PROTOTYPE DESIGN IMAGE  ·  UNALTERED  ·  CONCEPT / PHYSICAL SCALE MODEL',96,1034,15,GREY,False,False)])
    return build('prototype',['-ss','1.6','-i',R+'/after_effects/prototype_reveal/AIU_PROTOTYPE_REVEAL_PREVIEW_v2.mp4'],'scale=1920:1080',[(P,0.2,4.3)])
def b_arch(): return build('arch',seqin(HERE+'/work/arch/a_%04d.png',1,276),FMT)
def b_closing():
    a,b,L,first=times('closing')
    # closing frames already include fade-out at the end; clone first frame for the dissolve pad
    return build('closing',seqin(HERE+'/work/close/c_%04d.png',1,279),FMT)
BUILDERS={'open':b_open,'doorA':b_doorA,'doorB':b_doorB,'classroom':b_classroom,'camera':b_camera,'att_results':b_results,'prototype':b_proto,'arch':b_arch,'closing':b_closing}

def b_montage():
    """2x2 recap of the capabilities shown above (re-used footage, intentionally a labelled summary)."""
    a,b,L,first=times('montage'); sh=XF
    srcs=[(f'{WK}/doorB.mp4',3.0,'SECURE ACCESS','concept animation'),(f'{WK}/camera.mp4',3.6,'ROOM MONITORING','concept visualisation'),
          (f'{WK}/camera.mp4',9.0,'ATTENDANCE WORKFLOW','concept · not implemented'),(f'{WK}/dash_home.mp4',1.2,'CAMPUS MANAGEMENT','real software recording')]
    pos=[(0,0),(960,0),(0,540),(960,540)]
    for k,(p,ss,t,sub) in enumerate(srcs):
        im=Image.new('RGBA',(960,540),(0,0,0,0)); d=ImageDraw.Draw(im); d.rectangle((0,0,959,539),outline=BLUE+(255,),width=3)
        d.rounded_rectangle((24,24,24+sum(d.textlength(c_,font=C(26,True))+3 for c_ in t)+40,24+70),radius=8,fill=(7,12,24,215)); spaced(d,(44,32),t,C(26,True),WHITE+(255,),3); spaced(d,(44,64),sub.upper(),C(15),GREY+(255,),2)
        im.save(f'{CUE}/mont_{k}.png')
    ins=[]; fc=''
    for k,(p,ss,t,sub) in enumerate(srcs): ins+=['-ss',str(ss),'-t',f'{L:.2f}','-i',p]
    for k in range(4): ins+=['-loop','1','-t',f'{L:.2f}','-i',f'{CUE}/mont_{k}.png']
    fc="color=c=0x070c18:s=1920x1080:r=30,format=rgba[bg];"
    prev='[bg]'
    for k in range(4):
        t0=0.15+0.65*k+sh
        fc+=f"[{k}:v]scale=960:540,format=rgba,fade=t=in:st={t0:.2f}:d=0.35:alpha=1[p{k}];[{4+k}:v]format=rgba,fade=t=in:st={t0+0.1:.2f}:d=0.3:alpha=1[t{k}];{prev}[p{k}]overlay={pos[k][0]}:{pos[k][1]}[q{k}];[q{k}][t{k}]overlay={pos[k][0]}:{pos[k][1]}[r{k}];"; prev=f'[r{k}]'
    fc+=f"{prev}tpad=start_duration=0:start_mode=clone,trim=duration={L:.3f},setpts=PTS-STARTPTS,{FMT}[v]"
    run(ins+['-filter_complex',fc,'-map','[v]','-frames:v',str(math.ceil(L*30-1e-6)),'-c:v','libx264','-crf','15','-an',f'{WK}/montage.mp4']); return f'{WK}/montage.mp4'
BUILDERS['montage']=b_montage

def _cap(name,items):
    P=f'{CUE}/{name}.png'; im=Image.new('RGBA',(1920,1080),(0,0,0,0)); d=ImageDraw.Draw(im)
    y=964
    for t,acc in items: chip(d,t,90,y,accent=acc); y-=58
    im.save(P); return P
def _mk_access():
    r=R+'/recordings/software/raw'; os.makedirs(SW,exist_ok=True)
    run(['-ss','0.9','-t','9.3','-i',r+'/take_auth.mp4','-ss','1.4','-t','2.7','-i',r+'/take_events_inv.mp4','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0,fps=30,scale=1920:1080[v]','-map','[v]','-c:v','libx264','-crf','14','-pix_fmt','yuv420p',SW+'/sw_access.mp4'])
def _mk(name,take,ss,dur):
    run(['-ss',str(ss),'-t',str(dur),'-i',R+f'/recordings/software/raw/{take}.mp4','-vf','fps=30,scale=1920:1080','-c:v','libx264','-crf','14','-pix_fmt','yuv420p',f'{SW}/{name}.mp4'])
REC=('REAL SOFTWARE RECORDING',BLUE)
def _sw(name,src,mk,caps):
    def f():
        if mk: mk()
        return swclip(name,src,0,[(_cap(name,c),0.4,seg(name)[1]-seg(name)[0]+XF-0.1) for c in [caps]])
    return f
def _wrap(name,take,ss,dur,caps):
    return _sw(name,name+'.mp4',lambda:_mk(name,take,ss,dur),caps)
SW_CLIPS={
 'sw_access':_sw('sw_access','sw_access.mp4',_mk_access,[('Access & Authorization check: GRANTED (backend rule evaluation)',GREEN),REC]),
 'sw_entry':_wrap('sw_entry','take_events_scroll',1.0,4.8,[('Access events log written by the backend',GREEN),REC]),
 'dash_home':_wrap('dash_home','take_home',1.0,5.6,[('Command Hub: SIMULATED demo data',AMBER),REC]),
 'dash_rooms':_wrap('dash_rooms','take_zones',1.5,4.0,[('Rooms & zones: demo data',AMBER),REC]),
 'dash_occ':_wrap('dash_occ','take_occ',1.0,3.4,[('Occupancy: SIMULATED, not live camera or hardware',AMBER),REC]),
 'dash_status':_wrap('dash_status','take_cmd',1.0,4.8,[('Command Center: access events, demo database',AMBER),REC]),
 'dash_auto':_wrap('dash_auto','take_auto',1.2,4.9,[('Automation engine: rules & decision log (demo data)',AMBER),REC]),
 'sw_map':_sw('sw_map','sw_map.mp4',lambda:run(['-ss','1.0','-t','2.9','-i',R+'/recordings/software/raw/take_events_scroll.mp4','-ss','5.73','-t','2.2','-i',R+'/recordings/software/raw/take_auto.mp4','-ss','5.0','-t','1.8','-i',R+'/recordings/software/raw/take_zones.mp4','-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0,fps=30,scale=1920:1080[v]','-map','[v]','-c:v','libx264','-crf','14','-pix_fmt','yuv420p',SW+'/sw_map.mp4']),[('Access events, automation rules and zones: one backend (demo data)',AMBER),REC]),
}

def final(silent_only=False):
    names=[n for n,_,_ in SEG]; miss=[n for n in names if not os.path.exists(f'{WK}/{n}.mp4')]
    if miss: raise SystemExit('clips missing: '+', '.join(miss))
    T_=[a for _,a,_ in SEG]+[TOTAL]; fc=''; prev='[0:v]'
    for k in range(len(names)-1):
        out='[v]' if k==len(names)-2 else f'[x{k+1}]'; off=T_[k+1]-XF
        fc+=f'{prev}[{k+1}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}{out};'; prev=out
    sil=HERE+'/AIU_SMART_CAMPUS_FINAL_SILENT.mp4'
    run(sum([['-i',f'{WK}/{n}.mp4'] for n in names],[])+['-filter_complex',fc.rstrip(';'),'-map','[v]','-c:v','libx264','-pix_fmt','yuv420p','-crf','17','-r','30','-t',str(TOTAL),'-an','-movflags','+faststart',sil])
    mix=HERE+'/AIU_SMART_CAMPUS_FINAL_MIX.wav'
    if os.path.exists(mix) and not silent_only:
        run(['-i',sil,'-i',mix,'-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','256k','-ar','48000','-ac','2','-t',str(TOTAL),'-movflags','+faststart',HERE+'/AIU_SMART_CAMPUS_FINAL_TRAILER.mp4'])
if __name__=='__main__':
    args=[a for a in sys.argv[1:] if not a.startswith('--')]
    todo=args or ([n for n in list(BUILDERS)+list(SW_CLIPS)] if '--all' in sys.argv else [])
    for n in todo:
        print('build',n,(BUILDERS.get(n) or SW_CLIPS[n])())
    if '--final' in sys.argv: final('--silent' in sys.argv)
