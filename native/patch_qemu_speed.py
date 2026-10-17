"""Speed: QEMU's virtual CPU threads ("CPU n/TCG") run at AboveNormal priority, so the Xbox schedules them ahead of
other background work. The app sets QEMU's main loop to the same level (Highest in GPU mode), so it is never behind them.
Run from the folder that contains qemu-src."""
import sys

p = "qemu-src/util/qemu-thread-win32.c"
t = open(p, encoding="utf-8").read()
a = """    if (name_threads && name && !set_thread_description(hThread, name)) {
        fprintf(stderr, "qemu: failed to set thread description: %s\\n", name);
    }
    CloseHandle(hThread);"""
b = """    if (name_threads && name && !set_thread_description(hThread, name)) {
        fprintf(stderr, "qemu: failed to set thread description: %s\\n", name);
    }
    if (name && strstr(name, "/TCG")) {
        SetThreadPriority(hThread, THREAD_PRIORITY_ABOVE_NORMAL);
    }
    CloseHandle(hThread);"""
if t.count(a) != 1:
    sys.exit("PATCH FAILED (thread priority): found %d" % t.count(a))
t = t.replace(a, b)
open(p, "w", encoding="utf-8", newline="\n").write(t)
print("QEMU speed patch applied (virtual CPU threads AboveNormal)")
