from collections import defaultdict
from colorsys import rgb_to_hls, hls_to_rgb
from math import sqrt
from pathlib import Path
import json

STRENGTHS = {"soft": .48, "balanced": .83, "vivid": 1.15}


def read_json(path, default):
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def save(path, content):
    try:
        if path.read_text() == content:
            return False
    except OSError:
        pass
    temp = path.with_name(path.name + ".next")
    temp.write_text(content)
    temp.replace(path)
    return True


def sample(config, state):
    image = config / "waybar/control-center/wallpaper.png"
    if not image.is_file():
        image = config / "niri/system-wallpaper.png"
    if not image.is_file():
        image = config / "niri/system-wallpaper.jpg"
    if not image.is_file():
        image = config / "niri/wanderer_coffee.jpg"
    try:
        stat = image.stat()
        key = [str(image), stat.st_size, stat.st_mtime_ns]
    except OSError:
        return None
    stored = state / "wallpaper-source.json"
    previous = read_json(stored, {})
    if previous.get("key") == key:
        return previous
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib
    try:
        pixels = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(image), 100, 100, True)
    except GLib.Error:
        return None
    samples = pixels.get_pixels()
    width, height = pixels.get_width(), pixels.get_height()
    stride, channels = pixels.get_rowstride(), pixels.get_n_channels()
    votes = defaultdict(float)
    luminances = []
    for y in range(height):
        for x in range(width):
            offset = y * stride + x * channels
            r, g, b = (value / 255 for value in samples[offset:offset + 3])
            if channels == 4 and samples[offset + 3] < 200:
                continue
            luminances.append(.2126 * r + .7152 * g + .0722 * b)
            hue, light, saturation = rgb_to_hls(r, g, b)
            if saturation < .14 or not .14 < light < .88:
                continue
            index = round(hue * 36) % 36
            weight = sqrt(saturation) * (1 - abs(light-.53))
            for shift, factor in ((-1, .30), (0, 1), (1, .30)):
                votes[(index+shift)%36] += weight * factor
    primary = max(votes, key=votes.get) if votes else 30
    options = {slot: value for slot, value in votes.items() if min((slot-primary)%36, (primary-slot)%36) >= 4}
    secondary = max(options, key=options.get) if options else (primary + 5) % 36
    values = sorted(luminances)
    brightness = values[len(values)//2] if values else .5
    answer = {"key":key, "primary":primary/36, "secondary":secondary/36, "brightness":brightness}
    save(stored, json.dumps(answer))
    return answer


def palette(source, mode, strength):
    ink_hue = source["primary"]
    second_hue = source["secondary"]
    amount = STRENGTHS[strength]

    def color(hue, lightness, saturation):
        rgb = hls_to_rgb(hue, lightness, min(.83, saturation*amount))
        return "#" + "".join(f"{round(channel*255):02x}" for channel in rgb)

    if mode == "light":
        recipes = {
            "surface":(.95,.43), "panel":(.89,.36), "ink":(.16,.31), "muted":(.32,.29),
            "edge":(.64,.34), "accent":(.77,.63), "on_accent":(.15,.40), "hover":(.84,.58),
            "secondary":(.35,.43), "terminal":(.94,.32), "border":(.46,.59),
        }
    else:
        recipes = {
            "surface":(.17,.32), "panel":(.24,.42), "ink":(.95,.32), "muted":(.78,.30),
            "edge":(.49,.30), "accent":(.75,.66), "on_accent":(.15,.42), "hover":(.83,.54),
            "secondary":(.82,.44), "terminal":(.14,.33), "border":(.68,.64),
        }
    return {name:color(second_hue if name in {"panel","secondary"} else ink_hue, *values)
            for name, values in recipes.items()}


def css_colors(p):
    return "".join(f"@define-color wp_{name} {value};\n" for name,value in p.items())


WAYBAR = """
window#waybar, #workspaces button, #window, #custom-island, #network, #pulseaudio,
#custom-notifications, #mpris.media-title, #mpris.media-prev, #mpris.media-next, tooltip label { color: @wp_ink; }
#workspaces, #window, #custom-island, #network, #pulseaudio,
#custom-notifications, #tray, #custom-control-center, #media:not(.empty), tooltip {
  background-color: alpha(@wp_surface, .95); border-color: alpha(@wp_edge, .56);
}
#workspaces button:hover, #mpris.media-prev:hover, #mpris.media-next:hover { background-color: @wp_panel; }
#workspaces button.active, #custom-control-center, #mpris.media-toggle {
  background: @wp_accent; color: @wp_on_accent;
}
#custom-control-center:hover, #mpris.media-toggle:hover { background: @wp_hover; }
window#waybar.empty #window { background: transparent; border-color: transparent; }
"""
PANEL = """
#dusk-control { color: @wp_ink; }
#dusk-control #frame { background: alpha(@wp_surface, .76); border-color: alpha(@wp_edge, .62); }
#dusk-control .muted, #dusk-control .temperature, #dusk-control .sun-symbol { color: @wp_secondary; }
#dusk-control button, #dusk-control entry {
  background-color: @wp_panel; color: @wp_ink; border-color: transparent;
}
#dusk-control button:hover, #dusk-control button:active { background-color: alpha(@wp_accent, .35); }
#dusk-control #sidebar button { background: transparent; color: @wp_ink; }
#dusk-control #sidebar button.selected { border-left-color: @wp_border; color: @wp_secondary; }
#dusk-control button.primary-action, #dusk-control button.play,
#dusk-control button.weather-search-toggle:checked { background: @wp_accent; color: @wp_on_accent; }
#dusk-control button.primary-action:hover, #dusk-control button.play:hover { background: @wp_hover; }
#dusk-control .slider-card { background-color: alpha(@wp_panel, .80); }
#dusk-control .slider-label { color: @wp_ink; }
#dusk-control .slider-value { color: @wp_secondary; background-color: alpha(@wp_surface, .70); }
#dusk-control .weather-hero, #dusk-control .forecast, #dusk-control .weather-metric,
#dusk-control .weather-map, #dusk-control .weather-map button { background: transparent; }
#dusk-control .weather-map button label { color: @wp_secondary; }
"""
SWAYNC = """
.control-center { background: alpha(@wp_surface, .93); color: @wp_ink; border-color: @wp_edge; }
.notification-row .notification-background .notification,
.control-center .control-center-list .notification-row .notification-background .notification {
  background: @wp_surface; color: @wp_ink; border-color: alpha(@wp_edge, .65);
}
.notification-row .notification-background .notification .notification-default-action,
.control-center .control-center-list .notification-row .notification-background .notification .notification-default-action,
.notification-row .notification-background .notification .notification-default-action .notification-content .summary,
.notification-content .summary { color: @wp_ink; }
.notification-row .notification-background .notification .notification-default-action .notification-content .body,
.notification-content .body { color: @wp_muted; }
.widget-title > label { color: @wp_secondary; }
.widget-title > button, .widget-dnd { background: @wp_panel; color: @wp_ink; }
.control-center .control-center-list .notification-group.collapsed .notification-row:not(:last-child) .notification-background .notification {
  background: transparent; border-color: transparent;
}
"""
ISLAND = """
#dusk-island.light, #dusk-island.dark { color: @wp_ink; }
#dusk-island.light #island-frame, #dusk-island.dark #island-frame {
  background: alpha(@wp_surface, .93); border-color: @wp_edge;
}
#dusk-island.light .heading, #dusk-island.dark .heading { color: @wp_secondary; }
#dusk-island.light .footnote, #dusk-island.dark .footnote,
#dusk-island.light .detail, #dusk-island.dark .detail { color: @wp_muted; }
#dusk-island.light progressbar trough, #dusk-island.dark progressbar trough { background: @wp_panel; }
#dusk-island.light progressbar progress, #dusk-island.dark progressbar progress { background: @wp_border; }
"""


def rgba(hex_color, opacity):
    rgb = [int(hex_color[offset:offset+2], 16) for offset in (1,3,5)]
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {opacity})"


