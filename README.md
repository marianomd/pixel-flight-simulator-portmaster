# Pixel Flight Simulator for PortMaster

Unofficial, ready-to-run PortMaster package for
[Pixel Flight Simulator](https://github.com/game-de-it/pixel-flight-simulator)
by game-de-it. Built from version 1.0.1, commit
`59ae47fee75960f976e2a213a23fbb0d1517e640`.

Tested on an R36S Plus running ArchR 20260709 at 720x720 using the
PortMaster Pyxel 2.9.5 / Python 3.11 runtime.

## Installation

1. Download `pixelflightsimulator.zip` from the latest GitHub Release.
2. Extract it directly into the `ports` directory on the games card.
3. Restart or refresh EmulationStation.
4. Open **Ports > Pixel Flight Simulator**.

PortMaster downloads the `pyxel_2.9.5_python_3.11` runtime automatically
on the first launch if it is not already installed.

For square displays, choose **OPTIONS > GRAPHICS > ASPECT > 1:1**, then
restart the game. On RK3326 devices, 30 FPS is recommended if 60 FPS is
not stable.

## Controls

| Button | Action |
|---|---|
| Left stick / D-pad | Pitch and roll |
| L1 + left stick / D-pad | Rudder |
| R2 / R1 | Throttle up / down |
| Y / A | Flaps down / up |
| X / B | Trim down / up |
| L1 + B | Brake |
| Right stick or L2 + D-pad | Look left / right |
| L1 + X | Change view |
| L1 + L2 | Next destination |
| Select | Autopilot |
| Start | Options |
| Start + Select | Exit to EmulationStation |

## Licenses

Published with permission from the original developer, game-de-it, subject
to the separate licenses supplied with the game:

- The source code is distributed under the
  [PolyForm Noncommercial License 1.0.0](pixelflightsimulator/licenses/LICENSE.game.txt).
- The music, portraits, and title artwork are Copyright (c) 2026 game-de-it,
  all rights reserved. They are redistributed unmodified solely as part of
  Pixel Flight Simulator under the
  [asset license](pixelflightsimulator/licenses/LICENSE.assets.txt).
- Bundled third-party notices are preserved in
  [LICENSE.third-party.txt](pixelflightsimulator/licenses/LICENSE.third-party.txt).
- Pyxel is distributed under the
  [MIT License](pixelflightsimulator/licenses/LICENSE.pyxel.txt); its runtime
  is downloaded separately by PortMaster.

This repository does not relicense the game or its assets. Each component
remains subject to its corresponding license above.
