# AIU SMART CAMPUS — Director's treatment, feasibility verdict, production plan (v6 direction)

No voice-over. No full film has been rendered. The old trailer is untouched.

## 0. Verdict first: what this environment can and cannot do
| Capability | Verified here? | Result |
|---|---|---|
| Photorealistic humans, walking/gestures | **Tested: no.** No human assets, rigs or motion data are available (no internet beyond package installs, no Blender/bpy, no GPU) | **Cannot meet the requirement.** My earlier silhouettes were rejected; I will not produce more. |
| Photoreal architecture via Blender | `pip install bpy` fails (no wheel for this Python) | Not available |
| Path-traced CPU rendering (Mitsuba 3, installed and working) | **Tested.** `pathtraced_hvac_feasibility_stills.jpg` = four real frames from a 12 s camera-path HVAC test scene (central unit with rotating fan, open-section main duct, tees, branch ducts, risers, diffusers, hangers, flanges, duct sensor probe, airflow particles). Physically lit and mechanically connected, but **procedural boxes/cylinders, flat materials, still noisy** | Better than before for mechanics only; **below "premium commercial" quality** |
| Render speed | Measured ≈11 s/frame at 640×360, 96 spp, 4 cores → 1080p at clean quality ≈ 1.5–2 min/frame ≈ **8–12 h per 12 s of footage** and each tool call is capped at ~3 min | Not practical for a 2-minute film |
| Real-time engines (Unreal/Unity/EEVEE) | No GPU / OpenGL | Not available |
| AI video generation | Not available as a tool | Not available |
| Licensed live-action footage | No stock access; AIU site unreachable | Not available (must be supplied) |
| Real dashboard recording | Chrome tool captures screenshots only; **no video recording** | Stills only; true video needs a local recording (Cmd+Shift+5) |
| Compositing, editing, typography, sound design, final export | Yes (ffmpeg, cairo, numpy) | Available and good |

**Conclusion:** I can edit, composite, design sound and export to broadcast spec, but I cannot create the photorealistic characters and detailed 3D worlds this film needs. Producing the full film here would again be a blockout. I recommend the pipeline in §6; I stop before scaling production, as instructed. I have **not** claimed the HVAC test as meeting the bar: it does not.

## 1. Story structure (118 s target)
1. **Beginning (0:00–0:22)** — Dawn at AIU. Ordinary morning: doors, rooms, air handling all run blind to what is happening inside.
2. **Problem (0:22–0:34)** — A building full of equipment that cannot see, verify or explain itself: a door that only checks a card, lights/air running in empty rooms, a duct nobody can read.
3. **Technological response (0:34–1:34)** — Cyber-physical control: SENSE → ANALYZE → VERIFY → DECIDE → ACT → MONITOR, shown through access, anonymous occupancy, device evidence, central HVAC, then the physical prototype.
4. **System demonstration (1:34–1:48)** — The real dashboard, with real implemented features and honest offline/unavailable states.
5. **Ending (1:48–1:58)** — Pull back to the connected building; title: AIU SMART CAMPUS · A CYBER-PHYSICAL CONTROL SYSTEM · DESIGNED FOR ALAMEIN INTERNATIONAL UNIVERSITY · SEE. UNDERSTAND. DECIDE. ACT.

### Motivated transitions (match cuts)
Door lock bolt macro → relay/PCB macro (backend) · ceiling camera lens iris → fan impeller (occupancy → HVAC) · diffuser grille square → the prototype's ceiling vent in the supplied image · fan rotation → circular status gauge in the real app · building section pull-back → connected-system diagram built from the same ducts/doors/cameras already seen.

