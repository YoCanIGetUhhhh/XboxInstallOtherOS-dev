# Dusty Road Bus

Drive a bus as far as you can down a dusty country road — now in full 3D (low-poly, GTA: San Andreas-style third-person chase camera, built with Three.js, bundled in `vendor/`).

- The bus constantly creeps **left**. Go off the road and it **beeps**, the **engine heats up**, and at 100% it **explodes**.
- Live time of day and weather: clear days, cloud, rain, storms with lightning, fog, and nights with stars and a moon. Real-time shadows. Headlight beams, tail/brake lights, hazards and interior lights all light up.
- Infinite procedurally generated road: hills, bends, farms, barns, windmills, cows, fences and telephone poles.
- Every so often a bus stop appears. Pull into the gravel on the **right**, stop, and wait for passengers — but the engine heats while you wait. Miss 3 stops and you're fired.

## Controls
| Key | Action |
|---|---|
| W / Up | Gas |
| S / Down / Space | Brake |
| A D / Left Right | Steer |
| H | Headlights: auto / on / off |
| P / Esc | Pause (also saves) |
| M | Mute |
| F | Fullscreen (desktop app) |
| Q | Save & quit (desktop app, from title/pause) |

## Save system
Progress is autosaved every few seconds, on every completed stop, on pause and on exit:
- **Lifetime stats**: best distance, total distance, stops, passengers, runs, settings.
- **Current run**: position, speed, engine heat, passengers, time of day and weather. Choose **Continue** on the title screen to resume; **N** starts a new run. A run ends (and the run save is cleared) when the engine blows or you get fired.

Desktop build saves to `%APPDATA%\Dusty Road Bus\save.json`. In a browser it uses `localStorage`.

## Play in a browser
Open `index.html` (needs a GPU-accelerated browser with WebGL).

## Build the Windows .exe
Requires Node.js 18+ on Windows (or use the GitHub Action below).

```
cd dusty-road-bus
npm install
npm start        # run the desktop app
npm run dist     # builds dist/*.exe (portable + installer)
```

The workflow `.github/workflows/build-dusty-road-bus.yml` builds the `.exe` on a Windows runner; download it from the run's **Artifacts**.
