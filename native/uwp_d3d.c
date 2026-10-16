/* GPU direct: the screen buffer (a DXGI swap chain) is made here, with the Direct3D 11 device that the
   graphics library (ANGLE) already uses. QEMU draws into its back buffer through ANGLE, and the app attaches
   the swap chain to its SwapChainPanel from the app's own screen thread (qemu_dll_attach_panel).

   Only COM calls through the objects ANGLE hands us are used, so no new Windows imports are needed. */
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_3.h>
#include <stdio.h>

static const IID UWP_IID_IDXGIDevice    = {0x54ec77fa, 0x1377, 0x44e6, {0x8c, 0x32, 0x88, 0xfd, 0x5f, 0x44, 0xc8, 0x4c}};
static const IID UWP_IID_IDXGIFactory2  = {0x50c83a1c, 0xe072, 0x4c48, {0x87, 0xb0, 0x36, 0x30, 0xfa, 0x36, 0xa6, 0xd0}};
static const IID UWP_IID_ID3D11Texture2D = {0x6f15aaf2, 0xd208, 0x4e89, {0x9a, 0xb4, 0x48, 0x95, 0x35, 0xd3, 0x4f, 0x9c}};
static const IID UWP_IID_IDXGISwapChain2 = {0xa8be2ac4, 0x199f, 0x4946, {0xb3, 0x31, 0x79, 0x59, 0x9f, 0xb9, 0x8d, 0xe7}};
static const IID UWP_IID_ISwapChainPanelNative = {0xf92f19d2, 0x3ade, 0x45a6, {0xa2, 0x0c, 0xf6, 0xf1, 0xea, 0x90, 0x55, 0x4b}};

/* ISwapChainPanelNative is not in the MinGW headers: IUnknown + SetSwapChain. */
typedef struct UwpPanelNative UwpPanelNative;
typedef struct {
    HRESULT (STDMETHODCALLTYPE *QueryInterface)(UwpPanelNative *, REFIID, void **);
    ULONG (STDMETHODCALLTYPE *AddRef)(UwpPanelNative *);
    ULONG (STDMETHODCALLTYPE *Release)(UwpPanelNative *);
    HRESULT (STDMETHODCALLTYPE *SetSwapChain)(UwpPanelNative *, IDXGISwapChain *);
} UwpPanelNativeVtbl;
struct UwpPanelNative { const UwpPanelNativeVtbl *lpVtbl; };

extern void *uwp_panel;               /* the app's SwapChainPanel (IUnknown), set by qemu_dll_set_panel */
static int g_pw = 1280, g_ph = 720;   /* panel size in real pixels */
static float g_sx = 1.0f, g_sy = 1.0f; /* panel composition scale */
static IDXGISwapChain1 *g_sc;
static ID3D11Texture2D *g_back;
static volatile LONG g_attached;
static char g_err[160];

__declspec(dllexport) void qemu_dll_set_panel_size(int w, int h, float sx, float sy)
{
    if (w > 0 && h > 0) { g_pw = w; g_ph = h; }
    if (sx > 0.01f && sy > 0.01f) { g_sx = sx; g_sy = sy; }
}

const char *uwp_d3d_error(void) { return g_err; }
int uwp_d3d_width(void) { return g_pw; }
int uwp_d3d_height(void) { return g_ph; }

