"""Shared folder: let QEMU's vvfat make a bigger FAT16 disk (about 2 GB instead of about 500 MB).

New vvfat option big=on: 32 KB clusters (instead of 8 KB) and 4100 cylinders (instead of 1024), which is
4,132,800 sectors = about 2.1 GB and 64,575 clusters (FAT16 allows up to 65,524). FAT32 is not used because
QEMU's vvfat still writes a FAT16-style boot sector for it. Without big=on nothing changes.
Run from the folder that contains qemu-src.
"""
import sys

p = "qemu-src/block/vvfat.c"
t = open(p, encoding="utf-8").read()


def rep(a, b, what):
    global t
    if t.count(a) != 1:
        sys.exit("PATCH FAILED (vvfat %s): found %d times" % (what, t.count(a)))
    t = t.replace(a, b)


rep("""        {
            .name = "fat-type",""", """        {
            .name = "big",
            .type = QEMU_OPT_BOOL,
            .help = "Make a ~2 GB FAT16 disk (32 KB clusters)",
        },
        {
            .name = "fat-type",""", "option")
rep("""    floppy = qemu_opt_get_bool(opts, "floppy", false);
""", """    floppy = qemu_opt_get_bool(opts, "floppy", false);
    big = qemu_opt_get_bool(opts, "big", false);
""", "read option")
rep("""        cyls = s->fat_type == 12 ? 64 : 1024;""", """        cyls = s->fat_type == 12 ? 64 : 1024;
        if (big && s->fat_type == 16) {
            cyls = 4100;
        }""", "cylinders")
rep("""    s->sectors_per_cluster=0x10;
""", """    s->sectors_per_cluster=0x10;
    if (big && !floppy && s->fat_type == 16) {
        s->sectors_per_cluster = 0x40;
    }
""", "cluster size")
# declare the variable next to "floppy"
rep("""    bool floppy;""", """    bool floppy, big;""", "variable")
rep("""    "fat-type",
""", """    "fat-type",
    "big",
""", "strong options")
open(p, "w", encoding="utf-8", newline="\n").write(t)
print("vvfat big-disk patch applied")
