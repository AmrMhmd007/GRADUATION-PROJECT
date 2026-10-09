"""Transparent verification overlay: IDENTITY > ACCOUNT > ROOM > SCHEDULE > BACKEND > GRANTED
1920x1080, 30 fps, 390 frames (same timeline as the Blender scene; GRANT = frame 225, same frame the reader ring turns green).
Outputs (blender/overlay/): PNG sequence (RGBA) in frames/, AIU_verification_overlay_ProRes4444.mov (alpha), preview on navy.
Text lives ONLY here, never in 3D geometry. This is a concept visualisation; no live hardware data is shown."""
import cairo, math, os, subprocess, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); FR = os.path.join(HERE, 'frames'); os.makedirs(FR, exist_ok=True)
W, H, FPS, N = 1920, 1080, 30, 390
NAVY, WHITE, AMBER, GREEN = (0.039, 0.082, 0.208), (0.96, 0.97, 0.99), (1.0, 0.62, 0.10), (0.18, 0.86, 0.45)
STEPS = ['IDENTITY', 'ACCOUNT', 'ROOM', 'SCHEDULE', 'BACKEND', 'GRANTED']
START = [172, 186, 198, 208, 216, 225]            # frame each step becomes active; step i is "done" when step i+1 starts
GRANT = 225; FADE_IN = (160, 172); FADE_OUT = (330, 345)
FONT = 'Carlito'
def ease(x): x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)
def rr(c, x, y, w, h, r):
    c.new_sub_path(); c.arc(x + w - r, y + r, r, -math.pi / 2, 0); c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi); c.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); c.close_path()
def text(c, s, x, y, size, col, a=1.0, bold=False, spacing=0.0, anchor='c'):
    c.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL); c.set_font_size(size)
    tw = sum(c.text_extents(ch).x_advance + spacing for ch in s) - spacing
    x0 = x - tw / 2 if anchor == 'c' else x
    c.set_source_rgba(*col, a)
    for ch in s: c.move_to(x0, y); c.show_text(ch); x0 += c.text_extents(ch).x_advance + spacing
def alpha_at(f):
    if f < FADE_IN[0] or f > FADE_OUT[1]: return 0.0
    if f < FADE_IN[1]: return ease((f - FADE_IN[0]) / (FADE_IN[1] - FADE_IN[0]))
    if f > FADE_OUT[0]: return 1 - ease((f - FADE_OUT[0]) / (FADE_OUT[1] - FADE_OUT[0]))
    return 1.0
def frame(f):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); c = cairo.Context(s); a = alpha_at(f)
    if a <= 0: return s
    px, py, pw, ph = 96, 746, 1240, 192
    slide = (1 - a) * 18
    c.translate(0, slide)
    rr(c, px, py, pw, ph, 14); c.set_source_rgba(*NAVY, 0.80 * a); c.fill_preserve(); c.set_source_rgba(1, 1, 1, 0.14 * a); c.set_line_width(1.2); c.stroke()
    text(c, 'ACCESS VERIFICATION', px + 36, py + 40, 17, WHITE, 0.72 * a, True, 3.2, 'l')
    granted = f >= GRANT
    st, stc = ('ACCESS GRANTED', GREEN) if granted else ('VERIFYING', AMBER)
    text(c, st, px + pw - 36 - (len(st) * 11.5), py + 40, 17, stc, a, True, 3.2, 'l')
    x0, x1, cy = px + 100, px + pw - 100, py + 92
    xs = [x0 + (x1 - x0) * i / 5 for i in range(6)]
    for i in range(5):                                             # connector lines (fill as steps complete)
        done = f >= START[i + 1]
        prog = ease((f - START[i + 1] + 6) / 8) if f >= START[i + 1] - 6 else 0
        c.set_line_width(2); c.set_source_rgba(1, 1, 1, 0.16 * a); c.move_to(xs[i] + 26, cy); c.line_to(xs[i + 1] - 26, cy); c.stroke()
        if prog > 0:
            col = GREEN if (i + 1 == 5 and granted) else WHITE
            c.set_source_rgba(*col, 0.85 * a); c.move_to(xs[i] + 26, cy); c.line_to(xs[i] + 26 + (xs[i + 1] - xs[i] - 52) * prog, cy); c.stroke()
    for i, name in enumerate(STEPS):
        started = f >= START[i]; done = (f >= START[i + 1]) if i < 5 else (f >= GRANT + 6)
        final = (i == 5)
        if final and granted: col = GREEN
        elif started and not done: col = AMBER
        elif started and done: col = WHITE
        else: col = WHITE
        pend = not started
        pulse = 0.5 + 0.5 * math.sin((f - START[i]) * 0.5) if (started and not done and not final) else 0
        r = 20
        if started and not (done and not final):
            c.new_path(); c.arc(xs[i], cy, r + 6 + 3 * pulse, 0, 2 * math.pi); c.set_source_rgba(*col, (0.14 + 0.12 * pulse) * a); c.fill()
        c.new_path(); c.arc(xs[i], cy, r, 0, 2 * math.pi)
        if (started and done and not final) or (final and granted):
            c.set_source_rgba(*(GREEN if final else WHITE), 0.95 * a); c.fill()
            c.set_line_width(3.2); c.set_source_rgba(*NAVY, a); c.set_line_cap(cairo.LINE_CAP_ROUND); c.set_line_join(cairo.LINE_JOIN_ROUND)
            c.move_to(xs[i] - 8, cy + 1); c.line_to(xs[i] - 2, cy + 7); c.line_to(xs[i] + 9, cy - 7); c.stroke()
        else:
            c.set_source_rgba(*NAVY, 0.9 * a); c.fill_preserve(); c.set_line_width(2.4)
            c.set_source_rgba(*col, (0.30 if pend else 1.0) * a); c.stroke()
            if started and not done: c.new_path(); c.arc(xs[i], cy, 5, 0, 2 * math.pi); c.set_source_rgba(*col, a); c.fill()
        text(c, name, xs[i], cy + 52, 16, col if started else WHITE, (1.0 if started else 0.42) * a, started, 2.6)
    text(c, 'CONCEPT VISUALISATION  ·  NOT LIVE HARDWARE DATA', px + 36, py + ph - 16, 12, WHITE, 0.42 * a, False, 2.0, 'l')
    return s
if '--test' in sys.argv:
    for f in (150, 180, 200, 214, 222, 226, 260, 340):
        frame(f).write_to_png(os.path.join(FR, f'test_{f}.png'))
    sys.exit()
for f in range(1, N + 1): frame(f).write_to_png(os.path.join(FR, f'ov_{f:04d}.png'))
mov = os.path.join(HERE, 'AIU_verification_overlay_ProRes4444.mov')
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', os.path.join(FR, 'ov_%04d.png'), '-c:v', 'prores_ks', '-profile:v', '4444',
                '-pix_fmt', 'yuva444p10le', '-vendor', 'apl0', mov], check=True)
json.dump({'fps': FPS, 'frames': N, 'size': [W, H], 'step_start_frames': dict(zip(STEPS, START)), 'grant_frame': GRANT,
           'fade_in': FADE_IN, 'fade_out': FADE_OUT, 'note': 'Align frame 1 of the overlay with frame 1 of the Blender shot; GRANT = frame 225 = ring turns green.'},
          open(os.path.join(HERE, 'overlay_timing.json'), 'w'), indent=2)
print('OK', mov)
