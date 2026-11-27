from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import fcntl
import os
import subprocess

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "dusk-control"
MODES = ("light", "dark", "auto")


def read_mode():
    try:
        value = (STATE / "appearance").read_text().strip()
        return value if value in MODES else "dark"
    except OSError:
        return "dark"


def resolve(mode, hour):
    return ("light" if 7 <= hour < 19 else "dark") if mode == "auto" else mode


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


def apply(chosen=None):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "appearance.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        mode = chosen or read_mode()
        active = resolve(mode, datetime.now().hour)
        links = [
            (CONFIG / "waybar/appearance.css", f"appearance-{active}.css"),
            (CONFIG / "waybar/control-center/appearance.css", f"appearance-{active}.css"),
            (CONFIG / "swaync/appearance.css", f"appearance-{active}.css"),
            (CONFIG / "kitty/appearance.conf", f"appearance-{active}.conf"),
            (CONFIG / "rofi/appearance.rasi", "appearance-light.rasi" if active == "light" else "dusk.rasi"),
            (CONFIG / "fastfetch/config.jsonc", f"appearance-{active}.jsonc"),
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
        if changes[0]:
            notify("pkill", "-USR2", "-u", str(os.getuid()), "-x", "waybar")
        if changes[2]:
            notify("swaync-client", "--skip-wait", "--reload-css")
        if changes[3]:
            notify("pkill", "-USR1", "-u", str(os.getuid()), "-x", "kitty")
        return mode, active


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--mode", choices=MODES)
    options = parser.parse_args()
    print(*apply(options.mode))
