# Pixel Flight Simulator for PortMaster

Unofficial, ready-to-run PortMaster package for
[Pixel Flight Simulator](https://github.com/game-de-it/pixel-flight-simulator)
by game-de-it. Built from version 1.0.1, commit
`59ae47fee75960f976e2a213a23fbb0d1517e640`.

Tested on an R36S Plus running ArchR 20260709 at 720x720 using the
PortMaster Pyxel 2.9.5 / Python 3.11 runtime.

## Installation

1. Download `pixelflightsimulator.zip` from the latest GitHub Release.
2. Copy the ZIP **without extracting it** into PortMaster's `autoinstall`
   directory. On ArchR this is normally
   `/storage/roms/ports/PortMaster/autoinstall/`.
3. Start PortMaster and wait for the automatic installation to finish.
4. Restart or refresh EmulationStation, then open
   **Ports > Pixel Flight Simulator**.

Other firmware may place the `autoinstall` directory elsewhere; see the
[PortMaster FAQ](https://portmaster.games/faq.html) for the corresponding
path. Extracting the package directly into `ports` is only a fallback manual
installation method.

PortMaster downloads the `pyxel_2.9.5_python_3.11` runtime automatically
on the first launch if it is not already installed.

For square displays, choose **OPTIONS > GRAPHICS > ASPECT > 1:1**, then
restart the game.

## Building and releasing

The release process is reproducible from the original game's source. It
downloads the selected upstream revision, runs upstream's `make_pyxapp.py` in
an isolated Pyxel 2.9.5 environment, builds the PortMaster ZIP, validates it,
and writes its checksum and release notes into `dist/`.

The Python source included in the currently published `.pyxapp` is also kept
unpacked under `src/pfs/`, so it can be reviewed directly on GitHub. A publish
run refreshes this snapshot together with the bundled game and licenses.

Preview the latest upstream release without changing tracked files:

```sh
python scripts/release.py
```

Build a specific upstream tag:

```sh
python scripts/release.py --upstream-ref v1.0.1
```

After reviewing the files in `dist/`, publish from a clean `main` branch:

```sh
python scripts/release.py --publish
```

Publishing updates the vendored game bundle and upstream license copies,
updates the provenance in this README, commits and pushes those changes, then
creates the next `vX.Y.Z-portmaster.N` GitHub Release using `gh`. Python, Git,
GitHub CLI authentication, and network access are required. The build script
creates and reuses its own virtual environment; Pyxel does not need to be
installed globally.

If that upstream version already has a PortMaster release, publishing stops to
avoid an accidental duplicate. An intentional port-only revision can specify
the next tag explicitly, for example:

```sh
python scripts/release.py --publish --upstream-ref v1.0.1 --release-tag v1.0.1-portmaster.2
```

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
