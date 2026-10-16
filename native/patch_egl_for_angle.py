"""Small fixes to QEMU's EGL/OpenGL helper code so it works with ANGLE (OpenGL ES 3.0 on Direct3D 11).

Run from the folder that contains qemu-src. Every change is checked: if QEMU's text is not what we
expect, this stops with an error instead of silently building something that will not work.

What it fixes (each one was found by reading the code, the first was seen in a real log):
  1. ANGLE (2016) cannot make a context current without a surface. We give it a small off-screen one.
  2. QEMU's blit shaders are "#version 300 es", so the context must be OpenGL ES 3, not 2.
  3. The drawing format must allow off-screen surfaces (EGL_PBUFFER_BIT).
  4. glFramebufferTexture2DEXT and friends are desktop-only names; the OpenGL loader aborts the
     whole app on ES when it cannot find them. The plain ES 3 names do the same job.
  5. GL_BGRA is not allowed for texture creation / reading in OpenGL ES 3. Use RGBA and swap the
     red and blue bytes ourselves when copying into QEMU's picture.
"""
import re
import sys

root = "qemu-src/"


def load(path):
    return open(root + path, encoding="utf-8").read()


def save(path, text):
    open(root + path, "w", encoding="utf-8", newline="\n").write(text)


def must_replace(text, old, new, what, count=1):
    n = text.count(old)
    if n != count:
        sys.exit("PATCH FAILED (%s): expected %d match(es), found %d" % (what, count, n))
    return text.replace(old, new)


# ---------- ui/egl-helpers.c ----------
p = "ui/egl-helpers.c"
t = load(p)

# 3. config: off-screen surfaces
t = must_replace(t, "EGL_SURFACE_TYPE, EGL_WINDOW_BIT,", "EGL_SURFACE_TYPE, EGL_WINDOW_BIT | EGL_PBUFFER_BIT,", "surface type", count=2)

# 2. ES 3 context for QEMU's own drawing
t = must_replace(t, "        EGL_CONTEXT_CLIENT_VERSION, 2,\n", "        EGL_CONTEXT_CLIENT_VERSION, 3,\n", "ES3 context")

