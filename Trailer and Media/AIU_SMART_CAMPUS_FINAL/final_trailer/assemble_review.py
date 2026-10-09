"""Assembly PREVIEW: reuses existing renders only (no re-render of scenes). Silent. Output: AIU_TRAILER_REVIEW_FINAL.mp4"""
import subprocess, os
from PIL import Image, ImageDraw, ImageFont
R=os.path.abspath(os.path.join(os.path.dirname(__file__),'..')); O=os.path.dirname(os.path.abspath(__file__)); Wk=O+'/work'
DOOR=R+'/blender/renders/review_v3/AIU_SHOT01_v3_review.mp4'; DOV=R+'/blender/overlay/AIU_verification_overlay_ProRes4444.mov'
OCC=R+'/blender/occupancy_scene/exports/AIU_OCCUPANCY_PREVIEW.mp4'; PROTO=R+'/after_effects/prototype_reveal/AIU_PROTOTYPE_REVEAL_PREVIEW.mp4'
# dashboard placeholder slate (NOT a recording)
C=lambda s,b=False:ImageFont.truetype('/usr/share/fonts/truetype/crosextra/Carlito-%s.ttf'%('Bold' if b else 'Regular'),s)
DASH=R+'/recordings/AIU_OCCUPANCY_DASHBOARD_PROVISIONAL.mp4'
FMT='fps=30,format=yuv420p,setsar=1'
def run(a): subprocess.run(['ffmpeg','-y','-loglevel','error']+a,check=True)
# seg1 door 0-10 s, upscaled 960x540 -> 1080p, verification overlay on top (ProRes alpha)
run(['-i',DOOR,'-i',DOV,'-filter_complex',f'[0:v]trim=0:10,setpts=PTS-STARTPTS,scale=1920:1080:flags=lanczos,format=rgba[a];[1:v]trim=0:10,setpts=PTS-STARTPTS,format=rgba[o];[a][o]overlay,{FMT}[v]','-map','[v]','-c:v','libx264','-crf','16','-an',Wk+'/s1.mp4'])
# seg2 classroom 9-15 s (cams D/E, coverage volume), upscale 720p->1080p
run(['-ss','9','-i',OCC,'-t','6','-vf',f'scale=1920:1080:flags=lanczos,{FMT}','-c:v','libx264','-crf','16','-an',Wk+'/s2.mp4'])
run(['-i',DASH,'-vf',FMT,'-c:v','libx264','-crf','16','-an',Wk+'/s3.mp4'])
# seg4 prototype reveal, hold last frame 2 s (title card already in the shot)
run(['-i',PROTO,'-vf',f'tpad=stop_mode=clone:stop_duration=2,{FMT}','-c:v','libx264','-crf','16','-an',Wk+'/s4.mp4'])
D=0.5; durs=[10,6,8,10]; offs=[]; t=0
for i in range(3): t+=durs[i]-D; offs.append(t)
fc=f'[0][1]xfade=transition=fade:duration={D}:offset={offs[0]}[x1];[x1][2]xfade=transition=fade:duration={D}:offset={offs[1]}[x2];[x2][3]xfade=transition=fade:duration={D}:offset={offs[2]}[v]'
run(sum([['-i',Wk+f'/s{i}.mp4'] for i in range(1,5)],[])+['-filter_complex',fc,'-map','[v]','-c:v','libx264','-pix_fmt','yuv420p','-crf','18','-r','30','-an','-movflags','+faststart',O+'/AIU_TRAILER_REVIEW_FINAL.mp4'])
print('done')
