from argparse import ArgumentParser
import fcntl
import json
from pathlib import Path
import subprocess

from appearance import CONFIG, STATE
from wallpaper_colors import read_json, save

SCENE = STATE / "scene.json"
RULES = CONFIG / "niri/scene-active.kdl"
PLACEMENT = CONFIG / "niri/placement-active.kdl"
WIDGETS = Path(__file__).with_name("desktop_widgets.py")
MODES = {"focus": .94, "presentation": 1.0}


def scene():
    return read_json(SCENE, {}).get("mode", "normal")


def call(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=5).stdout.strip()


def apply_rules(mode):
    if mode == "normal":
        RULES.unlink(missing_ok=True)
    else:
        opacity = MODES[mode]
        save(RULES, rf'''window-rule {{
    match app-id=r#"^(firefox|org\.mozilla\.firefox|code|Code|code-oss|com\.visualstudio\.code)$"#
    opacity {opacity}
}}
''')
    call("niri", "msg", "action", "load-config-file")


def set_desktop(dnd, widgets):
    if dnd != (call("swaync-client", "--get-dnd") == "true"):
        call("swaync-client", "--dnd-on" if dnd else "--dnd-off")
    call("python3", "-B", str(WIDGETS), "restore" if widgets else "hide")


def set_scene(mode):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "scene.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read_json(SCENE, {})
        previous = state.get("mode", "normal")
        if previous == mode:
            return mode
        if not state:
            layers = json.loads(call("niri", "msg", "--json", "layers"))
            state = {
                "dnd": call("swaync-client", "--get-dnd") == "true",
                "widgets": any(layer["namespace"].startswith("dusk-desktop-widget-") for layer in layers),
            }
        try:
            apply_rules(mode)
            if mode == "normal":
                set_desktop(state["dnd"], state["widgets"])
                SCENE.unlink(missing_ok=True)
            else:
                set_desktop(True, False)
                save(SCENE, json.dumps({**state, "mode": mode}))
        except (OSError, subprocess.SubprocessError):
            apply_rules(previous)
            set_desktop(state["dnd"], state["widgets"]) if previous == "normal" else set_desktop(True, False)
            raise
        return mode


def set_placement(enabled):
    if enabled:
        save(PLACEMENT, 'include "window-placement.kdl"\n')
    else:
        PLACEMENT.unlink(missing_ok=True)
    call("niri", "msg", "action", "load-config-file")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("normal", *MODES, "placement-on", "placement-off", "sync"))
    action = parser.parse_args().action
    try:
        if action.startswith("placement-"):
            set_placement(action == "placement-on")
        elif action == "sync":
            mode = scene()
            if mode in MODES:
                apply_rules(mode)
                set_desktop(True, False)
        else:
            set_scene(action)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
