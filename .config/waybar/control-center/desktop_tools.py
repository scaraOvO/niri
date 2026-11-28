from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "dusk-desktop"
LAUNCH = CONFIG / "rofi/launch"
SCRATCH = "dusk-scratchpad"


def niri(*args):
    return subprocess.check_output(["niri", "msg", *map(str, args)], text=True, timeout=3)


def query(name):
    return json.loads(niri("--json", name))


@contextmanager
def locked(name):
    with (Path(os.environ["XDG_RUNTIME_DIR"]) / f"dusk-{name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def pick(prompt, rows=(), *, edit=False, timeout=None):
    placeholder = json.dumps(prompt, ensure_ascii=False)
    command = [str(LAUNCH), "-dmenu", "-i", "-no-show-icons", "-p", "",
               "-theme-str", f"entry {{ placeholder: {placeholder}; }}"]
    if edit:
        command += ["-format", "s"]
    else:
        command += ["-no-custom", "-display-columns", "2"]
    try:
        result = subprocess.run(command, input="\n".join(rows), text=True,
                                stdout=subprocess.PIPE, timeout=timeout,
                                env={**os.environ, "DUSK_ROFI_ACTIONS": "1"})
    except subprocess.TimeoutExpired:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def clean(value):
    return " ".join((value or "").split())


def window_label(window):
    app, title = (clean(window.get(key)) for key in ("app_id", "title"))
    return " · ".join(dict.fromkeys(filter(None, (app, title)))) or "未命名窗口"


def window_search():
    spaces = {w["id"]: w for w in query("workspaces")}
    windows = sorted(query("windows"), key=lambda w: not w["is_focused"])
    rows = []
    for window in windows:
        space = spaces.get(window["workspace_id"], {})
        name = clean(space.get("name")) or str(space.get("idx", "?"))
        output = clean(space.get("output"))
        rows.append(f"{window['id']}\t{window_label(window)}    —    {name} {output}")
    if rows:
        selected = pick("搜索窗口", rows).split("\t", 1)[0]
        if selected.isdecimal() and any(w["id"] == int(selected) for w in query("windows")):
            niri("action", "focus-window", "--id", selected)


def scratch_window():
    return next((window for window in query("windows") if window["app_id"] == SCRATCH), None)


def hide_scratchpad(window_id):
    niri("action", "move-floating-window", "--id", window_id, "--y", "-900")
    time.sleep(.24)
    niri("action", "close-window", "--id", window_id)
    for _ in range(20):
        window = scratch_window()
        if not window or window["id"] != window_id:
            return
        time.sleep(.05)


def watch_scratchpad(window_id):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

    def dismiss(*_):
        try:
            with locked("scratchpad"):
                window = scratch_window()
                if window and window["id"] == window_id:
                    for surface in surfaces:
                        surface.hide()
                    hide_scratchpad(window_id)
        except BlockingIOError:
            return False
        Gtk.main_quit()
        return True

    def check_focus():
        try:
            window = scratch_window()
            if not window or window["id"] != window_id:
                Gtk.main_quit()
                return False
            if not window["is_focused"] and dismiss():
                return False
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return True

    display = Gdk.Display.get_default()
    surfaces = []
    provider = Gtk.CssProvider()
    provider.load_from_data(b"#dusk-scratch-dismiss { background: transparent; }")
    for index in range(display.get_n_monitors()):
        surface = Gtk.Window(name="dusk-scratch-dismiss")
        surface.set_decorated(False)
        surface.set_accept_focus(False)
        surface.set_app_paintable(True)
        surface.set_visual(surface.get_screen().get_rgba_visual())
        surface.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        GtkLayerShell.init_for_window(surface)
        GtkLayerShell.set_namespace(surface, "dusk-scratch-dismiss")
        GtkLayerShell.set_layer(surface, GtkLayerShell.Layer.BOTTOM)
        GtkLayerShell.set_monitor(surface, display.get_monitor(index))
        GtkLayerShell.set_exclusive_zone(surface, -1)
        GtkLayerShell.set_keyboard_mode(surface, GtkLayerShell.KeyboardMode.NONE)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(surface, edge, True)
        surface.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        surface.connect("button-press-event", dismiss)
        surface.show()
        surfaces.append(surface)
    GLib.timeout_add(140, check_focus)
    Gtk.main()


def scratchpad():
    with locked("scratchpad"):
        window = scratch_window()
        if window:
            hide_scratchpad(window["id"])
            return
        command = ["kitty", "-o", "confirm_os_window_close=0", "--class", SCRATCH,
                   "--title", "Scratchpad", "tmux", "new-session", "-A", "-s", "dusk-scratch"]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline:
            window = scratch_window()
            if window and window["is_floating"]:
                window_id = window["id"]
                niri("action", "move-floating-window", "--id", window_id, "--y", "12")
                if not window["is_focused"]:
                    niri("action", "focus-window", "--id", window_id)
                break
            if process.poll() is not None:
                raise ValueError("\u4e34\u65f6\u7ec8\u7aef\u542f\u52a8\u5931\u8d25")
            time.sleep(.08)
        else:
            process.terminate()
            raise ValueError("\u4e34\u65f6\u7ec8\u7aef\u542f\u52a8\u8d85\u65f6")
    watch_scratchpad(window_id)


def output_snapshot():
    snapshot = {}
    for name, output in query("outputs").items():
        logical = output["logical"]
        if logical is None or output["current_mode"] is None:
            snapshot[name] = None
            continue
        mode = output["modes"][output["current_mode"]]
        snapshot[name] = {
            "mode": f"{mode['width']}x{mode['height']}@{mode['refresh_rate']/1000:.3f}",
            "custom": output["is_custom_mode"], "scale": logical["scale"],
            "transform": logical["transform"], "x": logical["x"], "y": logical["y"],
        }
    return snapshot


TRANSFORMS = {"Normal": "normal", "90": "90", "180": "180", "270": "270",
              "Flipped": "flipped", "Flipped90": "flipped-90",
              "Flipped180": "flipped-180", "Flipped270": "flipped-270"}


def apply_outputs(preset, current):
    matched = {name: value for name, value in preset.items() if name in current}
    if not any(matched.values()):
        raise ValueError("此预设没有可用的显示器")
    for name, value in matched.items():
        if value is None:
            continue
        previous = current[name] or {}
        if not previous:
            niri("output", name, "on")
        if any(previous.get(key) != value[key] for key in ("mode", "custom")):
            niri("output", name, "custom-mode" if value["custom"] else "mode", value["mode"])
        if previous.get("transform") != value["transform"]:
            niri("output", name, "transform", TRANSFORMS[value["transform"]])
        if previous.get("scale") != value["scale"]:
            niri("output", name, "scale", value["scale"])
        if any(previous.get(key) != value[key] for key in ("x", "y")):
            niri("output", name, "position", "set", "--", value["x"], value["y"])
    active = output_snapshot()
    if any(value is not None and active.get(name) != value for name, value in matched.items()):
        raise ValueError("显示器未能应用预设参数")
    for name, value in matched.items():
        if value is None and current[name] is not None:
            niri("output", name, "off")


def confirm_outputs(preset):
    before = output_snapshot()
    confirmed = False
    try:
        apply_outputs(preset, before)
        selected = pick("保留新设置？15 秒后自动恢复",
                        ["revert\t恢复原设置", "keep\t保留新设置"],
                        timeout=15)
        confirmed = selected.startswith("keep\t")
    finally:
        if not confirmed:
            apply_outputs(before, output_snapshot())


def save_presets(path, presets):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(presets, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def display_presets():
    with locked("display-presets"):
        path = STATE / "display-presets.json"
        presets = json.loads(path.read_text()) if path.exists() else {}
        rows = ["save\t保存当前显示设置",
                "delete\t删除预设"] if presets else [
                    "save\t保存当前显示设置"]
        choices = list(presets)
        rows = [f"{idx}\t应用：{name}" for idx, name in enumerate(choices)] + rows
        action = pick("显示器预设", rows).split("\t", 1)[0]
        if action == "save":
            name = clean(pick("预设名称", ["单屏", "双屏", "投影"], edit=True))
            if name and (name not in presets or pick("覆盖预设？",
                                                     ["yes\t覆盖"]).startswith("yes\t")):
                presets[name] = output_snapshot()
                save_presets(path, presets)
        elif action == "delete":
            choice = pick("选择要删除的预设",
                          [f"{idx}\t{name}" for idx, name in enumerate(choices)]).split("\t", 1)[0]
            if choice.isdecimal() and int(choice) < len(choices):
                del presets[choices[int(choice)]]
                save_presets(path, presets)
        elif action.isdecimal() and int(action) < len(choices):
            confirm_outputs(presets[choices[int(action)]])


def active_casts():
    try:
        return [cast for cast in query("casts") if cast["is_active"]]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def cast_details(casts):
    windows = {window["id"]: window for window in query("windows")} if any(
        "Window" in cast["target"] for cast in casts) else {}
    details = []
    for cast in casts:
        target = cast["target"]
        if "Output" in target:
            name = target["Output"]["name"]
            label = f"屏幕 · {name}"
        elif "Window" in target:
            window_id = target["Window"]["id"]
            label = f"窗口 · {window_label(windows.get(window_id, {}))}"
        else:
            label = "目标切换中"
        details.append((label, cast["kind"]))
    return tuple(details)


if __name__ == "__main__":
    actions = {"scratchpad": scratchpad, "windows": window_search, "displays": display_presets}
    try:
        actions[sys.argv[1]]()
    except BlockingIOError:
        pass
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        subprocess.run(["notify-send", "桌面工具", str(error)], check=False)
        raise SystemExit(1)
