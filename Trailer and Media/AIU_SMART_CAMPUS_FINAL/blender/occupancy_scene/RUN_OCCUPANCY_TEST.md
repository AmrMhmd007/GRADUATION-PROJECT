# Occupancy scene — Stage 0 (EMPTY ROOM) — run instructions
Status: `aiu_occupancy_classroom_test.py` is syntax-checked only. **It has not been executed by anyone.** Expect fix rounds. No people, no count.

Approved-scene guard (these hashes were taken before this work; the script only READS the approved .blend):
  door script md5 1563a3a1264aac62b1ad4eb57b3c669b · approved .blend md5 84432446afb34ae72d9c975a691efc15   → `md5 "$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/aiu_test01_corridor_door.py" "$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/AIU_TEST01_corridor_door.blend"`

1) Build only (fast; catches script errors; writes occupancy_scene/AIU_OCC_classroom_test.blend):
B=/Applications/Blender.app/Contents/MacOS/Blender; S="$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/occupancy_scene/aiu_occupancy_classroom_test.py"; D="$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/occupancy_scene/renders/review_occ_v1"; mkdir -p "$D"
$B -b --python-exit-code 1 -P "$S" -- --mode build 2>&1 | tee "$D/occ_build_log.txt"

2) Logic checks only (no rendering): camera never inside geometry or door jambs, correct camera per cut, objects in frame, no human objects:
$B -b --python-exit-code 1 -P "$S" -- --mode review --only logic 2>&1 | tee "$D/occ_logic_log.txt"

3) Five stills (1280x720, 32 samples):  … -- --mode review --only stills 2>&1 | tee "$D/occ_stills_log.txt"
4) Preview animation (854x480, 12 samples, 450 frames; add `--step 2` for a faster, choppier test):  … -- --mode review --only preview 2>&1 | tee "$D/occ_preview_log.txt"

Outputs: renders/review_occ_v1/AIU_OCC_still_f0060|0150|0250|0330|0420.png, preview_frames/AIU_OCC_preview_0001…0450.png, logs.
Overlay (already generated, separate file): AIU_OCC_overlay_ProRes4444.mov (frames 375–450; label "OCCUPANCY DEMO — PEOPLE ASSETS PENDING"; no count).
