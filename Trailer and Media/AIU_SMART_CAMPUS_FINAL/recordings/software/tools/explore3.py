import sys, os, json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
from playwright.sync_api import sync_playwright
OUT=S+'/logs/explore3'; os.makedirs(OUT,exist_ok=True); log=[]
with sync_playwright() as p:
    b,ctx=new_context(p); pg=ctx.new_page()
    pg.goto(APP+'/#tab=access'); pg.wait_for_timeout(2000)
    pg.get_by_text('Building A').first.click(); pg.wait_for_timeout(1500)
    pg.get_by_role('button',name='View Room').first.click(); pg.wait_for_timeout(3000); pg.screenshot(path=OUT+'/room_view.png',full_page=True)
    log.append(('url',pg.url))
    pg.goto(APP+'/#tab=academic'); pg.wait_for_timeout(2000)
    try:
        pg.get_by_text('Doctors / Instructors').first.click(); pg.wait_for_timeout(2500); pg.screenshot(path=OUT+'/doctors.png')
    except Exception as e: log.append(('doc',str(e)[:100]))
    b.close()
json.dump(log,open(OUT+'/log.json','w')); print(log)
