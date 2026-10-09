# Third-party asset sources and licenses (AIU SMART CAMPUS trailer)

## Quaternius — Universal Base Characters [Standard]
- Source (official): https://quaternius.itch.io/universal-base-characters (linked from https://quaternius.com/packs/universalbasecharacters.html)
- File: `Universal Base Characters[Standard].zip` (≈122 MB), downloaded 2026-10-09 via the Chrome browser on this Mac, free ("no thanks, just take me to the downloads"; no payment).
- License: **CC0 1.0 Universal (public domain)** — stated on the pack page and in the zip's License_Standard.txt. No attribution required; credit "Quaternius" given here voluntarily.
- Contents used: Superhero_Male_FullBody.gltf and Superhero_Female_FullBody.gltf (body, eyes, eyebrows). The pack's separate hairstyle glTFs were tried but NOT used (alignment problems); hair is a simplified cap built from the head mesh with a procedural material. The [Standard] pack contains only the Superhero-proportion models; Regular/Teen proportions are in the paid Source version and were NOT purchased.
- Local copy: `assets/characters/quaternius/UBC_Standard/` (+ original zip).

## Quaternius — Universal Animation Library [Standard]
- Source (official): https://quaternius.itch.io/universal-animation-library (page also on https://quaternius.com/packs/universalanimationlibrary.html)
- File: `Universal Animation Library[Standard].zip` (≈15 MB), downloaded 2026-10-09, free.
- License: **CC0 1.0 Universal**. Rig is compatible with the Universal Base Characters (same bone names).
- Clips used so far in the door-entry preview: Walk_Formal_Loop, Idle_Loop. Inspected (not used in the door-entry shot): Interact, Push_Loop, Sitting_*; Sitting_Idle_Loop / Sitting_Talking_Loop are reserved for the classroom students.
- Local copy: `assets/characters/quaternius/UAL_Standard/` (+ original zip).

## Modifications we make (allowed by CC0)
Clothing (shirt, trousers, belt, shoes) and hair are our own procedural geometry/materials built in Blender by offsetting/cutting copies of the body mesh (no third-party clothing assets). Animation = Quaternius UAL clips (Walk_Formal_Loop, Idle_Loop) blended and distance-driven in Blender, plus a Blender IK constraint for the hand-on-lever contact. Door-entry preview character = Superhero_Female (the Superhero_Male build was too exaggerated for the intended realism and is hidden in the door-entry working file). Original downloaded files are kept unmodified.

## Not used / not downloaded
Mixamo, Sketchfab, Poly Pizza (blocked or require accounts). No paid assets.

## Update — classroom scene (human_classroom)
- Same two Quaternius CC0 packs (UBC Standard bodies, UAL Standard clips). Classroom uses Superhero_Female and Superhero_Male copies (male armature scaled ~0.86–0.9 in width to reduce the exaggerated build), clips Sitting_Idle_Loop, Sitting_Talking_Loop (one student), Idle_Talking_Loop + Idle_Loop (lecturer). Head-turn/posture motion is procedural.
- Shirts/hair are re-tinted per character; a collar "yoke" was added to the male shirt (our own geometry). No other third-party assets. No music/voice-over.
- Trailer typography: Carlito (SIL OFL, metric-compatible with Calibri) used for title cards/labels.
