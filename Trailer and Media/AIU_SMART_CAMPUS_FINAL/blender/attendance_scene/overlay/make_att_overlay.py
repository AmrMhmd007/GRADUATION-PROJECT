"""Transparent overlay for the attendance-camera scene (360 output frames = Blender 1-300 then POV ping-pong).
i 0-89 shot1 (camera reveal), 90-209 shot2 (coverage), 210-359 shot3 (camera view + pipeline). Concept visualisation only."""
import cairo, json, os, sys
from uilib import *
HERE=os.path.dirname(os.path.abspath(__file__)); FR=HERE+'/frames_att'; os.makedirs(FR,exist_ok=True)
PROJ=json.load(open(HERE+'/proj.json')) if os.path.exists(HERE+'/proj.json') else {}
N=330
def bmap(i):
    if i<84: return 1+round(i*89/83)
    if i<186: return 91+(i-84)
    j=i-186; return 211+j if j<90 else 299-(j-90)
import json as _j; _j.dump([bmap(i) for i in range(N)],open(HERE+'/frame_map.json','w'))
def lerp(a,b,t): return a+(b-a)*t
def callout(c,label,pt,off,a,sub=None):
    x,y=pt; lx,ly=x+off[0],y+off[1]
    c.set_source_rgba(*WHITE,0.85*a); c.set_line_width(2); c.move_to(x,y); c.line_to(lx,ly); c.stroke()
    c.arc(x,y,6,0,6.2832); c.set_source_rgba(*WHITE,a); c.fill()
    w=tw(c,label,22,True,3)+40; bx=lx if off[0]>=0 else lx-w
    rr(c,bx,ly-26,w,52,10); c.set_source_rgba(*NAVY,0.82*a); c.fill_preserve(); c.set_source_rgba(1,1,1,0.25*a); c.set_line_width(1.2); c.stroke()
    text(c,label,bx+20,ly+7,22,WHITE,a,True,3)
    if sub: text(c,sub,bx+20,ly+44,16,GREY,a,False,2)
STEPS=[('CLASSROOM CAMERA','wall-mounted camera (rendered prop)','CONCEPT',False),
       ('IMAGE PROCESSING','frame analysis at the camera node (design)','CONCEPT',False),
       ('STUDENT PRESENCE ANALYSIS','anonymous head-count only · no identities','BACKEND INGEST: IMPLEMENTED',True),
       ('ATTENDANCE RECORD','per-student present / absent','CONCEPT · NOT IMPLEMENTED',False)]
