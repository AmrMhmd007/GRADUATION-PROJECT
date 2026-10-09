import sys, os, json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
from playwright.sync_api import sync_playwright
OUT=S+'/logs/explore4'; os.makedirs(OUT,exist_ok=True); log=[]
with sync_playwright() as p:
    b,ctx=new_context(p); pg=ctx.new_page()
    pg.goto(APP+'/#tab=physical'); pg.wait_for_timeout(2500)
    pg.get_by_text('Lecture Hall 101').first.click(); pg.wait_for_timeout(3000); pg.screenshot(path=OUT+'/map_room.png',full_page=True)
    log.append(pg.url)
    b.close()
json.dump(log,open(OUT+'/log.json','w')); print(log)
