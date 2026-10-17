"""Sound: add QEMU audio driver "xaudio2" (native/qemu_xaudio2audio.c -> qemu-src/audio/xaudio2audio.c).

Registers the new driver name with QEMU's option system (qapi/audio.json) and the two places in audio/ that
list every driver. The sound itself is played by native/uwp_audio.c, linked into qemu.dll.
Run from the folder that contains qemu-src.
"""
import os
import shutil
import sys

root = "qemu-src/"


def edit(path, old, new, what):
    t = open(root + path, encoding="utf-8").read()
    if t.count(old) != 1:
        sys.exit("PATCH FAILED (audio %s): found %d times in %s" % (what, t.count(old), path))
    open(root + path, "w", encoding="utf-8", newline="\n").write(t.replace(old, new))


here = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(here, "qemu_xaudio2audio.c"), root + "audio/xaudio2audio.c")

edit("qapi/audio.json", "  'data': [ 'none',\n", "  'data': [ 'none',\n            'xaudio2',\n", "enum")
edit("qapi/audio.json", "    'none':      'AudiodevGenericOptions',\n",
     "    'none':      'AudiodevGenericOptions',\n    'xaudio2':   'AudiodevGenericOptions',\n", "union")
edit("audio/audio_template.h", "    case AUDIODEV_DRIVER_NONE:\n        return dev->u.none.TYPE;\n",
     "    case AUDIODEV_DRIVER_NONE:\n        return dev->u.none.TYPE;\n"
     "    case AUDIODEV_DRIVER_XAUDIO2:\n        return dev->u.xaudio2.TYPE;\n", "template")
edit("audio/audio.c", "        CASE(NONE, none, );\n", "        CASE(NONE, none, );\n        CASE(XAUDIO2, xaudio2, );\n", "pdos")
edit("audio/meson.build", "  'noaudio.c',\n", "  'noaudio.c',\n  'xaudio2audio.c',\n", "meson")
print("QEMU audio driver xaudio2 added")
