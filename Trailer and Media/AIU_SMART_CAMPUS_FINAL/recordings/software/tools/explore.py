import sys, os, json, time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import *
from playwright.sync_api import sync_playwright
OUT=S+'/logs/explore'; os.makedirs(OUT,exist_ok=True); log=[]
with sync_playwright() as p:
    b,ctx=new_context(p); pg=ctx.new_page()
    pg.on('console',lambda m: log.append(('console',m.type,m.text[:200])) if m.type in('error','warning') else None)
    pg.on('requestfailed',lambda r: log.append(('reqfail',r.url,str(r.failure))))
    pg.on('response',lambda r: log.append(('http',r.status,r.url)) if r.status>=400 else None)
    pg.goto(APP+'/#tab=home'); pg.wait_for_timeout(2500)
    for tab in ('home','command','critical','access','events','smart','physical','academic'):
        pg.goto(APP+f'/#tab={tab}'); pg.wait_for_timeout(2200); pg.screenshot(path=f'{OUT}/tab_{tab}.png')
        log.append(('tab',tab,pg.title()))
    # physical sub tabs
    pg.goto(APP+'/#tab=physical'); pg.wait_for_timeout(1500)
    for name in ('Campus Map','Occupancy','Device Faults','Face ID'):
        try: pg.get_by_role('tab',name=name).first.click(timeout=3000)
        except Exception:
            try: pg.get_by_text(name,exact=True).first.click(timeout=3000)
            except Exception as e: log.append(('click-fail',name,str(e)[:100])); continue
        pg.wait_for_timeout(2000); pg.screenshot(path=f'{OUT}/phys_{name.replace(" ","_")}.png')
    log.append(('buttons-physical',[t for t in pg.locator('button,[role=tab]').all_inner_texts()][:40]))
    b.close()
json.dump(log,open(OUT+'/explore_log.json','w'),indent=1,default=str); print('done')
