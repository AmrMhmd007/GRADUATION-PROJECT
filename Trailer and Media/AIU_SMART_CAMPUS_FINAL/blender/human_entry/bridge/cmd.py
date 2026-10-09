import subprocess, os
S='/Users/amrmohamed/Desktop/AIU_SMART_CAMPUS_FINAL/recordings/software'
r=subprocess.run(f'cd {S} && ./.venv/bin/python tools/record_all.py',shell=True,capture_output=True,text=True,timeout=590,env={**os.environ,'PATH':'/opt/homebrew/bin:/usr/bin:/bin'})
open(S+'/logs/record_all_run.txt','w').write(r.stdout+r.stderr[-3000:])
