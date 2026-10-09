"""Transparent overlay for the empty-room occupancy test: door camera vs interior camera. NO count is shown (no people exist in the scene).
Output: AIU_OCC_overlay_ProRes4444.mov (1920x1080, 30 fps, 450 frames, alpha) + AIU_OCC_overlay_panel.png. Align frame 1 with the Blender timeline."""
import cairo, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1920, 1080
NAVY, WHITE, AMBER, BLUE = (0.039, 0.082, 0.208), (0.96, 0.97, 0.99), (1.0, 0.62, 0.10), (0.62, 0.78, 1.0)
FONT = 'Carlito'
def rr(c, x, y, w, h, r):
    c.new_sub_path(); c.arc(x + w - r, y + r, r, -1.5708, 0); c.arc(x + w - r, y + h - r, r, 0, 1.5708); c.arc(x + r, y + h - r, r, 1.5708, 3.1416); c.arc(x + r, y + r, r, 3.1416, 4.7124); c.close_path()
def text(c, s, x, y, size, col, a=1.0, bold=False, sp=0.0):
    c.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL); c.set_font_size(size); c.set_source_rgba(*col, a)
    for ch in s: c.move_to(x, y); c.show_text(ch); x += c.text_extents(ch).x_advance + sp
s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); c = cairo.Context(s)
px, py, pw, ph = 96, 700, 1240, 270
rr(c, px, py, pw, ph, 14); c.set_source_rgba(*NAVY, 0.82); c.fill_preserve(); c.set_source_rgba(1, 1, 1, 0.14); c.set_line_width(1.2); c.stroke()
text(c, 'OCCUPANCY DEMO  —  PEOPLE ASSETS PENDING', px + 34, py + 42, 19, AMBER, 1.0, True, 3.0)
cw = (pw - 34 * 2 - 24) / 2
for i, (head, sub, line1, line2, col) in enumerate((('EXTERIOR DOOR CAMERA', 'Identity verification', 'Outside the room, at the door reader', 'Verifies who is entering', WHITE),
                                                    ('INTERIOR OCCUPANCY CAMERA', 'Anonymous head-count only', 'Inside the room, covers the seating area', 'No names · no identities · COUNT: —  (no people in scene)', BLUE))):
    x = px + 34 + i * (cw + 24); rr(c, x, py + 66, cw, 150, 10); c.set_source_rgba(1, 1, 1, 0.06); c.fill_preserve(); c.set_source_rgba(*col, 0.55); c.set_line_width(1.6); c.stroke()
    text(c, head, x + 22, py + 104, 20, col, 1.0, True, 2.2); text(c, sub, x + 22, py + 140, 24, WHITE, 1.0, True)
    text(c, line1, x + 22, py + 172, 17, WHITE, 0.78); text(c, line2, x + 22, py + 198, 17, WHITE, 0.78)
text(c, 'CONCEPT VISUALISATION  ·  NOT LIVE CAMERA OR SENSOR DATA', px + 34, py + ph - 16, 13, WHITE, 0.45, False, 2.0)
panel = os.path.join(HERE, 'AIU_OCC_overlay_panel.png'); s.write_to_png(panel)
mov = os.path.join(HERE, 'AIU_OCC_overlay_ProRes4444.mov')
vf = 'format=rgba,fade=t=in:st=12.5:d=0.5:alpha=1,fade=t=out:st=14.67:d=0.33:alpha=1'          # frame 375 -> 450 (30 fps)
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-framerate', '30', '-i', panel, '-t', '15', '-vf', vf, '-c:v', 'prores_ks', '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', mov], check=True)
print('OK', mov)
