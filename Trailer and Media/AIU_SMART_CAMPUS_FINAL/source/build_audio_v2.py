import subprocess, sys, os

BUILD = "/tmp/build"

def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        print("CMD FAILED:", " ".join(cmd))
        print(r.stdout.decode(errors="replace")[-4000:])
        sys.exit(1)

VO = f"{BUILD}/vo_master.wav"
TOTAL = 142.915875

# 1. Normalize / clean the real VO (gentle loudness normalize, no character-changing effects)
vo_clean = f"{BUILD}/vo_clean.wav"
run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i", VO,
     "-af", "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.97",
     "-ar","48000","-ac","2", vo_clean])
print("VO cleaned:", vo_clean)

def vol_expr(segments):
    parts = f"{segments[-1][1]}"
    for i in range(len(segments)-2, -1, -1):
        t0, v0 = segments[i]
        t1, v1 = segments[i+1]
        span = max(t1 - t0, 0.001)
        ramp = f"({v0}+({v1}-{v0})*((t-{t0})/{span}))"
        parts = f"if(lt(t,{t1}),{ramp},{parts})"
    t0, v0 = segments[0]
    parts = f"if(lt(t,{t0}),{v0},{parts})"
    return parts

# Music dynamic arc (pre-ducking level; sidechain will duck further under VO)
pad_env   = vol_expr([(0,0.0),(9.2,0.0),(11.0,0.22),(107.3,0.22),(122.6,0.34),(132.9,0.0)])
pulse_env = vol_expr([(0,0.0),(41.8,0.0),(43.0,0.13),(107.3,0.13),(122.6,0.22),(132.9,0.0)])
tension_env = vol_expr([(0,0.0),(77.4,0.0),(107.3,0.15),(132.9,0.0)])
noise_env = vol_expr([(0,0.05),(9.2,0.05),(11.0,0.02),(132.9,0.02),(136.3,0.0)])

music_pre = f"{BUILD}/music_pre.wav"
filter_complex = (
    f"[0:a]volume='{noise_env}':eval=frame,lowpass=f=500[noiseA];"
    f"[1:a]volume='{pad_env}':eval=frame[p1];"
    f"[2:a]volume='{pad_env}':eval=frame[p2];"
    f"[3:a]volume='{pad_env}':eval=frame[p3];"
    f"[4:a]volume='{pulse_env}':eval=frame[pu];"
    f"[5:a]volume='{tension_env}':eval=frame,lowpass=f=300[te];"
    f"[noiseA][p1][p2][p3][pu][te]amix=inputs=6:duration=longest:normalize=0[mix]"
)
run(["ffmpeg","-y","-hide_banner","-loglevel","error",
     "-f","lavfi","-i", f"anoisesrc=colour=pink:amplitude=1:duration={TOTAL}:sample_rate=48000",
     "-f","lavfi","-i", f"sine=frequency=98:duration={TOTAL}:sample_rate=48000",
     "-f","lavfi","-i", f"sine=frequency=123.47:duration={TOTAL}:sample_rate=48000",
     "-f","lavfi","-i", f"sine=frequency=146.83:duration={TOTAL}:sample_rate=48000",
     "-f","lavfi","-i", f"sine=frequency=55:duration={TOTAL}:sample_rate=48000",
     "-f","lavfi","-i", f"sine=frequency=110:duration={TOTAL}:sample_rate=48000",
     "-filter_complex", filter_complex, "-map","[mix]", "-t", str(TOTAL), "-ac","2", music_pre])
print("Music pre-duck bed:", music_pre)