# 1. a small off-screen surface to make contexts current
helper = '''
/* Xbox/ANGLE: contexts cannot be made current without a surface, so use a small off-screen one. */
EGLSurface qemu_uwp_surface(EGLContext ctx)
{
    static EGLSurface pb = EGL_NO_SURFACE;
    static const EGLint att[] = { EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE };

    if (ctx == EGL_NO_CONTEXT) {
        return EGL_NO_SURFACE;
    }
    if (pb == EGL_NO_SURFACE) {
        pb = eglCreatePbufferSurface(qemu_egl_display, qemu_egl_config, att);
        if (pb == EGL_NO_SURFACE) {
            error_report("egl: could not make the off-screen surface: %s",
                         qemu_egl_get_error_string());
        }
    }
    return pb;
}

/* GL_BGRA reads are not allowed in OpenGL ES 3: we read RGBA and swap red/blue here. */
static void uwp_swap_rb(uint8_t *base, int stride, int x, int y, int w, int h)
{
    int row, col;

    for (row = y; row < y + h; row++) {
        uint8_t *p = base + (size_t)row * stride + (size_t)x * 4;
        for (col = 0; col < w; col++, p += 4) {
            uint8_t r = p[0];
            p[0] = p[2];
            p[2] = r;
        }
    }
}

/* Copy the picture from the GPU. If the graphics library can hand it over in BGRA order
   (GL_EXT_read_format_bgra), the GPU does the colour swap and the CPU loop above is skipped. */
/* Measured on the Xbox (1.2.45/1.2.46): the BGRA read made glmark2 about 2x SLOWER than RGBA + our own
   swap (the library converts the picture in a slower way). So it starts switched off (0). */
static int uwp_bgra_state = 0; /* -1 try BGRA, 1 BGRA works, 0 RGBA + CPU swap */
static void uwp_read_pixels(int gx, int gy, int w, int h, uint8_t *base, int stride, int sx, int sy)
{
    uint8_t *p = base + (size_t)sx * 4;

    if (uwp_bgra_state < 0) {
        while (glGetError() != GL_NO_ERROR) {
        }
        if (!epoxy_has_gl_extension("GL_EXT_read_format_bgra")) {
            uwp_bgra_state = 0;
            error_report("egl: screen copy uses RGBA + CPU colour swap (no GL_EXT_read_format_bgra)");
        }
    }
    if (uwp_bgra_state != 0) {
        glReadPixels(gx, gy, w, h, GL_BGRA_EXT, GL_UNSIGNED_BYTE, p);
        if (uwp_bgra_state < 0) {
            uwp_bgra_state = (glGetError() == GL_NO_ERROR) ? 1 : 0;
            error_report("egl: screen copy uses %s", uwp_bgra_state ?
                         "BGRA from the GPU (no CPU colour swap)" : "RGBA + CPU colour swap (BGRA read refused)");
        }
        if (uwp_bgra_state == 1) {
            return;
        }
    }
    glReadPixels(gx, gy, w, h, GL_RGBA, GL_UNSIGNED_BYTE, p);
    uwp_swap_rb(base, stride, sx, sy, w, h);
}

/* "GPU direct": draw the finished picture straight into the app's SwapChainPanel (set by the app with
   qemu_dll_set_panel). No read-back to memory, no CPU copies. Returns false to use the normal path. */
extern void *uwp_panel;
extern volatile long uwp_direct_frames;
extern volatile int uwp_direct_w, uwp_direct_h;
static EGLSurface uwp_win = EGL_NO_SURFACE;
static int uwp_win_failed;

bool uwp_present(egl_fb *src)
{
    EGLContext ctx = eglGetCurrentContext();
    EGLint ww = 0, wh = 0;

    if (!uwp_panel || uwp_win_failed || !src->framebuffer || !src->width || !src->height) {
        return false;
    }
    if (uwp_win == EGL_NO_SURFACE) {
        uwp_win = eglCreateWindowSurface(qemu_egl_display, qemu_egl_config,
                                         (EGLNativeWindowType)uwp_panel, NULL);
        if (uwp_win == EGL_NO_SURFACE) {
            uwp_win_failed = 1;
            error_report("egl: direct screen not available (%s), using the normal copy",
                         qemu_egl_get_error_string());
            return false;
        }
        {
            EGLint r = 0, g = 0, b = 0, a = 0, st = 0, cid = 0, rb = 0;
            eglGetConfigAttrib(qemu_egl_display, qemu_egl_config, EGL_RED_SIZE, &r);
            eglGetConfigAttrib(qemu_egl_display, qemu_egl_config, EGL_GREEN_SIZE, &g);
            eglGetConfigAttrib(qemu_egl_display, qemu_egl_config, EGL_BLUE_SIZE, &b);
            eglGetConfigAttrib(qemu_egl_display, qemu_egl_config, EGL_ALPHA_SIZE, &a);
            eglGetConfigAttrib(qemu_egl_display, qemu_egl_config, EGL_SURFACE_TYPE, &st);
            eglGetConfigAttrib(qemu_egl_display, qemu_egl_config, EGL_CONFIG_ID, &cid);
            eglQuerySurface(qemu_egl_display, uwp_win, EGL_RENDER_BUFFER, &rb);
            error_report("egl: drawing straight into the app window (GPU direct); config %d R%dG%dB%dA%d surface-types 0x%x render-buffer 0x%x",
                         cid, r, g, b, a, st, rb);
        }
    }
    if (!eglMakeCurrent(qemu_egl_display, uwp_win, uwp_win, ctx)) {
        uwp_win_failed = 1;
        error_report("egl: direct screen make-current failed (%s), using the normal copy",
                     qemu_egl_get_error_string());
        eglMakeCurrent(qemu_egl_display, qemu_uwp_surface(ctx), qemu_uwp_surface(ctx), ctx);
        return false;
    }
    {
        static int interval_set;
        if (!interval_set) {
            interval_set = 1;
            eglSwapInterval(qemu_egl_display, 0); /* never wait for the TV refresh inside QEMU's main loop */
        }
    }
    eglQuerySurface(qemu_egl_display, uwp_win, EGL_WIDTH, &ww);
    eglQuerySurface(qemu_egl_display, uwp_win, EGL_HEIGHT, &wh);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
    glViewport(0, 0, ww, wh);
    glDisable(GL_SCISSOR_TEST);
    /* Test colour: the empty side bars are dark blue, so it is easy to see whether the window shows anything. */
    glClearColor(0.0f, 0.1f, 0.35f, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    if (ww > 0 && wh > 0) {
        double sx = (double)ww / src->width, sy = (double)wh / src->height;
        double s = sx < sy ? sx : sy;
        int dw = (int)(src->width * s), dh = (int)(src->height * s);
        int dx = (ww - dw) / 2, dy = (wh - dh) / 2;
        glBindFramebuffer(GL_READ_FRAMEBUFFER, src->framebuffer);
        /* the picture is stored upside down for the memory copy, so flip it back for the window */
        glBlitFramebuffer(0, src->height, src->width, 0, dx, dy, dx + dw, dy + dh,
                          GL_COLOR_BUFFER_BIT, GL_LINEAR);
    }
    /* The guest picture has alpha 0 (X8R8G8B8). The app window treats alpha as transparency,
       so make every pixel fully solid, or the picture is invisible (black). */
    glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_TRUE);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    {
        static int logged;
        GLenum ge = glGetError();
        EGLBoolean ok = eglSwapBuffers(qemu_egl_display, uwp_win);
        if (logged < 4 || ge != GL_NO_ERROR || !ok || (uwp_direct_frames % 300) == 0) {
            if (logged < 30) {
                logged++;
                error_report("egl: direct frame %ld: %dx%d into window %dx%d, gl error 0x%x, swap %s",
                             (long)uwp_direct_frames, src->width, src->height, ww, wh, ge,
                             ok ? "ok" : qemu_egl_get_error_string());
            }
        }
    }
    eglMakeCurrent(qemu_egl_display, qemu_uwp_surface(ctx), qemu_uwp_surface(ctx), ctx);
    uwp_direct_w = src->width;
    uwp_direct_h = src->height;
    uwp_direct_frames++;
    return true;
}
'''
marker = "void egl_fb_setup_for_tex("
t = must_replace(t, marker, helper.lstrip("\n") + "\n" + marker, "insert helpers")