def files(config, p):
    result = {config / path: "" for path in (
        "waybar/wallpaper-palette.css", "waybar/control-center/wallpaper-palette.css",
        "waybar/control-center/island-wallpaper.css", "swaync/wallpaper-palette.css",
        "rofi/wallpaper-palette.rasi", "kitty/wallpaper-palette.conf", "niri/wallpaper-palette.kdl",
    )}
    if not p:
        return result
    for path, content in (("waybar/wallpaper-palette.css",WAYBAR),("waybar/control-center/wallpaper-palette.css",PANEL),
                          ("waybar/control-center/island-wallpaper.css",ISLAND),("swaync/wallpaper-palette.css",SWAYNC)):
        result[config/path] = css_colors(p) + content
    result[config/"rofi/wallpaper-palette.rasi"] = (
        "* {\n"
        f"    surface: {rgba(p['surface'], .85)};\n"
        f"    foreground: {p['ink']};\n    muted: {p['muted']};\n"
        f"    outline: {rgba(p['edge'], .42)};\n"
        f"    selection: {p['accent']};\n    selected-text: {p['on_accent']};\n"
        "}\n"
    )
    result[config/"kitty/wallpaper-palette.conf"] = (
        f"background {p['terminal']}\nforeground {p['ink']}\ncursor {p['border']}\n"
        f"selection_background {p['accent']}\nselection_foreground {p['on_accent']}\n"
        f"active_border_color {p['border']}\n"
    )
    result[config/"niri/wallpaper-palette.kdl"] = (
        "layout {\n    focus-ring {\n"
        f'        active-gradient from="{p["border"]}" to="{p["secondary"]}" angle=45\n'
        f'        active-color "{p["border"]}"\n'
        "    }\n}\n"
    )
    return result
