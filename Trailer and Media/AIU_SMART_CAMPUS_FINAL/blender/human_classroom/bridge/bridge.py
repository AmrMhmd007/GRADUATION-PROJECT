"""Local file-watching bridge for the AIU human door-entry work (written by Claude, visible to you).
Every second it checks bridge/cmd.py; when that file changes it runs it inside this Blender session and writes the output to bridge/cmd_log.txt.
Stop it by writing the single word STOP into bridge/cmd.py (or just quit Blender). It only reads/executes this one file."""
import bpy, os, traceback, io, contextlib
ROOT = '/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/blender/human_entry/bridge'
CMD = ROOT + '/cmd.py'; LOG = ROOT + '/cmd_log.txt'
_state = {'m': 0.0, 'run': True}
def _poll():
    if not _state['run']: return None
    try:
        if os.path.exists(CMD):
            m = os.path.getmtime(CMD)
            if m != _state['m']:
                _state['m'] = m
                src = open(CMD).read()
                if src.strip() == 'STOP':
                    _state['run'] = False; open(LOG, 'w').write('bridge stopped\n'); return None
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    try: exec(compile(src, CMD, 'exec'), {'__name__': '__cmd__', 'bpy': bpy})
                    except Exception: traceback.print_exc()
                open(LOG, 'w').write(f'#done {m}\n' + buf.getvalue())
    except Exception as e:
        try: open(LOG, 'w').write('bridge error: ' + repr(e))
        except Exception: pass
    return 1.0
bpy.app.timers.register(_poll, first_interval=1.0, persistent=True)
print('AIU bridge running')