# 4. EXT names -> plain ES 3 names
t = must_replace(t, "glFramebufferTexture2DEXT(", "glFramebufferTexture2D(", "FramebufferTexture2DEXT", count=1)
t = t.replace("GL_FRAMEBUFFER_EXT", "GL_FRAMEBUFFER").replace("GL_COLOR_ATTACHMENT0_EXT", "GL_COLOR_ATTACHMENT0")

# 5. RGBA instead of BGRA
t = must_replace(t, "0, GL_BGRA, GL_UNSIGNED_BYTE, 0);", "0, GL_RGBA, GL_UNSIGNED_BYTE, 0);", "texture format")
t = must_replace(
    t,
    "    glReadPixels(0, 0, surface_width(dst), surface_height(dst),\n"
    "                 GL_BGRA, GL_UNSIGNED_BYTE, surface_data(dst));\n",
    "    uwp_read_pixels(0, 0, surface_width(dst), surface_height(dst),\n"
    "                    surface_data(dst), surface_stride(dst), 0, 0);\n",
    "read pixels",
)
t = must_replace(
    t,
    "    glReadPixels(x, y, w, h,\n"
    "                 GL_BGRA, GL_UNSIGNED_BYTE, surface_data(dst) + x * 4);\n",
    "    uwp_read_pixels(x, y, w, h, surface_data(dst), surface_stride(dst), x, 0);\n",
    "read pixels rect",
)

pat = re.compile(r"eglMakeCurrent\(qemu_egl_display,\s*EGL_NO_SURFACE,\s*EGL_NO_SURFACE,\s*(\w+)\)")
t, n = pat.subn(r"eglMakeCurrent(qemu_egl_display, qemu_uwp_surface(\1), qemu_uwp_surface(\1), \1)", t)
if n != 1:
    sys.exit("PATCH FAILED (egl-helpers make current): expected 1, found %d" % n)
save(p, t)

# ---------- header ----------
p = "include/ui/egl-helpers.h"
t = load(p)
t = must_replace(t, "bool egl_init(", "EGLSurface qemu_uwp_surface(EGLContext ctx);\nbool uwp_present(egl_fb *src);\nbool egl_init(", "header")
save(p, t)

# ---------- ui/egl-context.c and ui/egl-headless.c ----------
for p in ("ui/egl-context.c", "ui/egl-headless.c"):
    t = load(p)
    t, n = pat.subn(r"eglMakeCurrent(qemu_egl_display, qemu_uwp_surface(\1), qemu_uwp_surface(\1), \1)", t)
    if n != 1:
        sys.exit("PATCH FAILED (%s make current): expected 1, found %d" % (p, n))
    save(p, t)

# GPU direct: show the picture in the app window instead of copying it to memory.
p = "ui/egl-headless.c"
t = load(p)
t = must_replace(t, """    egl_fb_read(edpy->ds, &edpy->blit_fb);
    dpy_gfx_update(edpy->dcl.con, x, y, w, h);""", """    if (uwp_present(&edpy->blit_fb)) {
        return;
    }
    egl_fb_read(edpy->ds, &edpy->blit_fb);
    dpy_gfx_update(edpy->dcl.con, x, y, w, h);""", "direct present")
save(p, t)

# Log which OpenGL ES versions the renderer asks for and whether the graphics library agrees (first few only).
p = "ui/egl-context.c"
t = load(p)
t = must_replace(t, """                          gles ? ctx_att_gles : ctx_att_core);
   return ctx;""", """                          gles ? ctx_att_gles : ctx_att_core);
   {
       static int logged;
       if (logged < 8) {
           logged++;
           error_report("egl: context %s %d.%d %s", gles ? "ES" : "GL",
                        params->major_ver, params->minor_ver,
                        ctx ? "created" : "refused");
       }
   }
   return ctx;""", "context log")
save(p, t)

print("EGL patches for ANGLE applied")
