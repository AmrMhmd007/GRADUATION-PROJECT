# AIU SMART CAMPUS — Sound design report (review cut v4)

## Sources and licences
**No third-party audio is used.** I did not download any music or sound-effect library, so there are no external licences, attributions or
redistribution conditions to track. Every sound is synthesised by `final_trailer/audio_v4/make_audio.py` (numpy/scipy: sine, triangle and
sawtooth oscillators, filtered noise, convolution reverb), and the music is original and procedural. The soundtrack is project-owned
output of that script. There is no voice-over and no vocals.

## Files
- `final_trailer/audio_v4/make_audio.py`: generator. `timeline_v4.py` holds the segment timeline shared with the assembly script.
- `final_trailer/audio_v4/AIU_TRAILER_v4_soundtrack.wav`: 48 kHz, 16-bit stereo, 55.1 s, full mix.
- `final_trailer/audio_v4/music_only.wav`: music stem for reference.
- `final_trailer/audio_v4/sfx_events.json`: every effect with its timestamp and ducking depth.
- `final_trailer/AIU_SMART_CAMPUS_FINAL_REVIEW.mp4`: video plus AAC 192 kbps audio.
- `final_trailer/AIU_SMART_CAMPUS_FINAL_SILENT.mp4`: the same picture with no audio, kept as the silent version.

## Music
D minor to D major, 96 BPM. Detuned pad layers, a sine bass, a plucked 8th-note arpeggio that enters with the classroom and gains level, and a soft low pulse
from the attendance scene onward. It builds gradually and ends on a D-major chord with a low impact and a high plucked figure on the closing title, then fades out over
the last 1.4 s.

## Synchronised effects (times in the final cut)
- Opening: riser, then a low impact at 0.75 s.
- Door scene (locked to the frame numbers of the access sequence): soft verification ticks at the five step starts, a two-note access-granted tone at the GRANT frame (225), a lock-release click and thunk (frame 229), a handle click (246), and a soft air and hinge sound for the door opening (256).
- Classroom: low room tone only.
- Attendance scene: a soft blip when the camera callout appears, a rising sweep as the coverage volume grows, ticks as the pipeline steps light up (a brighter chime on the count-ingest step and a hollow tone on the concept "attendance record" step), and tiny ticks as the demo roster rows resolve.
- Transitions: a whoosh into the dashboard, one into the prototype, and a rise into the closing card, with a final resolving impact on the closing title.
- No sound implies unsupported hardware behaviour (no camera shutter, face-match beep or alarm).

## Mix and ducking
Music runs at about -5 dB relative to the effects bus and is ducked by 20–50 % for 0.9 s around key effects (opening impact, access granted, lock, closing).
A soft limiter (tanh) is applied, and the master is normalised to a -4 dBFS sample peak.

## Measured results (ffmpeg ebur128 on the final WAV)
Integrated loudness -17.6 LUFS, true peak -2.5 dBFS, so there is no clipping. The final file's audio is checked in `ASSEMBLY_REPORT.md` (v4 section).

## Limitations
The audio was verified with measurements and by reading the event timings. I did not listen to it, so taste, balance and the naturalness of the synthesised door and
handle sounds are unreviewed. Synthesised foley is simple compared with recorded sound; replace it with licensed recordings if a more realistic result is wanted.