## 2. Visual world (applies to every scene)
- **Architecture:** modern three-storey teaching building, warm stone cladding, blue-tinted glazing, navy-painted metal trim, red accent panel (taken from the real AIU photographs). Corridor 2.4 m wide, room 6×6×3 m, suspended grid ceiling, 2.2 m service plenum above.
- **Materials:** limestone/travertine, glazing, galvanised steel duct, white powder-coat, oak desks, navy chairs.
- **Characters (continuity):** lecturer — adult woman or man, navy blazer, white shirt, grey trousers, lanyard, laptop bag; students — varied casual clothing, no logos; **no student is ever identifiable or named**.
- **Light:** key from the left (window side) in all rooms; plenum lit by cool maintenance strips; colour pipeline ACES-style tone map, neutral highlights, cool navy shadows, red only on status LEDs/title rule.
- **Camera behaviour:** 35 mm / 50 mm equivalents, handheld-free dolly/gimbal language; moves are slow and motivated; rack focus only on hardware reveals.
- **Honesty rule:** all conceptual architecture carries a small "CONCEPTUAL ANIMATION" tag; only the supplied AIU photographs/footage are called authentic AIU.

## 3. Shot list (scene → shots with cinematography)
Columns: duration · camera/lens · camera move · subject · environment motion · light · FG/MG/BG · transition.

| # | Dur | Camera / lens | Move | Subject action | Environment motion | Light | FG / MG / BG | Transition |
|---|---|---|---|---|---|---|---|---|
| **1A** Campus dawn (authentic AIU footage — **to be supplied**) | 6 s | 24 mm drone/gimbal | Slow rise + forward dolly toward the AIU-logo façade | Few staff/students walking | Flags, tree movement | Low sun from left | Trees / façade / sky | Match cut: window glass reflection → interior of same window |
| 1B Façade to section | 4 s | 35 mm (3D) | Continuous push through glazing; façade dissolves to cutaway | — | Dust motes, light shafts | Same sun direction | Glazing / lobby / corridor | Camera passes a pillar (occlusion cut) |
| 1C Problem beat | 2 s | 50 mm | Static-to-slow tilt along dark service plenum | — | Blind duct hum | Cool | Pipes / duct / dark | Hard cut on door click |
| **2A** Corridor | 6 s | 35 mm | Tracking shot beside lecturer, left-to-right | Lecturer walks naturally | Students pass in BG, light flicker-free | Window key left | Door frames FG / lecturer MG / far door BG | Continuous |
| 2B Cutaway reveal | 4 s | 24 mm | Crane up through ceiling to plenum | — | Cables/ducts revealed | Plenum strips | Slab FG / ducts MG / rooms BG | Cut to door hardware |
| **3A** Approach | 5 s | 35 mm | Dolly backwards ahead of subject | Walks to door, stops | Lanyard sway | Left key | Door handle FG | Continuous |
| 3B Verify | 7 s | 50 mm, rack focus camera→face→reader | Slow orbit 30° | Looks at camera; small overlay: IDENTITY › ACCOUNT › ROOM › SCHEDULE › BACKEND DECISION | Status LED amber | Soft key | Reader FG / person MG / corridor BG | Match cut: lock bolt macro |
| 3C Grant → door | 6 s | Macro 100 mm then 35 mm | Pull-back to follow subject in | Bolt retracts **only after** GRANT; door opens; she enters | Door swing, room light spill | Warm room light | Frame FG / person / room BG | Camera follows through doorway |
| **4A** Lecture hall | 6 s | 28 mm | Dolly into populated room | Students settle, pages turn | Projector light, dust | Window key | Desks FG / students MG / screen BG | Rack focus up to ceiling |
| 4B Anonymous count | 6 s | 85 mm macro of ceiling camera, then wide | Tilt down; subtle anonymised point-cloud (dots, no faces) and counter | Same room | Counter increments | Same | Camera FG / dots MG / room BG | Lens iris match cut → fan |
| **5A** Projector | 5 s | 50 mm | Slow dolly along ceiling mount | Lecturer starts projector manually | Fan, lamp glow | Warm | Mount FG / projector MG | Macro on sensor |
| 5B Evidence | 7 s | 100 mm macro | Push-in on sensor, cable to node | Reading shown vs expected; abnormal value → alert card with stated evidence (labelled **SIMULATION**) | Cable LED pulses | Cool macro light | Sensor / cable / wall | Cut on alert tone |
| **6A** Central unit | 5 s | 35 mm | Dolly from fan along duct | — | Impeller rotation, particles | Plenum strips | Fan FG / duct MG | Continuous |
| 6B Duct journey | 8 s | 28 mm | Tracking along main duct, tee, branch | Air path visible through cutaway sections | Streamlines follow real duct only | Same | Hangers FG / duct MG / rooms BG | Descends through diffuser |
| 6C Room vent | 3 s | 24 mm from room | Tilt up to diffuser | Students below | Gentle airflow cues | Room light | Desks FG / diffuser MG | Match cut: diffuser square → prototype photo |
| **7** Prototype | 12 s | n/a (photograph) | Restrained pan/zoom only, **no fake motion** | — | Light sweep only | Original | Original | Cut: rooms 3031 › 3032 › 3033 › HVAC › sensors/cameras › technical compartment › full |
| **8** Real app | 14 s | **Screen recording** | Real scrolling/clicks | Dashboard, access events, occupancy, device health | Real UI | — | — | Fan-gauge match cut in |
| **9** Connected system | 6 s | 24 mm | Pull-back crane over building section | — | Data paths along existing doors/cameras/ducts only | Dusk | Building / paths / sky | Dolly into title |
| **10** Title | 8 s | 35 mm | Slow lateral dolly past façade | — | Light fade | Blue hour | Façade | Hold |

