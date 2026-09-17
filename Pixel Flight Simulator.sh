#!/bin/bash

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

if [ -d "/opt/system/Tools/PortMaster/" ]; then
  controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
  controlfolder="/opt/tools/PortMaster"
elif [ -d "$XDG_DATA_HOME/PortMaster/" ]; then
  controlfolder="$XDG_DATA_HOME/PortMaster"
else
  controlfolder="/roms/ports/PortMaster"
fi

source "$controlfolder/control.txt"
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"

get_controls

GAMEDIR="/$directory/ports/pixelflightsimulator"
CONFDIR="$GAMEDIR/conf"
PYXEL_PKG="pfs.pyxapp"
runtime="pyxel_2.9.5_python_3.11"
SYS_TEMP="${TMPDIR:-/tmp}"
export TMPDIR="${SYS_TEMP}/.pyx-v295up"
export pyxel_dir="$HOME/$runtime"

cd "$GAMEDIR" || exit 1
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

mkdir -p "$CONFDIR" "$pyxel_dir" "$TMPDIR"
export PFS_CONFIG_DIR="$CONFDIR"

if [ ! -f "$controlfolder/libs/${runtime}.squashfs" ]; then
  if [ ! -f "$controlfolder/harbourmaster" ]; then
    pm_message "This port requires the latest PortMaster."
    sleep 5
    exit 1
  fi
  $ESUDO "$controlfolder/harbourmaster" --quiet --no-check runtime_check "${runtime}.squashfs"
fi

if [[ "$PM_CAN_MOUNT" != "N" ]]; then
  $ESUDO umount "$pyxel_dir"
fi

$ESUDO mount "$controlfolder/libs/${runtime}.squashfs" "$pyxel_dir"

export LD_LIBRARY_PATH="${pyxel_dir}/libs.${DEVICE_ARCH}:${LD_LIBRARY_PATH:-}"
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
$GPTOKEYB "pyxel" &
pm_platform_helper "$pyxel_dir/bin/pyxel"

source "$pyxel_dir/bin/activate"
export PYTHONHOME="$pyxel_dir"
export PYTHONPYCACHEPREFIX="$GAMEDIR/${runtime}.cache"
export DEVICE_NAME CFW_NAME
export PYXEL_WATCH_STATE_FILE=/dev/null

while true; do
  "$pyxel_dir/bin/pyxel" play "$GAMEDIR/gamedata/$PYXEL_PKG"
  EXIT_CODE=$?
  if [ "$EXIT_CODE" -ne 82 ]; then
    break
  fi
  echo "pyxel.reset() detected. Restarting game cleanly..."
done

if [[ "$PM_CAN_MOUNT" != "N" ]]; then
  $ESUDO umount "$pyxel_dir"
fi

pm_finish
