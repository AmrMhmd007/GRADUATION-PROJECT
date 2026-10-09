import sys, os, json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
from playwright.sync_api import sync_playwright
OUT=S+'/logs/explore2'; os.makedirs(OUT,exist_ok=True); log=[]
with sync_playwright() as p:
    b,ctx=new_context(p); pg=ctx.new_page()
    pg.goto(APP+'/#tab=events'); pg.wait_for_timeout(2500)
    try:
        pg.get_by_text('Investigate').first.click(timeout=4000); pg.wait_for_timeout(2500); pg.screenshot(path=OUT+'/investigate.png',full_page=True)
    except Exception as e: log.append(('investigate',str(e)[:120]))
    pg.goto(APP+'/#tab=smart'); pg.wait_for_timeout(2500); pg.screenshot(path=OUT+'/smart_full.png',full_page=True)
    try:
        pg.get_by_text('ROOM A101',exact=False).first.click(timeout=4000); pg.wait_for_timeout(2500); pg.screenshot(path=OUT+'/smart_zone.png')
    except Exception as e: log.append(('zone',str(e)[:120]))
    pg.goto(APP+'/#tab=home'); pg.wait_for_timeout(2500); pg.screenshot(path=OUT+'/home_full.png',full_page=True)
    pg.goto(APP+'/#tab=access'); pg.wait_for_timeout(2000)
    try:
        pg.get_by_text('Building A').first.click(timeout=3000); pg.wait_for_timeout(2000); pg.screenshot(path=OUT+'/access_bldgA.png',full_page=True)
    except Exception as e: log.append(('bldgA',str(e)[:120]))
    b.close()
json.dump(log,open(OUT+'/log.json','w')); print('ok',log)
