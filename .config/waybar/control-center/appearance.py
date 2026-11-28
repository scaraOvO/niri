from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import fcntl
import os
import subprocess
import json
import wallpaper_colors

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "dusk-control"
MODES = ("light", "dark", "auto", "wallpaper", "glass")


def read_mode():
    try:
        value = (STATE / "appearance").read_text().strip()
        return value if value in MODES else "dark"
    except OSError:
        return "dark"


def resolve(mode, hour, brightness=None):
    if mode == "wallpaper" and brightness is not None:
        return "light" if brightness >= .53 else "dark"
    if mode in ("auto", "wallpaper"):
        return "light" if 7 <= hour < 19 else "dark"
    return "light" if mode == "glass" else mode


def palette_options():
    stored = wallpaper_colors.read_json(STATE / "palette-options.json", {})
    source = stored.get("source")
    strength = stored.get("strength")
    return ("wallpaper" if source == "wallpaper" else "dusk",
            strength if strength in wallpaper_colors.STRENGTHS else "balanced")


def current_palette():
    return wallpaper_colors.read_json(STATE / "current-palette.json", {})


def effective():
    return "light" if (CONFIG / "waybar/appearance.css").is_symlink() and (
        CONFIG / "waybar/appearance.css"
    ).readlink().name == "appearance-light.css" else "dark"


def switch(link, target):
    if link.is_symlink() and link.readlink() == Path(target):
        return False
    temporary = link.with_name(link.name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(link)
    return True


def notify(*command):
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def apply(chosen=None, source=None, strength=None):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "appearance.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        mode = chosen or read_mode()
        old_source, old_strength = palette_options()
        source = source or old_source
        strength = strength or old_strength
        color_source = wallpaper_colors.sample(CONFIG, STATE) if source == "wallpaper" or mode == "wallpaper" else None
        active = resolve(mode, datetime.now().hour, color_source["brightness"] if color_source else None)
        palette = wallpaper_colors.palette(color_source, active, strength, .54 if mode == 'glass' else .76) if source == "wallpaper" and color_source else {}
        files = wallpaper_colors.files(CONFIG, palette)
        if mode == "glass":
            wallpaper_colors.glass_surfaces(CONFIG, palette, files)
        written = [wallpaper_colors.save(path, content) for path, content in files.items()]
        changed_palette = any(written)
        wallpaper_colors.save(STATE / "palette-options.json", json.dumps({"source":source,"strength":strength}))
        wallpaper_colors.save(STATE / "current-palette.json", json.dumps(palette))
        fastfetch = f"appearance-{active}.jsonc"
        if palette:
            data = json.loads((CONFIG / "fastfetch" / fastfetch).read_text())
            data["logo"]["color"] = {"1": palette["border"], "2": palette["secondary"]}
            data["display"]["color"] = {"title": palette["border"], "keys": palette["secondary"], "output": palette["ink"]}
            fastfetch = "appearance-wallpaper.jsonc"
            wallpaper_colors.save(CONFIG / "fastfetch" / fastfetch, json.dumps(data, indent=2)+"\n")
        links = [
            (CONFIG / "waybar/appearance.css", f"appearance-{active}.css"),
            (CONFIG / "waybar/control-center/appearance.css", f"appearance-{active}.css"),
            (CONFIG / "swaync/appearance.css", f"appearance-{active}.css"),
            (CONFIG / "kitty/appearance.conf", f"appearance-{active}.conf"),
            (CONFIG / "rofi/appearance.rasi", "appearance-light.rasi" if active == "light" else "dusk.rasi"),
            (CONFIG / "fastfetch/config.jsonc", fastfetch),
        ]
        for link, target in links:
            if not link.with_name(target).is_file():
                raise OSError(f"缺少主题文件：{target}")
        changes = [switch(link, target) for link, target in links]
        if chosen:
            temporary = STATE / "appearance.tmp"
            temporary.write_text(mode + "\n")
            temporary.replace(STATE / "appearance")
        if chosen or any(changes):
            notify("gsettings", "set", "org.gnome.desktop.interface", "color-scheme", f"prefer-{active}")
        if changes[0] or changed_palette:
            notify("pkill", "-USR2", "-u", str(os.getuid()), "-x", "waybar")
        if changes[2] or changed_palette:
            notify("swaync-client", "--skip-wait", "--reload-css")
        if changes[3] or changed_palette:
            notify("pkill", "-USR1", "-u", str(os.getuid()), "-x", "kitty")
        return mode, active


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--source", choices=("dusk", "wallpaper"))
    parser.add_argument("--strength", choices=wallpaper_colors.STRENGTHS)
    options = parser.parse_args()
    print(*apply(options.mode, options.source, options.strength))
