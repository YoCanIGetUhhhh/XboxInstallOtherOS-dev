"""Make Google's ANGLE build use clang-cl (not Microsoft's cl.exe) for the Xbox/UWP toolchain.

The current Chromium build files give the UWP toolchain Microsoft's cl.exe but still pass clang-only
options, so cl.exe stops with "D8021 invalid numeric argument". Run from the ANGLE folder.
Writes what it changed to the file named in argv[1].
"""
import re
import sys

report = []
path = "build/toolchain/win/BUILD.gn"
t = open(path, encoding="utf-8").read()


def block_end(text, start):
    i = text.index("{", start)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(text)


changed = 0
clang = '"\\"" + rebase_path("//third_party/llvm-build/Release+Asserts/bin/clang-cl.exe", root_build_dir) + "\\""'
pos = 0
while True:
    m = re.search(r'msvc_toolchain\("uwp_[^)]*\)', t[pos:])
    if not m:
        break
    s = pos + m.start()
    e = block_end(t, s)
    block = t[s:e]
    report.append("=== before ===\n" + block)
    nb, n1 = re.subn(r'(?m)^(\s*)cl\s*=\s*.*cl\.exe.*$', lambda mm: mm.group(1) + "cl = " + clang, block)
    nb, n2 = re.subn(r'is_clang\s*=\s*false', 'is_clang = true', nb)
    # clang toolchains must be given the system include (and library) folders, like the desktop ones are.
    extra = []
    for var, want in (("sys_include_flags", "imsvc"), ("sys_lib_flags", "lld")):
        cands = re.findall(r'%s\s*=\s*"([^"]*)"' % var, t)
        report.append("%s candidates: %s" % (var, cands))
        pick = [c for c in cands if want in c] or cands[:1]
        if pick:
            val = re.sub(r'\$\{[A-Za-z_]+\.', '${store_cpu_toolchain_data.', pick[0])
            extra.append('    %s = "%s"' % (var, val))
    if extra and "sys_include_flags" not in nb:
        nb = re.sub(r'(?m)^(\s*cl = .*)$', lambda mm: mm.group(1) + "\n" + "\n".join(extra), nb, count=1)
    report.append("cl replaced: %d, is_clang changed: %d" % (n1, n2))
    report.append("=== after ===\n" + nb)
    changed += n1
    t = t[:s] + nb + t[e:]
    pos = s + len(nb)

if changed == 0:
    # show where the UWP toolchain is described so the next attempt can target it
    for mm in re.finditer(r"uwp|winuwp|store", t):
        a = max(0, mm.start() - 300)
        report.append("--- context at %d ---\n%s" % (mm.start(), t[a:mm.start() + 600]))
        if len(report) > 6:
            break
open(path, "w", encoding="utf-8", newline="\n").write(t)
try:
    g = open("build/toolchain/win/toolchain.gni", encoding="utf-8").read().split("\n")
    for i, l in enumerate(g):
        if "toolchain_is_clang" in l and ("assert" in l or "if (" in l):
            report.append("toolchain.gni:%d: %s" % (i + 1, l.strip()))
except Exception as ex:
    report.append("could not read toolchain.gni: %s" % ex)
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(report) + "\n")
print("\n".join(report))
if changed == 0:
    sys.exit("PATCH FAILED: no cl.exe line found in the UWP toolchain")
