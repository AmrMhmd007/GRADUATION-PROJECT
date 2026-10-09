import json, os, time, urllib.request
S='/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/recordings/software'
API='http://127.0.0.1:8001'; APP='http://localhost:5174'
def token():
    c=json.load(open(S+'/.demo_credentials.json'))
    req=urllib.request.Request(API+'/api/auth/login',data=json.dumps({'email':c['email'],'password':c['password']}).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(req))['access_token']
def new_context(p,record_dir=None):
    b=p.chromium.launch(channel='chrome',headless=True,args=['--force-device-scale-factor=1','--hide-scrollbars'])
    kw=dict(viewport={'width':1920,'height':1080},device_scale_factor=1)
    if record_dir: kw.update(record_video_dir=record_dir,record_video_size={'width':1920,'height':1080})
    ctx=b.new_context(**kw); tok=token()
    ctx.add_init_script("try{localStorage.setItem('access_control_token',%s)}catch(e){}"%json.dumps(tok))
    return b,ctx
