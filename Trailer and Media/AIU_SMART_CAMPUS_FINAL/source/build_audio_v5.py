"""Procedural music bed + restrained SFX for AIU trailer v5 (numpy). The supplied voice-over is never regenerated or altered
except for loudness normalisation. Output: /tmp/work/v5/music.wav, sfx.wav then final mix via ffmpeg."""
import numpy as np, subprocess, wave, sys
SR = 48000; TOTAL = 152.92
N = int(SR * TOTAL)
rng = np.random.default_rng(5)
t = np.arange(N) / SR

def env(a, b, c=None, d=None, lo=0.0, hi=1.0):
    pts = [(a, lo), (b, hi)] if c is None else [(a, lo), (b, hi), (c, hi), (d, lo)]
    return np.interp(t, [p[0] for p in pts], [p[1] for p in pts])


try:
    import scipy.signal as sg
except Exception:
    sg = None
if sg is None:
    subprocess.run([sys.executable, "-m", "pip", "install", "scipy", "--break-system-packages", "-q"]); import scipy.signal as sg

def onepole(x, fc): a = np.exp(-2 * np.pi * fc / SR); return sg.lfilter([1 - a], [1, -a], x)
def hp(x, fc): return x - onepole(x, fc)
def tone(f, harm=(1, .5, .25, .12), det=0.0):
    ph = 2 * np.pi * f * t
    return sum(a * np.sin((k + 1) * ph * (1 + det * (k % 2 * 2 - 1))) for k, a in enumerate(harm))

# ---------------- music
chords = [(110.0, 164.8, 220.0, 261.6), (87.3, 130.8, 174.6, 261.6), (130.8, 196.0, 261.6, 329.6), (98.0, 146.8, 196.0, 293.7)]  # Am F C G
bar = 6.0
pad = np.zeros(N)
for i in range(int(TOTAL // bar) + 1):
    a, b = i * bar, (i + 1) * bar
    ch = chords[i % 4]
    g = np.clip(np.minimum((t - a) / 1.5, (b + 1.5 - t) / 1.5), 0, 1)
    for f in ch: pad += g * (tone(f, (1, .35, .12), 0.0015) * 0.07)
pad = onepole(pad, 1400) * env(0, 6, 140, 146.1, 0.0, 1.0)
pad *= np.interp(t, [0, 21, 60, 107, 125, 146.1, 152.92], [0.6, 0.8, 0.9, 1.0, 1.15, 0.0, 0.0])
# pulse (plucks) 100 bpm from 40 s
beat = 60 / 100
pulse = np.zeros(N)
notes = [220.0, 261.6, 329.6, 261.6, 196.0, 261.6, 293.7, 392.0]
for k in range(int((TOTAL - 40) / (beat / 2))):
    st = 40 + k * beat / 2; i0 = int(st * SR); L = int(0.45 * SR)
    if i0 + L > N: break
    f = notes[k % 8] * (1 if st < 107 else 2 if k % 16 > 7 else 1)
    tt = np.arange(L) / SR
    pulse[i0:i0 + L] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 7) * 0.05
pulse *= env(40, 46, 140, 146.1)
# sub drone + tension riser into the final reveal
sub = np.sin(2 * np.pi * 55 * t) * 0.07 * env(0, 8, 140, 146.1) * np.interp(t, [0, 60, 125, 146], [0.4, 0.6, 1, 1])
noise = rng.normal(0, 1, N)
riser = onepole(noise, 3000) * env(136, 146.1, 146.1, 146.3) * np.interp(t, [136, 146.1], [0.0, 0.10]) * (np.linspace(0, 1, N) * 0 + 1)
music = pad + pulse + sub + riser
# ---------------- sfx
sfx = np.zeros(N)
def add(at, x, g=1.0):
    i0 = int(at * SR); x = x[:max(0, N - i0)]; sfx[i0:i0 + len(x)] += x * g
def burst(dur, f0, f1, g=0.3, decay=6.0, noise_amt=0.0):
    tt = np.arange(int(dur * SR)) / SR; f = f0 + (f1 - f0) * tt / dur
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * decay)
    if noise_amt: x += rng.normal(0, 1, len(tt)) * np.exp(-tt * decay * 1.5) * noise_amt
    return x * g
def whoosh(dur, g=0.12, rev=False):
    x = rng.normal(0, 1, int(dur * SR)); tt = np.linspace(0, 1, len(x))
    y = np.zeros_like(x);
    for fc in (400, 1200, 3000): y += onepole(x, fc) - onepole(x, fc * 0.4)
    y *= np.sin(np.pi * tt) ** 2 * g
    return y[::-1] if rev else y
def click(g=0.5):
    x = burst(0.06, 1800, 600, g, 60, 0.6); y = burst(0.16, 140, 70, g * 0.9, 22, 0.15)
    out = np.zeros(int(0.3 * SR)); out[:len(x)] += x; out[int(0.09 * SR):int(0.09 * SR) + len(y)] += y; return out
def chime(g=0.2, f=880): return burst(1.2, f, f, g, 3.2) + burst(1.2, f * 1.5, f * 1.5, g * 0.5, 4.0)
def tick(g=0.25): return burst(0.05, 2400, 1800, g, 90, 0.2)
def boom(g=0.5): return burst(2.8, 70, 38, g, 1.6, 0.05)

# scene boundary whooshes
for b in (21.0, 40.2, 58.7, 73.6, 88.0, 107.3, 125.7):
    add(b - 0.5, whoosh(1.0, 0.10, True))
add(9.9 - 0.2, boom(0.55)); add(9.9 - 1.4, whoosh(1.4, 0.12, True))
# access: reader beep, verified ticks, lock release, door
add(49.55, burst(0.12, 1500, 1500, 0.15, 10)); add(52.3, tick(0.18)); add(53.0, tick(0.18)); add(53.7, tick(0.18))
add(54.25, click(0.55)); add(54.75, whoosh(0.9, 0.06))
# occupancy count pings (soft, sparse)
for k in range(6): add(61.5 + k * 2.0, tick(0.12))
# projector / sensor alert
add(77.06, click(0.25)); add(80.16, burst(0.18, 880, 880, 0.2, 12)); add(80.4, burst(0.18, 880, 880, 0.2, 12)); add(82.9, chime(0.22, 740))
# HVAC airflow
air = onepole(rng.normal(0, 1, N), 1200) - onepole(rng.normal(0, 1, N), 200)
air *= np.interp(t, [87.5, 91, 104, 107.8], [0, 0.07, 0.07, 0]) * (1 + 0.15 * np.sin(2 * np.pi * 0.4 * t))
sfx += air
# prototype beats
for u in (3.5, 6.0, 9.1, 11.9, 14.6, 16.8): add(107.3 + u - 0.3, whoosh(0.6, 0.06))
add(107.3 + 0.2, chime(0.12, 660))
# app UI ticks
for k in range(7): add(125.7 + k * (20.4 / 7), tick(0.3))
# final
add(146.1 - 0.05, boom(0.7)); add(146.1, chime(0.28, 523.2) + chime(0.2, 392.0))
for tw, f in ((149.3, 700), (150.17, 800), (151.28, 900), (152.32, 1050)): add(tw, burst(0.5, f, f, 0.10, 6))

def norm_to(x, peak): return x / (np.max(np.abs(x)) + 1e-9) * peak
music = norm_to(music, 0.5); sfx = norm_to(sfx, 0.6)
def save(path, x):
    st = np.stack([x, x], 1); pcm = (np.clip(st, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
save("/tmp/work/v5/music.wav", music); save("/tmp/work/v5/sfx.wav", sfx)
print("ok")
