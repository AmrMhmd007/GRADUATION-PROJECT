"""Final audio mix: supplied ElevenLabs narration + ORIGINAL procedural music + SFX. Music/SFX are ducked under speech by the VO envelope.
Run:  python3 make_mix_vo.py   ->  AIU_SMART_CAMPUS_FINAL_MIX.wav (+ stems, sfx_events.json)"""
import numpy as np, wave, json, os, subprocess, sys
from scipy import signal
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
from audio_lib import *
from timeline_vo import *
N=int(TOTAL*SR)
def rd(p):
    w=wave.open(p); x=np.frombuffer(w.readframes(w.getnframes()),'<i2').astype(float)/32768; w.close(); return x
# ---- narration: processed copy (HPF, gentle compression, loudness-normalised) ----
raw=HERE+'/AIU_SMART_CAMPUS_VOICEOVER.wav'; proc=HERE+'/work/vo_processed.wav'
subprocess.run(['ffmpeg','-y','-loglevel','error','-i',raw,'-af','highpass=f=80,acompressor=threshold=0.1:ratio=2.5:attack=8:release=140:makeup=1.5,loudnorm=I=-16:TP=-2.5:LRA=7','-ar','48000','-ac','1',proc],check=True)
vo=rd(proc); vobuf=np.zeros((N,2)); i0=int(VO_OFF*SR); vobuf[i0:i0+len(vo),0]=vo[:N-i0]; vobuf[i0:i0+len(vo),1]=vo[:N-i0]
# speech envelope (attack 40 ms, release 450 ms) for ducking
e=np.abs(vobuf[:,0]); e=signal.sosfilt(signal.butter(1,6/(SR/2),'low',output='sos'),e); e=e/ (np.percentile(e[e>0.001],90)+1e-9); sp=np.clip(e*1.6,0,1)
rel=np.copy(sp)
for k in range(1,len(rel)): rel[k]=max(sp[k],rel[k-1]-1/(0.45*SR))      # fast attack, 450 ms release
speech=np.clip(rel,0,1)
# ---- music ----
def music():
    buf=np.zeros((N,2)); prog=CH; at=0.0; ci=0
    while at<TOTAL-0.5:
        name,notes=prog[ci%4]; d=2*BAR+1.0
        lvl=np.interp(at,[0,15,43,61,82,99,105.7],[0.45,0.55,0.65,0.75,0.85,0.95,1.0])
        place(buf,pad(notes,d,0.55*lvl),at,1.0,-0.05); place(buf,pad([n+12 for n in notes[1:]],d,0.25*lvl),at,1.0,0.15)
        b=sine(mtof(notes[0]-12),d)*np.minimum(1,np.arange(int(d*SR))/SR/0.6)*np.minimum(1,(d-np.arange(int(d*SR))/SR)/0.8); place(buf,b,at,0.30*lvl)
        at+=2*BAR; ci+=1
    # plucked arpeggio from 6 s, becoming denser after the classroom
    step=BEAT/2; k=0; at=6.0
    while at<105.5:
        name,notes=CH[int((at//(2*BAR)))%4]; m=notes[[0,1,2,3,2,1,3,2][k%8]]+24
        g=np.interp(at,[6,43,61,82,99],[0.07,0.12,0.17,0.22,0.27]); place(buf,pluck(m),at,g,np.sin(k*0.7)*0.4); at+=step; k+=1
    at=43.0                                                       # soft pulse
    while at<105.0:
        place(buf,sine(52,0.28)*env(int(0.28*SR),0.002,0.07)*np.interp(at,[43,82,99],[0.10,0.18,0.25]),at,1.0); at+=BEAT*2
    place(buf,whoosh(3.2,200,5000),0.4,0.35)                      # opening riser into the title
    # closing resolution: D major
    place(buf,pad([50,57,62,66,69,74],9.5,0.95),105.7,0.9); place(buf,boom(3.5),105.85,0.5)
    for j,m in enumerate([74,78,81,86]): place(buf,pluck(m,1.8)*1.1,108.4+j*0.2,0.22,(j-1.5)*0.2)
    ir=np.exp(-np.arange(int(2.4*SR))/SR/0.7); irl=rng.standard_normal(len(ir))*ir; irr=rng.standard_normal(len(ir))*ir
    wet=np.stack([signal.fftconvolve(buf[:,0],irl)[:N],signal.fftconvolve(buf[:,1],irr)[:N]],1)*0.012
    return buf*0.8+wet
M=music()
# ---- SFX ----
EV=[]; S=np.zeros((N,2))
def P(x,at,g=1.0,pan=0.0,lab='',key=False): place(S,x,at,g,pan); EV.append((round(at,3),lab,key))
P(boom(3.0),3.85,0.55,0,'title impact',True)
for f in (172,186,198,208,216): P(tick(1900),door_T(f),0.22,0.1,'verification step')
P(chime(659,0.5),door_T(225),0.30,0,'access granted (1)',True); P(chime(988,1.0),door_T(225)+0.14,0.30,0,'access granted (2)',True)
P(lock_release(),door_T(229)+0.05,0.55,0.1,'lock release',True)
P(handle(),door_T(246),0.5,0.15,'handle',True)
P(door_open(),door_T(256),0.55,0.2,'door opening',True)
P(blip(740,0.15),T(0)+52.0-0.0 if False else 46.2+40/30,0.22,0,'camera callout')
P(sweep(1.6),49.0,0.35,0,'coverage volume grows')
for k,t in enumerate((52.4+0.07,53.4+0.07,54.6+0.07)): P(tick(1500+k*200),t,0.25,0,'pipeline step')
P(chime(880,0.9),54.67,0.28,0,'count-ingest step (implemented)'); P(hollow(440,0.6),55.97,0.26,0,'attendance record (concept)')
for k in range(12): P(tick(2200+(k%3)*120,0.04),57.2+(30+4*k+4)/30,0.10,((k%2)-0.5)*0.4,'roster row')
for t,l in ((86.7,'backend'),(87.9,'database'),(89.0,'dashboard'),(90.3,'automation'),(91.4,'door node'),(91.5+0.5,'occupancy node')): P(tick(1700),t,0.2,0,'architecture node: '+l)
P(chime(784,0.8),93.1,0.25,0,'one connected system')
for t in (95.7,96.4,97.1,97.8): P(tick(1400),t,0.16,0,'montage cell')
P(whoosh(0.8,300,4000),61.3,0.25,0,'transition to dashboard'); P(whoosh(0.8,300,4000),81.95,0.22,0,'transition to architecture')
P(whoosh(1.0,300,4000),105.0,0.28,0,'rise into closing'); P(chime(1046,1.4),105.95,0.28,0,'closing title',True)
# software-recording interaction ticks (timestamps measured from the recordings' action logs)
rj=HERE+'/work/recording_cues.json'
if os.path.exists(rj):
    for t,l in json.load(open(rj)): P(tick(2400,0.035),t,0.09,0,'UI interaction: '+l)
S=S*1.0
# ---- ducking: music -9 dB under speech, SFX -4 dB under speech except key cues ----
duck_m=1-0.66*speech; duck_s=1-0.35*speech
mix=M*duck_m[:,None]*0.55+S*duck_s[:,None]*0.9
# key cues restore full level around themselves
for t,l,key in EV:
    if key:
        i=int(t*SR); j=min(N,i+int(1.2*SR)); mix[i:j]+=S[i:j]*(0.35*speech[i:j])[:,None]*0.9
mix+=vobuf*1.0
fo=int(1.6*SR); mix[-fo:]*=(np.linspace(1,0,fo)**1.5)[:,None]; fi=int(0.15*SR); mix[:fi]*=np.linspace(0,1,fi)[:,None]
mix=np.tanh(mix*1.05)/np.tanh(1.05)
peak=np.abs(mix).max(); mix*=10**(-2.0/20)/peak
def lufs(x):
    p=HERE+'/work/_m.wav'; wav_(p,x); o=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',p,'-af','ebur128=peak=true','-f','null','-'],capture_output=True,text=True).stderr
    import re; return float(re.findall(r'I:\s+(-?[\d.]+) LUFS',o)[-1]), float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS',o)[-1])
def wav_(p,x):
    w=wave.open(p,'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(x,-1,1)*32767).astype('<i2').tobytes()); w.close()
L,TP=lufs(mix); g=10**((-16.0-L)/20); mix*=g; L2,TP2=lufs(mix); print('LUFS %.1f -> %.1f ; true peak %.1f'%(L,L2,TP2)); GAIN=g
def wav(p,x):
    w=wave.open(p,'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(x,-1,1)*32767).astype('<i2').tobytes()); w.close()
wav(HERE+'/AIU_SMART_CAMPUS_FINAL_MIX.wav',mix)
wav(HERE+'/work/stem_music.wav',M*duck_m[:,None]*0.55*10**(-2.0/20)/peak*GAIN); wav(HERE+'/work/stem_sfx.wav',S*duck_s[:,None]*0.9*10**(-2.0/20)/peak*GAIN)
json.dump({'vo_offset':VO_OFF,'events':EV,'total':TOTAL},open(HERE+'/work/sfx_events.json','w'),indent=1)
m=speech>0.6; vr=np.sqrt((vobuf[m,0]**2).mean()); br=np.sqrt(((M*duck_m[:,None]*0.55+S*duck_s[:,None]*0.9)[m]*10**(-2.0/20)/peak*GAIN)[:,0]**2).mean() if False else None
bed=(M*duck_m[:,None]*0.55+S*duck_s[:,None]*0.9)*10**(-2.0/20)/peak*GAIN; vv=vobuf*10**(-2.0/20)/peak*GAIN
print('speech-to-bed ratio during speech: %.1f dB'%(20*np.log10(np.sqrt((vv[m,0]**2).mean())/np.sqrt((bed[m,0]**2).mean()))))
print('mix ok; sample peak dBFS',20*np.log10(np.abs(mix).max()))
