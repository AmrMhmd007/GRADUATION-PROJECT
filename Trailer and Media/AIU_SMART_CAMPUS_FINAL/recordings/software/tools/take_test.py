from takelib import *
with sync_playwright() as p:
    t=Take(p,'test_home'); t.goto('#tab=home'); t.wait(1.5); t.mark('top'); t.scroll(500,2.5); t.wait(1.0); print(t.finish(),t.marks,len(t.frames))
