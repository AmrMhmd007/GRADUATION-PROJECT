"""Record every software take (real app, isolated simulation backend :8001, dashboard :5174). Raw outputs -> recordings/software/raw/<take>.mp4 (+ frames, timestamps, marks)."""
import sys, os, traceback
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from takelib import *
only=sys.argv[1:]
def run(name,fn):
    if only and name not in only: return
    with sync_playwright() as p:
        t=Take(p,name)
        try: fn(t)
        except Exception as e: print('TAKE FAILED',name,repr(e)[:300]); traceback.print_exc()
        print(name,t.finish(),{k:round(v-t.first_kept_ts if hasattr(t,'first_kept_ts') else v,2) for k,v in t.marks.items()} if False else '')
def auth(t):
    t.goto('#tab=access'); t.wait(1.4); t.mark('landing'); t.wait(1.4)
    t.pg.get_by_text('Building A').first.click(); t.mark('bldgA'); t.wait(1.0)
    t.pg.get_by_role('button',name='View Room').first.click(); t.mark('room_open'); t.wait(1.2)
    t.pg.mouse.move(960,540); t.scroll(380,2.2); t.mark('scrolled'); t.wait(0.5)
    t.pg.locator('select').filter(has_text='Select a Doctor').first.select_option(label='Demo Doctor (Doctor)'); t.mark('selected'); t.wait(0.7)
    t.pg.get_by_role('button',name='Check Authorization').first.click(); t.mark('checked'); t.wait(3.0)
def face(t):
    t.goto('#tab=physical'); t.wait(1.4); t.pg.get_by_text('Face ID',exact=True).first.click(); t.mark('face'); t.wait(3.2)
def events_inv(t):
    t.goto('#tab=events'); t.wait(1.4); t.mark('events'); t.pg.get_by_text('Investigate').first.click(); t.mark('inv'); t.wait(1.2)
    t.pg.mouse.move(960,540); t.scroll(300,1.6); t.mark('authdec'); t.wait(1.8)
def events_scroll(t):
    t.goto('#tab=events'); t.wait(1.0); t.mark('start'); t.scroll(700,4.4); t.wait(0.6)
def cmd(t):
    t.goto('#tab=command'); t.wait(1.0); t.mark('start'); t.scroll(650,4.2); t.wait(0.6)
def home(t):
    t.goto('#tab=home'); t.wait(1.2); t.mark('start'); t.scroll(520,4.2); t.wait(0.6)
def cmap(t):
    t.goto('#tab=physical'); t.wait(1.2); t.mark('start')
    for nm in ('Room A101','Room A102','Smart Lab 301','Lecture Hall 101'):
        bb=t.pg.get_by_text(nm,exact=False).first.bounding_box(); t.pg.mouse.move(bb['x']+bb['width']/2,bb['y']+bb['height']/2,steps=14); t.wait(0.7)
    t.wait(0.6)
def occ(t):
    t.goto('#tab=physical'); t.wait(1.0); t.pg.get_by_text('Occupancy',exact=True).first.click(); t.mark('occ'); t.wait(1.2); t.scroll(420,3.0); t.wait(0.6)
def auto(t):
    t.goto('#tab=smart'); t.wait(1.2); t.mark('start'); t.scroll(520,2.0); t.wait(0.6)
    t.pg.get_by_text('Room A101',exact=False).locator('visible=true').last.click(); t.mark('zone'); t.wait(1.3)
    t.pg.mouse.move(960,540); t.scroll(300,1.8); t.wait(1.2)
def zones(t):
    t.goto('#tab=smart'); t.wait(1.0); t.pg.evaluate('window.scrollTo(0,document.body.scrollHeight)'); t.wait(0.5); t.mark('start'); t.wait(1.4); t.scroll(-200,3.2); t.wait(1.2)
for n,f in (('take_auth',auth),('take_face',face),('take_events_inv',events_inv),('take_events_scroll',events_scroll),('take_cmd',cmd),('take_home',home),('take_map',cmap),('take_occ',occ),('take_auto',auto),('take_zones',zones)): run(n,f)
