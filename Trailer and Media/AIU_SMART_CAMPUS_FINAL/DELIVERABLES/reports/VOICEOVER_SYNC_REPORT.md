# Voice-over sync report
Voice-over: user-supplied ElevenLabs "Mamdoh v4" MP3 (105.33 s; original kept in `original/`; 48 kHz mono WAV `AIU_SMART_CAMPUS_VOICEOVER.wav`). Script not rewritten. VO starts at film time 4.0 s; film is 115.0 s (closing hold ~9.3 s after the VO ends at 109.3 s).

**How timing was derived:** no speech recogniser was available, so sentence positions come from silence analysis of the VO (`vo_silences.json`), accuracy about ±0.4 s inside a clause. The access-granted frame of the door scene is pinned to 33.2 s.

| Film time | Segment | Source type |
|---|---|---|
| 0.0–15.5 | Opening / title | 3D & graphics, real AIU photos |
| 15.5–18.0 | Door approach | Blender (concept) |
| 18.0–29.7 | Access control UI + authorization check (GRANTED) | REAL recording |
| 29.7–38.97 | Verification overlay, handle, door | Blender (concept) |
| 38.97–43.36 | Access events log | REAL recording |
| 43.36–46.2 | Classroom | Blender |
| 46.2–57.2 | Indoor camera, coverage, pipeline | Blender, concept |
| 57.2–61.5 | Attendance result interface | Concept, labelled NOT IMPLEMENTED |
| 61.5–82.2 | Dashboard home, rooms, occupancy (SIMULATED), command center, automation | REAL recordings |
| 82.2–86.4 | Prototype image | Supplied image, unaltered |
| 86.4–95.6 | Architecture | Graphics |
| 95.6–99.1 | Recap montage | Re-used footage, labelled |
| 99.1–105.7 | Events / automation / zones | REAL recordings |
| 105.7–115.0 | Closing tagline / logo | Graphics |

## Checks actually performed
ffprobe (H.264 1920×1080 30 fps, AAC 48 kHz stereo, 115.000 s); full decode with no errors; freezedetect (no freeze ≥1.5 s); blackdetect (one 0.2 s dark-navy flash at 95.6 s at the architecture→montage dissolve); loudness −16.1 LUFS integrated; contact sheets and key frames viewed.
## NOT performed
I did not watch the film in motion or listen to the audio. Lip/phrase sync is predicted from the timeline and silence analysis, not heard. A 12 s excerpt (28–40 s, door grant) is saved as `AIU_SYNC_TEST_28-40s.mp4` for you to check. The Arabic/English wording against the visuals should be checked by a native listener.
