import fcntl
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys
import tempfile

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
HERE = Path(__file__).resolve().parent
USER = pwd.getpwuid(os.getuid()).pw_name


def notification_count():
    try:
        count = int(subprocess.check_output(
            ["swaync-client", "--skip-wait", "--count"],
            timeout=.8, stderr=subprocess.DEVNULL, text=True,
        ).strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return
    if count > 0:
        print(f"{count} \u6761\u901a\u77e5")


def desktop_wallpaper():
    launcher = CONFIG / "waybar/control-center/wallpaper"
    path = subprocess.check_output([str(launcher), "--print-path"], text=True).rstrip("\n")
    image = Path(path)
    return image if image.is_file() else None


def make_avatar(target):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib

    candidates = (HERE / "avatar.png", Path.home() / ".face",
                  Path.home() / ".face.icon", Path("/var/lib/AccountsService/icons") / USER)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            avatar = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 256, 256, True)
            size = min(avatar.get_width(), avatar.get_height())
            crop = avatar.new_subpixbuf((avatar.get_width() - size) // 2,
                                        (avatar.get_height() - size) // 2, size, size)
            crop.savev(str(target), "png", [], [])
            return
        except GLib.Error:
            continue

    import cairo
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 160, 160)
    canvas = cairo.Context(surface)
    fill = cairo.LinearGradient(0, 0, 160, 160)
    fill.add_color_stop_rgb(0, .48, .42, .73)
    fill.add_color_stop_rgb(1, .24, .26, .45)
    canvas.set_source(fill)
    canvas.paint()
    canvas.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    canvas.set_font_size(64)
    initials = USER[:2].upper()
    bounds = canvas.text_extents(initials)
    canvas.move_to(80 - bounds.width / 2 - bounds.x_bearing,
                   80 - bounds.height / 2 - bounds.y_bearing)
    canvas.set_source_rgb(.98, .96, 1)
    canvas.show_text(initials)
    surface.write_to_png(str(target))


def prepare(directory, wallpaper):
    avatar = directory / "avatar.png"
    make_avatar(avatar)
    image = ""
    if wallpaper:
        linked = directory / ("wallpaper" + wallpaper.suffix)
        linked.symlink_to(wallpaper)
        image = str(linked)
    config = (HERE / "dusk-lock.conf").read_text()
    values = {
        "@WALLPAPER@": image,
        "@AVATAR@": str(avatar),
        "@PLACEHOLDER@": "\u8f93\u5165\u5bc6\u7801\u89e3\u9501",
        "@FAIL@": "\u9a8c\u8bc1\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5",
        "@NOTIFICATIONS@": shlex.join([sys.executable, "-B", str(Path(__file__).resolve()), "--notifications"]),
    }
    for key, value in values.items():
        config = config.replace(key, value)
    path = directory / "hyprlock.conf"
    path.write_text(config)
    return path


def main():
    if sys.argv[1:] == ["--notifications"]:
        notification_count()
        return 0

    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    display = Path(os.environ.get("WAYLAND_DISPLAY", "wayland-0")).name
    with (runtime / f"dusk-lock-{display}.guard").open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        wallpaper = None
        try:
            wallpaper = desktop_wallpaper()
            if shutil.which("hyprlock"):
                with tempfile.TemporaryDirectory(prefix="dusk-lock-", dir=runtime) as temporary:
                    config = prepare(Path(temporary), wallpaper)
                    result = subprocess.run(["hyprlock", "--config", str(config), "--grace", "0"])
                    if result.returncode == 0:
                        return 0
        except (ImportError, OSError, subprocess.SubprocessError) as error:
            print(error, file=sys.stderr)
        fallback = ["swaylock", "--color", "151825"]
        if wallpaper:
            fallback += ["--image", str(wallpaper), "--scaling", "fill"]
        return subprocess.call(fallback)


if __name__ == "__main__":
    raise SystemExit(main())
