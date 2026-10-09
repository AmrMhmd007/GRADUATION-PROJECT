# Review v3 — run commands (Blender 5.2.2). Status: script syntax-checked only; NOT executed by the author.
Outputs go to blender/renders/review_v3/ (review_v2 is not touched).

1) Logic check + both stills (1920x1080, 64 samples), ~1-2 min on the M4:
B=/Applications/Blender.app/Contents/MacOS/Blender; S="$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/aiu_test01_corridor_door.py"; D="$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/renders/review_v3"; mkdir -p "$D"
$B -b --python-exit-code 1 -P "$S" -- --mode review3 --only stills 2>&1 | tee "$D/review3_stills_log.txt"

2) Low-res animation preview (960x540, 16 samples, frames 1-390; time unknown until measured):
$B -b --python-exit-code 1 -P "$S" -- --mode review3 --only preview 2>&1 | tee "$D/review3_preview_log.txt"

Outputs: AIU_SHOT01_wide_v3_f0001.png, AIU_SHOT01_reader_macro_v3_f0200.png, AIU_SHOT01_v3_render_settings.json, AIU_SHOT01_v3_preview_0001-0390.mp4
