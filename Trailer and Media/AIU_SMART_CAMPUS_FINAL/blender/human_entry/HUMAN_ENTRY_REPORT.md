# Human door-entry preview v1 (working file: AIU_HUMAN_door_entry_v1.blend)
Preview: renders/AIU_HUMAN_DOOR_ENTRY_PREVIEW_v1.mp4 — 960x540, 30 fps, 354 frames (11.8 s, Blender frames 45–398), Cycles 16 spp, no audio.
Approved scene/.blend, review_v3 and earlier trailer exports were not modified (new .blend only).

## What was built
- Character: Quaternius CC0 Superhero_Female (UBC Standard) + our own procedural clothes/hair; animation from Quaternius UAL clips (Walk_Formal_Loop, Idle_Loop) blended by speed, walk phase driven by distance travelled.
- Sequence (30 fps): walk f45–169 -> stops at reader, head turns to reader -> amber verification (overlay "VERIFYING IDENTITY...") -> GRANT f225 ("ACCESS GRANTED") -> she does not move toward the handle until f230 (lock releases 229–241) -> left hand reaches (IK) and touches lever f244 -> lever pressed 246–254 -> door opens (approved timing 256–346) -> she releases at f268 and walks through the doorway from f296, turning right inside the room.
- 4 cameras with hard cuts at f45/149/225/296. Overlay is a human-scene variant of the approved panel (human_entry/overlay/), marked "CONCEPT VISUALISATION · NOT LIVE HARDWARE DATA"; no facial-recognition claim.

## Measured checks (verify.py, per frame)
- Hand-to-lever: 27 frames in contact, mean error 2.4 mm, max 27 mm (f269, release start).
- Body vs door leaf/jambs/walls/chairs (circle r=0.20 m): min clearance +8 mm (f309, latch jamb corner) — no penetration by this model.
- Feet: lowest ball height 4 mm, highest planted 38 mm (no floating/sinking measured). Planted-foot slide during the approach walk: median 0.26 cm/frame; worst 5.4 cm/frame at walk start (f296–297), ~5 cm/frame elsewhere in a few frames.
Visual inspection: contact sheet of every 15th frame plus detail stills; I did not watch the clip in motion.

## Changes vs approved door scene (working copy only)
- Lever press direction flipped (approved file lifts the handle on press; ours pushes it down so a hand can operate it). Timing unchanged.
- Male character hidden in this file.

## Honest limitations
- Quaternius Standard has only Superhero proportions; the male was too exaggerated, so the TA is the female model. Stylized, not photoreal; hair is a simplified cap; fingers are not individually posed around the lever.
- Door-open motion is slow (approved timing), so she waits ~1 s after releasing before walking in.
- Feet re-pivot ~50° in place while turning to the door (small slide); brief shuffle at walk start.
- Room has no aisle in the approved layout, so she turns south along the free strip next to the wall and the shot ends there.
- Verification panel text is small at 960 px width; fine at 1920.
- Classroom lecturer/students NOT started. Final trailer NOT rendered.