START=[188,216,252,291]
def frame(i):
    s=cairo.ImageSurface(cairo.FORMAT_ARGB32,W,H); c=cairo.Context(s)
    ha=ease((i-4)/10)*(1-ease((i-174)/9)) if i<184 else ease((i-188)/10)
    g=cairo.LinearGradient(0,0,0,230); g.add_color_stop_rgba(0,*NAVY,0.62*ha); g.add_color_stop_rgba(1,*NAVY,0); c.rectangle(0,0,W,230); c.set_source(g); c.fill()
    # header
    if i<184: chapter(c,'INDOOR CLASSROOM CAMERA','CONCEPT VISUALISATION — RENDERED CLASSROOM',ease((i-4)/10)*(1-ease((i-174)/9)))
    else: chapter(c,'ATTENDANCE WORKFLOW','IMPLEMENTED VS CONCEPT — SEE LEGEND',ease((i-188)/10))
    if i<186: chip(c,'CONCEPT VISUALISATION  ·  RENDERED CLASSROOM  ·  NOT A CONNECTED DEVICE',ease((i-8)/10)*(1-ease((i-174)/9)))
    # shot 1 callout
    if 40<=i<=83 and 'cam' in PROJ:
        p=PROJ['cam'].get(str(bmap(i)));
        if p: callout(c,'CLASSROOM CAMERA',p,(150,-110),ease((i-40)/12),'indoor camera mounted above the board')
    # shot 2 callout
    if 110<=i<=185 and 'floor' in PROJ:
        p=PROJ['floor'].get(str(bmap(i)))
        if p: callout(c,'MONITORED SEATING AREA',p,(-60,150),ease((i-110)/12)*(1-ease((i-178)/7)),'approximate coverage · illustrative')
    # shot 3
    if i>=186:
        a=ease((i-187)/10)
        for (x,y,dx,dy) in ((60,60,1,1),(W-60,60,-1,1),(60,H-60,1,-1),(W-60,H-60,-1,-1)):
            c.set_source_rgba(*WHITE,0.75*a); c.set_line_width(3); c.move_to(x,y+dy*50); c.line_to(x,y); c.line_to(x+dx*50,y); c.stroke()
        pill(c,W-96,80,'CAMERA VIEW · RENDERED SCENE · NOT A LIVE FEED',17,WHITE,a,False,True,2.2,anchor='l') if False else None
        w=tw(c,'CAMERA VIEW · RENDERED SCENE · NOT A LIVE FEED',17,True,2.2)+34
        pill(c,W-96-w,70,'CAMERA VIEW · RENDERED SCENE · NOT A LIVE FEED',17,WHITE,a)
        px,py,pw,ph=96,742,1728,250
        rr(c,px,py,pw,ph,16); c.set_source_rgba(*NAVY,0.84*a); c.fill_preserve(); c.set_source_rgba(1,1,1,0.15*a); c.set_line_width(1.2); c.stroke()
        xs=[px+216*(1+2*k) for k in range(4)]; cy=py+56
        for k in range(3):
            pr=ease((i-START[k+1]+10)/12)
            c.set_source_rgba(1,1,1,0.16*a); c.set_line_width(2); c.move_to(xs[k]+34,cy); c.line_to(xs[k+1]-34,cy); c.stroke()
            if pr>0:
                col=STEPS[k+1][3] and BLUE or WHITE
                c.set_source_rgba(*WHITE,0.85*a); c.move_to(xs[k]+34,cy); c.line_to(xs[k]+34+(xs[k+1]-xs[k]-68)*pr,cy); c.stroke()
        for k,(name,sub,badge,impl) in enumerate(STEPS):
            on=i>=START[k]; col=(BLUE if impl else AMBER) if on else WHITE
            c.new_path(); c.arc(xs[k],cy,22,0,6.2832)
            if on and impl: c.set_source_rgba(*BLUE,0.95*a); c.fill()
            else:
                c.set_source_rgba(*NAVY,0.9*a); c.fill_preserve(); c.set_line_width(2.4)
                if on: c.set_dash([6,5])
                c.set_source_rgba(*col,(1 if on else 0.3)*a); c.stroke(); c.set_dash([])
            text(c,str(k+1),xs[k],cy+7,20,(NAVY if (on and impl) else col),(1 if on else 0.4)*a,True,0,'c')
            text(c,name,xs[k],cy+62,21,WHITE,(1 if on else 0.4)*a,True,2.2,'c')
            text(c,sub,xs[k],cy+90,16,GREY,(1 if on else 0.35)*a,False,0.8,'c')
            if on: pill(c,xs[k],cy+108,badge,15,BLUE if impl else AMBER,ease((i-START[k])/8)*a,fill=impl,anchor='c')
        text(c,'FILLED NODE = IMPLEMENTED IN BACKEND (occupancy count ingest)    ·    DASHED NODE = CONCEPT VISUALISATION',px+pw/2,py+ph-18,15,GREY,0.9*a,False,1.6,'c')
    return s
if '--test' in sys.argv:
    for i in (30,80,150,180,200,230,260,300,329): frame(i).write_to_png(FR+f'/test_{i}.png')
    sys.exit()
for i in range(N): frame(i).write_to_png(FR+f'/ov_{i+1:04d}.png')
print('done')