## 4. Technical accuracy rules (checked against the codebase)
- Door: face/identity check → backend authorization (account, room, schedule, access window) → GRANT or DENY → only then bolt retracts. DENY shown once for contrast. Door hardware is **not yet connected**: labelled conceptual.
- Occupancy: count only, no identities, no attendance; the real app shows "Unavailable" without sensors.
- Device health: alert carries expected vs observed values; no real fault claimed.
- HVAC: central unit → main duct → branch ducts → room vents; no cooling claim; room readings only when a sensor reports.
- No invented live readings; offline/unavailable shown as such.

## 5. Sound design (no voice)
Ambient beds: outdoor dawn air (0–10 s), interior room tone (10–60 s), plenum low hum + fan whirr (72–90 s), quiet UI bed (102–116 s). SFX cues: footsteps on stone/tile (24–30 s, synced to gait), reader beep (~31 s), relay click + bolt retract (~37 s, only after GRANT), door swing/latch (~38 s), projector fan (58 s), alert chime (~66 s), air movement (72–90 s), UI ticks (102–116 s), title low impact (124 s). Music: sparse piano/pad build, controlled swell at HVAC reveal and title; always below effects.

## 6. Recommended production pipeline (needs your machine or assets)
| Need | Best route | Who |
|---|---|---|
| Authentic campus motion | AIU media office permission, or film on campus (gimbal/phone, drone only with permission) | You / AIU |
| Detailed 3D rooms, door, ducts, camera hardware | **Blender (Cycles/EEVEE) on your Apple-silicon Mac**; I write the scene scripts and shot cameras, you run the render (GPU/Metal makes this minutes per second instead of hours) | You run; I author |
| Natural humans | Rigged characters from Mixamo/Blender Studio/Daz/Unreal MetaHuman with motion capture clips (check licences), or licensed stock footage composited with the 3D | You supply assets |
| Alternative for humans | A video-generation tool (Runway/Veo/Kling) for short human shots, accepting continuity risk | You |
| Real app footage | macOS Cmd+Shift+5 screen recording at 1080p/60 while the app runs; send the .mov | You |
| Edit, typography, overlays, sound, export | ffmpeg/cairo here | Me |

## 7. Risks
Human realism (highest) · render time if run on CPU · continuity of generated clips · licensing of third-party assets and AIU imagery · the real app currently shows mostly empty/offline states (honest, but visually sparse; consider seeding a clearly labelled demo dataset in a test database).

## 8. Final export spec
1920×1080 (3840×2160 if Blender renders allow), 16:9, 30 fps, H.264 High, CRF ≤ 18 (or ProRes 422 master), AAC 48 kHz stereo, Rec.709 / sRGB, loudness −16 LUFS, optional separate stems (music, ambience, SFX).

## 9. Approval gate
Next step needs your decision: (a) supply/agree the human and campus-footage route and run Blender locally (I will write the scripts and then edit/composite), or (b) accept a lower-fidelity stylised look (not what you asked for). Until then no full render will be made. Quality gate tests A (human movement) and C (infrastructure → app) **cannot** be honestly produced with the current tools; test B (HVAC) was attempted and judged insufficient as described above.
