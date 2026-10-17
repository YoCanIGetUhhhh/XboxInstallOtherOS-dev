/* Sound out of the Xbox: QEMU's "xaudio2" audio driver (qemu_xaudio2audio.c) hands finished 16-bit stereo
   sound to these functions, which play it with XAudio2 (the sound API Xbox apps may use; DirectSound and
   WASAPI-by-name are not available to them).

   Kept in its own file, compiled with plain Windows headers, because QEMU's headers and the Windows audio
   headers do not mix well. Only called from QEMU's main loop thread. */
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <xaudio2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef XAUDIO2_VOICE_NOSAMPLESPLAYED
#define XAUDIO2_VOICE_NOSAMPLESPLAYED 0x0100
#endif

#define UWP_SND_BUFS 16          /* blocks queued at most (16 x 2048 bytes = about 170 ms at 48 kHz stereo) */

static IXAudio2 *g_xa;
static IXAudio2MasteringVoice *g_master;
static IXAudio2SourceVoice *g_src;
static unsigned char *g_mem;
static size_t g_block;
static int g_next;
static int g_started;
static char g_err[200];

const char *uwp_snd_error(void) { return g_err; }

void uwp_snd_close(void)
{
    if (g_src) { IXAudio2SourceVoice_Stop(g_src, 0, 0); IXAudio2SourceVoice_DestroyVoice(g_src); g_src = NULL; }
    if (g_master) { IXAudio2MasteringVoice_DestroyVoice(g_master); g_master = NULL; }
    if (g_xa) { IXAudio2_Release(g_xa); g_xa = NULL; }
    free(g_mem);
    g_mem = NULL;
    g_started = 0;
}

/* rate: samples per second; channels: 1 or 2; block_bytes: size of one queued block. 0 = ok. */
int uwp_snd_open(int rate, int channels, int block_bytes)
{
    WAVEFORMATEX wf;
    HRESULT hr;

    uwp_snd_close();
    hr = XAudio2Create(&g_xa, 0, XAUDIO2_DEFAULT_PROCESSOR);
    if (FAILED(hr) || !g_xa) {
        snprintf(g_err, sizeof g_err, "XAudio2Create failed 0x%08lx", (unsigned long)hr);
        g_xa = NULL;
        return -1;
    }
    hr = IXAudio2_CreateMasteringVoice(g_xa, &g_master, XAUDIO2_DEFAULT_CHANNELS, XAUDIO2_DEFAULT_SAMPLERATE,
                                       0, NULL, NULL, 0);
    if (FAILED(hr) || !g_master) {
        snprintf(g_err, sizeof g_err, "CreateMasteringVoice failed 0x%08lx", (unsigned long)hr);
        g_master = NULL;
        uwp_snd_close();
        return -1;
    }
    memset(&wf, 0, sizeof wf);
    wf.wFormatTag = WAVE_FORMAT_PCM;
    wf.nChannels = (WORD)channels;
    wf.nSamplesPerSec = (DWORD)rate;
    wf.wBitsPerSample = 16;
    wf.nBlockAlign = (WORD)(channels * 2);
    wf.nAvgBytesPerSec = wf.nSamplesPerSec * wf.nBlockAlign;
    hr = IXAudio2_CreateSourceVoice(g_xa, &g_src, &wf, 0, XAUDIO2_DEFAULT_FREQ_RATIO, NULL, NULL, NULL);
    if (FAILED(hr) || !g_src) {
        snprintf(g_err, sizeof g_err, "CreateSourceVoice %d Hz x%d failed 0x%08lx", rate, channels, (unsigned long)hr);
        g_src = NULL;
        uwp_snd_close();
        return -1;
    }
    g_block = (size_t)block_bytes - (size_t)block_bytes % wf.nBlockAlign;
    g_mem = malloc(g_block * UWP_SND_BUFS);
    if (!g_mem) {
        snprintf(g_err, sizeof g_err, "out of memory");
        uwp_snd_close();
        return -1;
    }
    g_next = 0;
    snprintf(g_err, sizeof g_err, "XAudio2 ready: %d Hz, %d channel(s), %d x %d byte blocks",
             rate, channels, UWP_SND_BUFS, (int)g_block);
    return 0;
}

void uwp_snd_enable(int on)
{
    if (!g_src) return;
    if (on && !g_started) { IXAudio2SourceVoice_Start(g_src, 0, 0); g_started = 1; }
    else if (!on && g_started) { IXAudio2SourceVoice_Stop(g_src, 0, 0); g_started = 0; }
}

static int free_blocks(void)
{
    XAUDIO2_VOICE_STATE st;
    memset(&st, 0, sizeof st);
    IXAudio2SourceVoice_GetState(g_src, &st, XAUDIO2_VOICE_NOSAMPLESPLAYED);
    return UWP_SND_BUFS - (int)st.BuffersQueued;
}

/* Queue as much of the sound as there is room for. Returns the bytes taken (the rest waits in QEMU). */
size_t uwp_snd_write(const void *buf, size_t len)
{
    size_t done = 0;
    if (!g_src || !g_mem) return len;   /* no sound device: drop it so the guest is not held up */
    while (len - done >= 4 && free_blocks() > 0) {
        XAUDIO2_BUFFER b;
        size_t n = len - done;
        unsigned char *dst = g_mem + (size_t)g_next * g_block;
        if (n > g_block) n = g_block;
        n -= n % 4;
        memcpy(dst, (const unsigned char *)buf + done, n);
        memset(&b, 0, sizeof b);
        b.AudioBytes = (UINT32)n;
        b.pAudioData = dst;
        if (FAILED(IXAudio2SourceVoice_SubmitSourceBuffer(g_src, &b, NULL))) break;
        g_next = (g_next + 1) % UWP_SND_BUFS;
        done += n;
    }
    if (!g_started) uwp_snd_enable(1);
    return done;
}
