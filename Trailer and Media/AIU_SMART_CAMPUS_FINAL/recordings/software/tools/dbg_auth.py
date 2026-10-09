from takelib import *
with sync_playwright() as p:
    t=Take(p,'dbg'); t.goto('#tab=access'); t.wait(1.2); t.pg.get_by_text('Building A').first.click(); t.wait(0.8)
    t.pg.get_by_role('button',name='View Room').first.click(); t.wait(1.5)
    for el in t.pg.locator('select').all():
        print('SELECT disabled=',el.is_disabled(),'visible=',el.is_visible(),'opts=',el.locator('option').all_inner_texts()[:6])
    t.pg.screenshot(path=S+'/logs/dbg_auth.png'); t.finish()
