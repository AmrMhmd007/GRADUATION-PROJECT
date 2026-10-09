"""System-architecture animation (conceptual diagram of the REAL code structure). 9.2 s = 276 frames @30 fps.
Facts used: FastAPI backend (app/routers: auth, doors, schedules, occupancy, face, zones/automation, audit...), SQLAlchemy models on SQLite (PostgreSQL via DATABASE_URL),
React/Vite dashboard calling the REST API, MQTT listener + automation engine, door-node firmware (Phase 2 prototype), occupancy ingest endpoint."""
import cairo, math, sys, os
sys.path.insert(0,'/sessions/great-sleepy-rubin/mnt/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/blender/attendance_scene/overlay')
from uilib import *
OUT=os.path.dirname(os.path.abspath(__file__))+'/work/arch'; N=276
def card(c,x,y,w,h,title,sub,badge,col,a,dashed=False,lines=()):
    rr(c,x,y,w,h,16); c.set_source_rgba(0.07,0.10,0.20,0.92*a); c.fill_preserve()
    if dashed: c.set_dash([9,7])
    c.set_source_rgba(*col,0.9*a); c.set_line_width(2.2); c.stroke(); c.set_dash([])
    text(c,title,x+26,y+46,28,WHITE,a,True,3); text(c,sub,x+26,y+76,18,GREY,a,False,1.4)
    yy=y+112
    for ln in lines: text(c,ln,x+26,yy,17,(0.78,0.82,0.9),a,False,1); yy+=26
    if badge: pill(c,x+26,y+h-50,badge,14,col,a,fill=not dashed)
def link(c,p0,p1,prog,a,label=None,dashed=False,col=BLUE):
    if prog<=0: return
    x0,y0=p0; x1,y1=p1; x=x0+(x1-x0)*prog; y=y0+(y1-y0)*prog
    if dashed: c.set_dash([8,7])
    c.set_source_rgba(*col,0.85*a); c.set_line_width(3); c.move_to(x0,y0); c.line_to(x,y); c.stroke(); c.set_dash([])
    if prog>=1:
        ang=math.atan2(y1-y0,x1-x0); c.move_to(x1,y1); c.line_to(x1-16*math.cos(ang-0.4),y1-16*math.sin(ang-0.4)); c.line_to(x1-16*math.cos(ang+0.4),y1-16*math.sin(ang+0.4)); c.close_path(); c.set_source_rgba(*col,a); c.fill()
        if label: text(c,label,(x0+x1)/2,(y0+y1)/2-14,16,GREY,a,False,1.4,'c')
def frame(i):
    s=cairo.ImageSurface(cairo.FORMAT_RGB24,W,H); c=cairo.Context(s)
    g=cairo.LinearGradient(0,0,0,H); g.add_color_stop_rgb(0,0.03,0.05,0.11); g.add_color_stop_rgb(1,0.015,0.025,0.06); c.set_source(g); c.paint()
    c.set_source_rgba(1,1,1,0.035); c.set_line_width(1)
    for x in range(0,W,80): c.move_to(x,0); c.line_to(x,H)
    for y in range(0,H,80): c.move_to(0,y); c.line_to(W,y)
    c.stroke()
    chapter(c,'SYSTEM ARCHITECTURE','BACKEND · DATABASE · DASHBOARD · AUTOMATION — DERIVED FROM THE PROJECT SOURCE CODE',ease(i/10))
    A=lambda t0: ease((i-t0)/10)
    BE=(700,300,500,400); DB=(1420,300,380,170); DS=(1420,520,380,170); HW1=(120,300,400,170); HW2=(120,520,400,170)
    # links first (under cards)
    link(c,(520,385),(700,385),ease((i-150)/16),1,'MQTT / API',True,AMBER)
    link(c,(520,605),(700,605),ease((i-166)/16),1,'occupancy ingest',True,AMBER)
    link(c,(1200,385),(1420,385),ease((i-52)/16),1,'SQLAlchemy')
    link(c,(1200,605),(1420,605),ease((i-86)/16),1,'REST API (JSON)')
    # backend
    a=A(9)
    if a>0:
        card(c,*BE,'BACKEND','FastAPI · Python',None,BLUE,a,False,('auth · doors · schedules · access events','occupancy · face credential check · rooms','audit log · alerts · device faults')); pill(c,BE[0]+BE[2]-26-232,BE[1]+22,'SOFTWARE IMPLEMENTED',13,BLUE,a)
    a=A(45)
    if a>0: card(c,*DB,'DATABASE','SQLite · PostgreSQL-ready','SOFTWARE IMPLEMENTED',BLUE,a)
    a=A(78)
    if a>0: card(c,*DS,'DASHBOARD','React web interface','SOFTWARE IMPLEMENTED',BLUE,a)
    a=A(117)
    if a>0:
        x,y=BE[0]+26,BE[1]+BE[3]-150; rr(c,x,y,BE[2]-52,120,12); c.set_source_rgba(0.12,0.2,0.4,0.9*a); c.fill_preserve(); c.set_source_rgba(*BLUE,a); c.set_line_width(1.8); c.stroke()
        text(c,'AUTOMATION',x+20,y+38,22,WHITE,a,True,3); text(c,'rules · occupancy verification window · automation log',x+20,y+66,16,GREY,a,False,1)
        pill(c,x+20,y+78,'SOFTWARE IMPLEMENTED · HARDWARE NOT LIVE',13,AMBER,a,fill=False)
    a=A(146)
    if a>0:
        card(c,*HW1,'DOOR NODE','Phase 2 prototype firmware (card reader)','PROTOTYPE · NOT LIVE',AMBER,a,True)
        card(c,*HW2,'OCCUPANCY NODE','sends a count to the ingest endpoint','INTERFACE ONLY · NOT LIVE',AMBER,A(162),True)
    a=A(204)
    if a>0:
        w=tw(c,'ONE CONNECTED SYSTEM',30,True,6)+60; rr(c,W/2-w/2,800,w,70,35); c.set_source_rgba(*BLUE,0.18*a); c.fill_preserve(); c.set_source_rgba(*BLUE,a); c.set_line_width(2); c.stroke()
        text(c,'ONE CONNECTED SYSTEM',W/2,846,30,WHITE,a,True,6,'c')
    text(c,'FILLED = SOFTWARE IMPLEMENTED IN THIS PROJECT   ·   DASHED = HARDWARE SIDE (PROTOTYPE / INTERFACE, NOT A LIVE DEPLOYMENT)   ·   DIAGRAM IS A SIMPLIFIED CONCEPT VIEW',W/2,1000,16,GREY,0.85*ease(i/12),False,1.4,'c')
    return s
if '--test' in sys.argv:
    for i in (60,130,200,275): frame(i).write_to_png(f'{OUT}/test_{i}.png')
    sys.exit()
for i in range(N): frame(i).write_to_png(f'{OUT}/a_{i+1:04d}.png')
print('done')
