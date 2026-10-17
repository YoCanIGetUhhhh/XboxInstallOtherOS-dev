/*
 * QEMU audio driver "xaudio2" for the Xbox app: plays the guest's sound through native/uwp_audio.c (XAudio2).
 * Copied into qemu-src/audio/ by native/patch_qemu_audio.py.
 *
 * The mixing engine converts whatever the guest plays to 16-bit stereo; this driver only queues it.
 * QEMU keeps what XAudio2 has no room for yet, so the guest is paced by the real sound clock.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "qemu/error-report.h"
#include "audio.h"

#define AUDIO_CAP "xaudio2"
#include "audio_int.h"

int uwp_snd_open(int rate, int channels, int block_bytes);
void uwp_snd_enable(int on);
size_t uwp_snd_write(const void *buf, size_t len);
void uwp_snd_close(void);
const char *uwp_snd_error(void);

typedef struct XaVoiceOut {
    HWVoiceOut hw;
} XaVoiceOut;

static int xa_init_out(HWVoiceOut *hw, struct audsettings *as, void *drv_opaque)
{
    struct audsettings obt = *as;

    obt.fmt = AUDIO_FORMAT_S16;
    obt.nchannels = 2;
    obt.endianness = 0;
    if (uwp_snd_open(obt.freq, 2, 2048) != 0) {
        error_report("xaudio2: %s", uwp_snd_error());
        return -1;
    }
    error_report("xaudio2: %s", uwp_snd_error());
    audio_pcm_init_info(&hw->info, &obt);
    hw->samples = 4096;
    return 0;
}

static void xa_fini_out(HWVoiceOut *hw)
{
    uwp_snd_close();
}

static size_t xa_write(HWVoiceOut *hw, void *buf, size_t len)
{
    return uwp_snd_write(buf, len);
}

static void xa_enable_out(HWVoiceOut *hw, bool enable)
{
    uwp_snd_enable(enable ? 1 : 0);
}

static void *xa_audio_init(Audiodev *dev, Error **errp)
{
    return &xa_audio_init;
}

static void xa_audio_fini(void *opaque)
{
}

static struct audio_pcm_ops xa_pcm_ops = {
    .init_out        = xa_init_out,
    .fini_out        = xa_fini_out,
    .write           = xa_write,
    .buffer_get_free = audio_generic_buffer_get_free,
    .run_buffer_out  = audio_generic_run_buffer_out,
    .enable_out      = xa_enable_out,
};

static struct audio_driver xa_audio_driver = {
    .name           = "xaudio2",
    .descr          = "XAudio2 sound output (Xbox app)",
    .init           = xa_audio_init,
    .fini           = xa_audio_fini,
    .pcm_ops        = &xa_pcm_ops,
    .max_voices_out = 1,
    .max_voices_in  = 0,
    .voice_size_out = sizeof(XaVoiceOut),
    .voice_size_in  = 0,
};

static void register_audio_xaudio2(void)
{
    audio_driver_register(&xa_audio_driver);
}
type_init(register_audio_xaudio2);