/* Returns the back buffer texture (ID3D11Texture2D*) or NULL. Called on QEMU's main loop thread. */
void *uwp_d3d_create(void *d3d11_device)
{
    ID3D11Device *dev = (ID3D11Device *)d3d11_device;
    IDXGIDevice *dxdev = NULL;
    IDXGIAdapter *adapter = NULL;
    IDXGIFactory2 *factory = NULL;
    DXGI_SWAP_CHAIN_DESC1 d;
    HRESULT hr;

    if (g_back) return g_back;
    if (!dev) { snprintf(g_err, sizeof g_err, "no Direct3D 11 device from the graphics library"); return NULL; }
    hr = ID3D11Device_QueryInterface(dev, &UWP_IID_IDXGIDevice, (void **)&dxdev);
    if (FAILED(hr)) { snprintf(g_err, sizeof g_err, "IDXGIDevice 0x%08lx", (unsigned long)hr); return NULL; }
    hr = IDXGIDevice_GetAdapter(dxdev, &adapter);
    IDXGIDevice_Release(dxdev);
    if (FAILED(hr)) { snprintf(g_err, sizeof g_err, "GetAdapter 0x%08lx", (unsigned long)hr); return NULL; }
    hr = IDXGIAdapter_GetParent(adapter, &UWP_IID_IDXGIFactory2, (void **)&factory);
    IDXGIAdapter_Release(adapter);
    if (FAILED(hr)) { snprintf(g_err, sizeof g_err, "IDXGIFactory2 0x%08lx", (unsigned long)hr); return NULL; }

    ZeroMemory(&d, sizeof d);
    d.Width = g_pw;
    d.Height = g_ph;
    d.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    d.SampleDesc.Count = 1;
    d.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    d.BufferCount = 3;
    d.Scaling = DXGI_SCALING_STRETCH;
    d.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
    d.AlphaMode = DXGI_ALPHA_MODE_IGNORE;
    hr = IDXGIFactory2_CreateSwapChainForComposition(factory, (IUnknown *)dev, &d, NULL, &g_sc);
    IDXGIFactory2_Release(factory);
    if (FAILED(hr)) { snprintf(g_err, sizeof g_err, "CreateSwapChainForComposition %dx%d 0x%08lx", g_pw, g_ph, (unsigned long)hr); g_sc = NULL; return NULL; }

    /* The panel shows one swap chain pixel per screen pixel; undo the panel's scale so it fits exactly. */
    {
        IDXGISwapChain2 *sc2 = NULL;
        if (SUCCEEDED(IDXGISwapChain1_QueryInterface(g_sc, &UWP_IID_IDXGISwapChain2, (void **)&sc2)) && sc2) {
            DXGI_MATRIX_3X2_F m;
            ZeroMemory(&m, sizeof m);
            m._11 = 1.0f / g_sx;
            m._22 = 1.0f / g_sy;
            IDXGISwapChain2_SetMatrixTransform(sc2, &m);
            IDXGISwapChain2_Release(sc2);
        }
    }

    hr = IDXGISwapChain1_GetBuffer(g_sc, 0, &UWP_IID_ID3D11Texture2D, (void **)&g_back);
    if (FAILED(hr)) { snprintf(g_err, sizeof g_err, "GetBuffer 0x%08lx", (unsigned long)hr); g_back = NULL; return NULL; }
    snprintf(g_err, sizeof g_err, "swap chain %dx%d (scale %.2f x %.2f)", g_pw, g_ph, g_sx, g_sy);
    return g_back;
}

/* Never wait for the TV: if the screen is not ready, this picture is skipped (the next one replaces it).
   Returns 1 when shown, 0 when skipped. */
int uwp_d3d_present(void)
{
    HRESULT hr;
    if (!g_sc) return 0;
    hr = IDXGISwapChain1_Present(g_sc, 0, DXGI_PRESENT_DO_NOT_WAIT);
    return hr == DXGI_ERROR_WAS_STILL_DRAWING ? 0 : 1;
}

/* Called by the app on its screen (UI) thread, again and again until it returns 1. */
__declspec(dllexport) int qemu_dll_attach_panel(void)
{
    UwpPanelNative *pn = NULL;
    HRESULT hr;

    if (g_attached) return 1;
    if (!g_sc || !uwp_panel) return 0;
    hr = ((IUnknown *)uwp_panel)->lpVtbl->QueryInterface((IUnknown *)uwp_panel, &UWP_IID_ISwapChainPanelNative, (void **)&pn);
    if (FAILED(hr) || !pn) return -(int)(hr & 0x7fffffff) - 1;
    hr = pn->lpVtbl->SetSwapChain(pn, (IDXGISwapChain *)g_sc);
    pn->lpVtbl->Release(pn);
    if (FAILED(hr)) return -(int)(hr & 0x7fffffff) - 1;
    InterlockedExchange(&g_attached, 1);
    return 1;
}
