import subprocess, os
OUT='/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/recordings/software/probe.txt'
os.makedirs(os.path.dirname(OUT),exist_ok=True)
def sh(c,t=60):
    try:
        r=subprocess.run(c,shell=True,capture_output=True,text=True,timeout=t,env={**os.environ,'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:'+os.environ.get('PATH','')}); return r.stdout+r.stderr
    except Exception as e: return repr(e)
SRC='/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Source Code'
cmds=['whoami; uname -m; sw_vers -productVersion','which node npm python3 python3.12 python3.11 uv brew ffmpeg','node -v; npm -v; python3 --version',
'ls /Applications | grep -i -E "chrome|chromium|firefox|safari"',
'lsof -iTCP -sTCP:LISTEN -P -n | grep -E ":(8000|8001|5173|5174)\\b" || echo "no listeners on 8000/8001/5173/5174"',
'ps aux | grep -E "uvicorn|vite|seed_simulated" | grep -v grep || echo "no uvicorn/vite/seeder processes"',
f'ls -l "{SRC}/backend/venv/bin/python3" "{SRC}/backend/venv/bin/uvicorn" 2>&1; readlink -f "{SRC}/backend/venv/bin/python3"; "{SRC}/backend/venv/bin/python3" --version 2>&1',
f'ls "{SRC}/dashboard/node_modules/.bin" | grep -E "^vite$" || echo "no vite bin"',
'ls -ld ~/Library/Application\\ Support/Google/Chrome 2>&1 | head -2','df -h ~ | tail -1']
open(OUT,'w').write('\n'.join('$ '+c+'\n'+sh(c) for c in cmds))
