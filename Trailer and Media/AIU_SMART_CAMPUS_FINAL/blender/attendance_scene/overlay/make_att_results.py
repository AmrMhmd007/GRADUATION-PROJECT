"""Shot 4: attendance RESULT interface. CONCEPT interface with demonstration data (no attendance backend/UI exists in the project).
Left: occupancy count card (backend capability, SIMULATED value). Right: concept attendance roster (demo placeholders, no real students)."""
import cairo, os, sys
from uilib import *
HERE=os.path.dirname(os.path.abspath(__file__)); FR=HERE+'/frames_results'; os.makedirs(FR,exist_ok=True)
BG=HERE+'/results_bg.png' if os.path.exists(HERE+'/results_bg.png') else None
N=129
ABSENT={4,8,11}
LIGHT=(0.965,0.972,0.99); CARD=(1,1,1); TXT=(0.10,0.12,0.30); MUTE=(0.40,0.43,0.55)
def card(c,x,y,w,h,a):
    rr(c,x,y,w,h,18); c.set_source_rgba(*CARD,0.97*a); c.fill_preserve(); c.set_source_rgba(0.1,0.12,0.3,0.12*a); c.set_line_width(1.2); c.stroke()
def frame(i):
    s=cairo.ImageSurface(cairo.FORMAT_RGB24,W,H); c=cairo.Context(s)
    if BG:
        c.set_source_surface(cairo.ImageSurface.create_from_png(BG),0,0); c.paint()
    else: c.set_source_rgb(*NAVY); c.paint()
    c.set_source_rgba(*NAVY,0.78); c.paint()
    chapter(c,'ATTENDANCE WORKFLOW','RESULT — CONCEPT INTERFACE WITH DEMONSTRATION DATA',1)
    # left: occupancy card (implemented capability, simulated value)
    a=ease(i/14); x,y,w,h=96,190,720,700
    card(c,x,y+(1-a)*24,w,h,a); y+=(1-a)*24
    text(c,'OCCUPANCY COUNT',x+36,y+50,17,MUTE,a,True,3); text(c,'Lecture Hall 101',x+36,y+92,34,TXT,a,True)
    pill(c,x+w-36-160,y+28,'SIMULATED',16,AMBER,a)
    n=round(10*ease((i-14)/22)); text(c,str(n),x+36,y+300,190,TXT,a,True)
    text(c,'people counted',x+36+ (330 if n>=10 else 190),y+300,30,MUTE,a)
    text(c,'matches the 10 people in the rendered classroom (9 students + lecturer)',x+36,y+350,19,MUTE,a)
    text(c,'demo capacity 30  ·  anonymous count  ·  no identities',x+36,y+384,19,MUTE,a)
    # bar
    rr(c,x+36,y+420,w-72,16,8); c.set_source_rgba(0.85,0.87,0.94,a); c.fill()
    rr(c,x+36,y+420,(w-72)*n/30,16,8); c.set_source_rgba(*INK,a); c.fill()
    text(c,'WHAT THE BACKEND DOES TODAY',x+36,y+500,16,MUTE,a,True,3)
    for k,t in enumerate(('POST /api/occupancy/ingest  —  count + confidence from a node','Doctors see occupancy only for their own class in progress','Admin Campus Intelligence shows per-room counts, or UNAVAILABLE')):
        text(c,'•  '+t,x+36,y+540+k*34,19,TXT,a)
    pill(c,x+36,y+h-66,'FEEDS  →  CAMPUS DASHBOARD',17,INK,ease((i-84)/10)*a,fill=True)
    # right: concept attendance
    a2=ease((i-10)/14); x,y,w,h=856,190,968,700; y+=(1-a2)*24
    card(c,x,y,w,h,a2)
    text(c,'ATTENDANCE',x+36,y+50,17,MUTE,a2,True,3); text(c,'Demo course  ·  Lecture Hall 101',x+36,y+92,34,TXT,a2,True)
    pill(c,x+w-36-330,y+28,'CONCEPT · NOT IMPLEMENTED',16,AMBER,a2,fill=False)
    pres=sum(1 for k in range(1,13) if k not in ABSENT)
    done=min(12,max(0,int((i-30)/4)))
    pc=sum(1 for k in range(1,done+1) if k not in ABSENT); ac=done-pc
    pill(c,x+36,y+124,f'PRESENT  {pc}',20,GREEN,a2); pill(c,x+36+190,y+124,f'ABSENT  {ac}',20,RED,a2); pill(c,x+36+370,y+124,'ENROLLED (DEMO)  12',20,INK,a2,fill=False)
    for k in range(1,13):
        col=(k-1)//6; r=(k-1)%6; rx=x+36+col*448; ry=y+210+r*70
        rr(c,rx,ry,420,56,10); c.set_source_rgba(0.95,0.96,0.99,a2); c.fill()
        text(c,f'Student {k:02d}',rx+20,ry+36,24,TXT,a2,True); text(c,'demo placeholder',rx+170,ry+35,17,MUTE,a2)
        if k<=done:
            ok=k not in ABSENT; pill(c,rx+420-20,ry+10,'PRESENT' if ok else 'ABSENT',16,GREEN if ok else RED,a2*ease((i-45-5*(k-1))/6),anchor='l') if False else None
            lab='PRESENT' if ok else 'ABSENT'; ww=tw(c,lab,16,True,1.6)+28; pill(c,rx+420-ww-12,ry+10,lab,16,GREEN if ok else RED,a2)
        else:
            lab='PENDING'; ww=tw(c,lab,16,True,1.6)+28; pill(c,rx+420-ww-12,ry+10,lab,16,GREY,0.7*a2,fill=False)
    text(c,'Concept layout: per-student attendance would be linked to the course schedule. Not part of the current backend.',x+36,y+h-28,17,MUTE,a2)
    chip(c,'SIMULATED / DEMONSTRATION DATA  ·  NO REAL STUDENT RECORDS, IDENTITIES OR BIOMETRIC DATA  ·  NOT A LIVE CAMERA FEED',ease(i/14),90,942)
    fo=ease((i-155)/10)
    if fo>0: c.set_source_rgba(*NAVY,0); 
    return s
if '--test' in sys.argv:
    for i in (10,60,100,164): frame(i).write_to_png(FR+f'/test_{i}.png')
    sys.exit()
for i in range(N): frame(i).write_to_png(FR+f'/rs_{i+1:04d}.png')
print('done')
