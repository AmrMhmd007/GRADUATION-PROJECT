# Shot 01 refinement — how to render the two quality-gate stills

Status: script updated and syntax-checked only. **No Blender render of these changes exists yet.** Nothing below is a claim about how it looks.

Run in Terminal (Blender 5.2.2 path assumed; adjust if different):

    B=/Applications/Blender.app/Contents/MacOS/Blender
    S="$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/aiu_test01_corridor_door.py"
    $B -b -P "$S" -- --mode shot01 --samples 64        # fast review pass (both stills)
    $B -b -P "$S" -- --mode shot01                      # 128 samples final-quality stills
    # options: --only wide | --only macro | --green (adds GRANT-state macro) | --exposure -0.3 | --wash 20 | --out <folder>

Outputs (`blender/renders/`): `AIU_SHOT01_wide_f0001.png`, `AIU_SHOT01_reader_macro_f0184.png` (amber verifying), optional `AIU_SHOT01_reader_macro_GRANT_f0300.png`, and `AIU_SHOT01_render_settings.json` (the settings actually used, written by Blender).
Settings: Cycles, Metal GPU, 1920×1080, 16-bit PNG, OpenImageDenoise, 8 bounces, AgX, exposure 0.

Cameras: wide = 24 mm f/5.6 from the corridor's left side at 1.55 m eye height, angled onto door 3031; macro = 85 mm f/3.2 about 1 m from the reader, framed to include the door jamb. The reader geometry/materials are untouched.

Added around the reader (script-level; judge in the render): door kick plate, hinge barrels, closer, threshold and gaskets, ceiling cable tray / smoke detector / sprinkler / exit sign, notice board, extinguisher, bench, wall wear gradient and stains, a soft wall-wash light above the door.

Animation logic (unchanged and still the rule): ring amber from frame 170, GREEN only at frame 225 (GRANT); strike keeper moves 227–240; lever 248–256; door opens 250–340.

## Verification overlay (done, checked)
`overlay/AIU_verification_overlay_ProRes4444.mov` — 1920×1080, 30 fps, 390 frames, ProRes 4444 with alpha (checked with ffprobe; design checked on test frames against a grey backdrop). Also `overlay/frames/ov_0001…0390.png` (RGBA) and `overlay/overlay_timing.json`.
IDENTITY 172 → ACCOUNT 186 → ROOM 198 → SCHEDULE 208 → BACKEND 216 → GRANTED 225 (green, same frame as the ring). Navy/white/amber/green; carries the label "CONCEPT VISUALISATION · NOT LIVE HARDWARE DATA". Text is not in the 3D scene.
Use: Final Cut Pro — place on the track above the Blender shot, frame 1 aligned. After Effects is not installed or required; the same .mov imports there if you later have it.
Regenerate: `python3 overlay/make_verification_overlay.py`.