# 2. Final chord hit at the very end (product reveal, t=136.3 -> "This is AIU Smart Campus" reveal beat)
hit_out = f"{BUILD}/hit2.wav"
freqs = [261.6,329.6,392.0,523.2]
fc = ";".join(f"[{idx}:a]volume='0.20*exp(-2.0*t)':eval=frame[h{idx}]" for idx in range(len(freqs)))
mixh = "".join(f"[h{idx}]" for idx in range(len(freqs))) + f"amix=inputs={len(freqs)}:duration=longest:normalize=0[hit]"
run(["ffmpeg","-y","-hide_banner","-loglevel","error",
     "-f","lavfi","-i","sine=frequency=261.6:duration=3.3:sample_rate=48000",
     "-f","lavfi","-i","sine=frequency=329.6:duration=3.3:sample_rate=48000",
     "-f","lavfi","-i","sine=frequency=392.0:duration=3.3:sample_rate=48000",
     "-f","lavfi","-i","sine=frequency=523.2:duration=3.3:sample_rate=48000",
     "-filter_complex", fc + ";" + mixh, "-map","[hit]","-ac","2", hit_out])
hit_delayed = f"{BUILD}/hit2_delayed.wav"
delay_ms = int(133.0*1000)
run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i", hit_out,
     "-af", f"adelay={delay_ms}|{delay_ms}", "-t", str(TOTAL), hit_delayed])

# 3. Soft transition whoosh generator (short filtered noise burst) at key cut points
whoosh_points = [9.2, 38.8, 49.3, 77.4, 91.6, 107.3, 122.6]
whoosh_files = []
for i, t in enumerate(whoosh_points):
    wf = f"{BUILD}/whoosh_{i}.wav"
    run(["ffmpeg","-y","-hide_banner","-loglevel","error",
         "-f","lavfi","-i","anoisesrc=colour=white:amplitude=1:duration=0.6:sample_rate=48000",
         "-af","volume='0.10*sin(PI*t/0.6)':eval=frame,highpass=f=800,lowpass=f=4000",
         "-ac","2", wf])
    delay_ms2 = int(t*1000)
    wfd = f"{BUILD}/whoosh_{i}_d.wav"
    run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i", wf,
         "-af", f"adelay={delay_ms2}|{delay_ms2}", "-t", str(TOTAL), wfd])
    whoosh_files.append(wfd)

# 4. Mix music+hit+whooshes into one "FX bed", then sidechain-duck the FX bed under the VO
fxbed_inputs = ["-i", music_pre, "-i", hit_delayed] + sum([["-i", w] for w in whoosh_files], [])
n_fx = 2 + len(whoosh_files)
fx_labels = "".join(f"[{i}:a]" for i in range(n_fx))
fxbed = f"{BUILD}/fxbed.wav"
run(["ffmpeg","-y","-hide_banner","-loglevel","error"] + fxbed_inputs +
    ["-filter_complex", f"{fx_labels}amix=inputs={n_fx}:duration=longest:normalize=0[fx]",
     "-map","[fx]","-t", str(TOTAL), "-ac","2", fxbed])
print("FX bed:", fxbed)

# 5. Sidechain compress the FX bed keyed by the VO (true professional ducking)
ducked = f"{BUILD}/fxbed_ducked.wav"
run(["ffmpeg","-y","-hide_banner","-loglevel","error",
     "-i", fxbed, "-i", vo_clean,
     "-filter_complex",
     "[0:a][1:a]sidechaincompress=threshold=0.03:ratio=8:attack=25:release=400:makeup=1[ducked]",
     "-map","[ducked]", "-t", str(TOTAL), ducked])
print("Ducked FX bed:", ducked)

# 6. Final mix: ducked FX bed + VO (voice dominant, clear)
final_audio = f"{BUILD}/final_audio_v2.wav"
run(["ffmpeg","-y","-hide_banner","-loglevel","error",
     "-i", ducked, "-i", vo_clean,
     "-filter_complex",
     "[0:a]volume=0.9[fxv];[1:a]volume=1.15[vov];[fxv][vov]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[out]",
     "-map","[out]", "-t", str(TOTAL), "-ar","48000","-ac","2", final_audio])
print("FINAL AUDIO V2 DONE:", final_audio)
