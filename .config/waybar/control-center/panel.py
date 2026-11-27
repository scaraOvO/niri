from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from math import asinh, cos, exp, floor, pi, radians, sin, tan
from pathlib import Path
import json
import os
import re
import subprocess
import time
from urllib.parse import urlencode
import appearance
from urllib.request import Request, urlopen

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkLayerShell, Pango

HERE = Path(__file__).resolve().parent
CITY_FILE = Path(GLib.get_user_state_dir()) / "dusk-control" / "weather-city"
PLAYER = ["playerctl", "--player=playerctld,%any"]


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=4)


def text(*args):
    return run(*args).stdout.strip()


def spawn(*args):
    return subprocess.Popen(args, start_new_session=True)


def label(value="", style=None):
    widget = Gtk.Label(label=value, xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def button(title, callback):
    widget = Gtk.Button(label=title)
    widget.connect("clicked", lambda *_: callback())
    return widget


def row(*widgets):
    box = Gtk.Box(spacing=9)
    for widget in widgets:
        box.pack_start(widget, False, False, 0)
    return box


def weather_condition(code):
    if code == 0:
        return "☀", "晴"
    if code <= 3:
        return "☁", "多云"
    if code <= 48:
        return "≋", "雾"
    if code in (71, 73, 75, 77, 85, 86):
        return "❄", "雪"
    if code < 95:
        return "☂", "雨"
    return "ϟ", "雷暴"


def weather(city):
    def query(endpoint, **params):
        with urlopen(endpoint + "?" + urlencode(params), timeout=7) as response:
            return json.load(response)

    result = query("https://geocoding-api.open-meteo.com/v1/search", name=city, count=1, language="zh")
    places = result.get("results") or []
    if not places:
        raise ValueError("未找到城市，试试中英文全名。")
    place = places[0]
    result = query(
        "https://api.open-meteo.com/v1/forecast",
        latitude=place["latitude"], longitude=place["longitude"],
        current="temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,surface_pressure",
        daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max,sunrise,sunset",
        forecast_days=5, timezone="auto",
    )
    return place, result["current"], result["daily"]


def map_tiles(latitude, longitude, width=300, height=210, zoom=10):
    size = 2 ** zoom
    latitude = max(-85.05, min(85.05, latitude))
    x = (longitude + 180) / 360 * size * 256
    y = (1 - asinh(tan(radians(latitude))) / pi) / 2 * size * 256
    left, top = round(x - width / 2), round(y - height / 2)
    cache = Path(GLib.get_user_cache_dir()) / "dusk-control" / "map" / str(zoom)
    cache.mkdir(parents=True, exist_ok=True)
    result = []
    for tile_y in range(floor(top / 256), floor((top + height - 1) / 256) + 1):
        if not 0 <= tile_y < size:
            continue
        for tile_x in range(floor(left / 256), floor((left + width - 1) / 256) + 1):
            wrapped_x = tile_x % size
            file = cache / f"{wrapped_x}-{tile_y}.png"
            if file.exists() and time.time() - file.stat().st_mtime < 7 * 86400:
                data = file.read_bytes()
            else:
                request = Request(
                    f"https://tile.openstreetmap.org/{zoom}/{wrapped_x}/{tile_y}.png",
                    headers={"User-Agent": "ScaraOvO-DuskControl/1.0 (+https://github.com/scaraOvO/niri)"},
                )
                with urlopen(request, timeout=4) as response:
                    data = response.read(1_000_000)
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("地图图块格式不正确")
                temporary = file.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(file)
            result.append((tile_x * 256 - left, tile_y * 256 - top, data))
    return result


class ExpressiveTrack(Gtk.Overlay):
    def __init__(self, name, color):
        super().__init__()
        self.color = color
        self.position = 0
        self.emphasis = 0
        self.pressed = False
        self.ticking = False
        self.previous_frame = None
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(-1, 40)
        self.canvas.connect("draw", self.draw_track)
        self.add(self.canvas)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_opacity(0)
        self.scale.get_accessible().set_name(name)
        self.add_overlay(self.scale)
        self.scale.connect("value-changed", self.queue_motion)
        self.scale.connect("button-press-event", self.press, True)
        self.scale.connect("button-release-event", self.press, False)
        self.scale.connect("grab-broken-event", self.press, False)
        self.scale.connect("notify::has-focus", lambda *_: self.canvas.queue_draw())
        self.connect("state-flags-changed", lambda *_: self.canvas.queue_draw())

    def press(self, _scale, _event, pressed):
        self.pressed = pressed
        self.queue_motion()
        return False

    def queue_motion(self, *_):
        if not self.get_settings().get_property("gtk-enable-animations"):
            self.position = self.scale.get_value() / 100
            self.emphasis = float(self.pressed)
            self.canvas.queue_draw()
            return
        if not self.ticking:
            self.ticking = True
            self.add_tick_callback(self.frame)

    def frame(self, _widget, clock):
        time = clock.get_frame_time()
        elapsed = min(0.04, (time - self.previous_frame) / 1e6) if self.previous_frame else 1 / 60
        self.previous_frame = time
        target = self.scale.get_value() / 100
        pressed = float(self.pressed)
        self.position += (target - self.position) * (1 - exp(-elapsed * (38 if self.pressed else 22)))
        self.emphasis += (pressed - self.emphasis) * (1 - exp(-elapsed * 26))
        settled = abs(self.position-target) < .001 and abs(self.emphasis-pressed) < .006
        if settled:
            self.position, self.emphasis = target, pressed
            self.ticking = False
            self.previous_frame = None
        self.canvas.queue_draw()
        return not settled

    def draw_track(self, widget, cr):
        width = widget.get_allocated_width()
        y = widget.get_allocated_height() / 2
        x = 10 + max(0, width-20) * self.position
        alpha = 1 if self.is_sensitive() else .40
        light = not self.get_settings().get_property("gtk-application-prefer-dark-theme")
        dynamic = getattr(self, "wallpaper_color", None)
        accent = dynamic or (tuple(component * .69 for component in self.color) if light else self.color)
        handle = 2.6 + self.emphasis * 1.4
        height = 20 + self.emphasis * 2
        gap = handle + 6

        def pill(left, right, center, size, rgb, opacity):
            if right <= left:
                return
            stroke = min(size, right-left)
            cr.set_line_cap(1)
            cr.set_line_width(stroke)
            cr.set_source_rgba(*rgb, opacity)
            cr.move_to(left + stroke / 2, center)
            cr.line_to(right - stroke / 2 + .01, center)
            cr.stroke()

        pill(1, x-gap, y, height, accent, alpha)
        pill(x+gap, width-1, y, height, (.75, .64, .77) if light else (.33, .27, .41), alpha)
        if x < width - 26:
            pill(width-13, width-9, y, 4, accent, .7*alpha)
        if self.scale.has_focus():
            pill(x-handle-3, x+handle+3, y, 40, accent, .26*alpha)
        # 用直线描边绘制竖直圆头滑块。
        cr.set_source_rgba(*accent, alpha)
        cr.set_line_width(2*handle)
        cr.set_line_cap(1)
        half = 13 + 2*self.emphasis
        cr.move_to(x, y-half)
        cr.line_to(x, y+half)
        cr.stroke()
        return False


class ControlCenter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.scaraovo.DuskControl", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.pool = ThreadPoolExecutor(max_workers=2)

    def do_activate(self):
        if self.window is not None:
            self.close_panel()
            return
        self.closing = False
        self.build()
        self.window.show_all()
        GLib.idle_add(self.reveal_panel)
        self.refresh()
        self.timer = GLib.timeout_add_seconds(2, self.refresh)

    def reveal_panel(self):
        if not self.closing:
            outer = self.panel_revealer.get_child()
            target = max(590, outer.get_preferred_height_for_width(860)[1])
            self.panel_revealer.set_reveal_child(True)
            self.animate_panel_height(target, 275)
        return False

    def close_panel(self):
        if self.closing:
            return
        self.closing = True
        self.panel_revealer.set_reveal_child(False)
        self.animate_panel_height(1, 245)

    def animate_panel_height(self, target, duration):
        if getattr(self, "panel_tick", None):
            self.window.remove_tick_callback(self.panel_tick)
        start = self.window.get_size()[1]
        began = GLib.get_monotonic_time()
        if not self.window.get_settings().get_property("gtk-enable-animations"):
            self.panel_revealer.set_size_request(860, target)
            if self.closing:
                self.destroy_panel()
            return

        def frame(_widget, _clock):
            progress = min(1, (GLib.get_monotonic_time() - began) / (duration * 1000))
            eased = 1 - (1 - progress) ** 3
            height = round(start + (target - start) * eased)
            self.panel_revealer.set_size_request(860, max(1, height))
            if progress >= 1:
                self.panel_tick = None
                if self.closing:
                    self.destroy_panel()
                return False
            return True

        self.panel_tick = self.window.add_tick_callback(frame)

    def destroy_panel(self):
        if self.window is not None:
            self.window.destroy()
        return False

    def build(self):
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_decorated(False)
        self.window.set_default_size(860, -1)
        self.window.set_resizable(True)
        self.window.set_app_paintable(True)
        self.window.set_visual(self.window.get_screen().get_rgba_visual())
        self.window.set_name("dusk-control")
        self.window.connect("key-press-event", self.keypress)
        self.window.connect("destroy", self.closed)
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, "dusk-control")
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.ON_DEMAND)
        for edge, margin in ((GtkLayerShell.Edge.TOP, 8), (GtkLayerShell.Edge.RIGHT, 14)):
            GtkLayerShell.set_anchor(self.window, edge, True)
            GtkLayerShell.set_margin(self.window, edge, margin)
        GtkLayerShell.set_exclusive_zone(self.window, 0)
        self.css = Gtk.CssProvider()
        self.active_theme = None
        self.reload_appearance()
        Gtk.StyleContext.add_provider_for_screen(
            self.window.get_screen(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=19)
        outer.set_name("frame")
        outer.set_size_request(-1, 590)
        self.panel_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, transition_duration=275
        )
        self.panel_revealer.set_size_request(860, 1)
        self.panel_revealer.add(outer)
        self.window.add(self.panel_revealer)
        body = Gtk.Box(spacing=20)
        outer.pack_start(body, True, True, 0)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.set_name("sidebar")
        body.pack_start(sidebar, False, False, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE, transition_duration=310)
        body.pack_start(self.stack, True, True, 0)
        self.tabs = {}
        for ident, glyph, title, make in (
            ("media", "\uf001", "媒体", self.media_page),
            ("sound", "\uf028", "音量", self.audio_page),
            ("display", "\uf108", "显示", self.display_page),
            ("wifi", "\uf1eb", "网络", self.network_page),
            ("bluetooth", "\uf294", "蓝牙", self.bluetooth_page),
            ("weather", "\uf0c2", "天气", self.weather_page),
            ("wallpaper", "\uf03e", "壁纸", self.wallpaper_page),
            ("appearance", "\uf1fc", "外观", self.appearance_page),
        ):
            tab = button(f"{glyph}  {title}", lambda name=ident: self.select(name))
            sidebar.pack_start(tab, False, False, 0)
            self.tabs[ident] = tab
            self.stack.add_named(make(), ident)
        self.select("media")

    def keypress(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close_panel()
            return True
        return False

    def closed(self, _window):
        self.window = None
        if hasattr(self, "timer"):
            GLib.source_remove(self.timer)
        for source in self.slider_writes.values():
            GLib.source_remove(source)
        self.slider_writes.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def select(self, ident):
        previous = self.stack.get_visible_child_name()
        if previous == ident and any(tab.get_style_context().has_class("selected") for tab in self.tabs.values()):
            return
        names = list(self.tabs)
        if previous in names:
            direction = Gtk.StackTransitionType.OVER_UP if names.index(ident) > names.index(previous) else Gtk.StackTransitionType.UNDER_DOWN
            self.stack.set_transition_type(direction)
        self.stack.set_visible_child_name(ident)
        for name, tab in self.tabs.items():
            style = tab.get_style_context()
            style.add_class("selected") if name == ident else style.remove_class("selected")
        if ident == "weather":
            self.restore_weather()
        if ident == "wallpaper":
            self.refresh_gallery()
        if hasattr(self, "track"):
            self.refresh()

    def page(self, detail=None):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.get_style_context().add_class("page")
        if detail:
            page.pack_start(label(detail, "muted"), False, False, 0)
        return page

    def put(self, page, *widgets):
        for widget in widgets:
            page.pack_start(widget, False, False, 0)

    def media_page(self):
        page = self.page()
        self.track = label("", "track")
        self.artist = label("", "muted")
        self.play = button("\uf04b", lambda: self.command(*PLAYER, "play-pause"))
        self.play.get_style_context().add_class("play")
        self.play.get_style_context().add_class("icon-action")
        self.previous = button("\uf048", lambda: self.command(*PLAYER, "previous"))
        self.next = button("\uf051", lambda: self.command(*PLAYER, "next"))
        for control in (self.previous, self.next):
            control.get_style_context().add_class("icon-action")
        self.previous.set_tooltip_text("上一首")
        self.next.set_tooltip_text("下一首")
        self.play.set_tooltip_text("播放或暂停")
        self.put(page, self.track, self.artist, row(self.previous, self.play, self.next))
        return page

    def audio_page(self):
        page = self.page()
        self.sliders = {}
        self.slider_writes = {}
        self.slider(page, "output", "扬声器", "\uf028")
        self.slider(page, "input", "麦克风", "\uf130")
        self.slider(page, "brightness", "屏幕亮度", "\uf185")
        self.put(page, row(
            button("切换扬声器静音", lambda: self.command("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle")),
            button("详细设置", lambda: self.open("pavucontrol")),
        ))
        return page

    def slider(self, page, key, title, glyph):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.get_style_context().add_class("slider-card")
        header = Gtk.Box(spacing=8)
        header.pack_start(label(f"{glyph}  {title}", "slider-label"), True, True, 0)
        value = label("—", "slider-value")
        header.pack_end(value, False, False, 0)
        colors = {"output": (.97, .75, .64), "input": (.83, .74, .97), "brightness": (.96, .84, .60)}
        control = ExpressiveTrack(title, colors[key])
        handler = control.scale.connect("value-changed", self.change_slider, key)
        self.sliders[key] = (control, handler, value)
        palette = appearance.current_palette()
        accent = palette.get("border" if key == "output" else "secondary" if key == "input" else "edge")
        control.wallpaper_color = tuple(int(accent[i:i+2],16)/255 for i in (1,3,5)) if accent else None
        self.put(card, header, control)
        self.put(page, card)

    def display_page(self):
        page = self.page("查看当前输出，也可打开显示设置调整分辨率、缩放和布局。")
        self.outputs = label()
        self.put(page, self.outputs, button("打开显示设置", lambda: self.open("wdisplays")))
        return page

    def network_page(self):
        page = self.page("管理 Wi‑Fi 开关、可用网络和已有连接。")
        self.network = label()
        self.wifi = button("切换 Wi‑Fi", self.toggle_wifi)
        self.wifi.set_sensitive(False)
        self.put(page, self.network, row(self.wifi, button("连接设置", lambda: self.open("nm-connection-editor"))))
        return page

    def bluetooth_page(self):
        page = self.page("查看适配器状态，打开设备管理器可搜索和配对。")
        self.bluetooth = label()
        self.bluetooth_toggle = button("切换蓝牙", self.toggle_bluetooth)
        self.put(page, self.bluetooth, row(self.bluetooth_toggle, button("管理设备", lambda: self.open("blueman-manager"))))
        return page

    def weather_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.get_style_context().add_class("page")
        header = Gtk.Box(spacing=8)
        self.city = Gtk.Entry(placeholder_text="搜索城市")
        self.city.set_max_length(80)
        self.city.set_width_chars(16)
        self.city.connect("activate", lambda *_: self.query_weather())
        self.weather_button = button("查询", self.query_weather)
        self.weather_button.get_style_context().add_class("primary-action")
        self.weather_search = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
            transition_duration=275,
        )
        self.weather_search.add(row(self.city, self.weather_button))
        self.weather_search_toggle = Gtk.ToggleButton(label="\uf002")
        self.weather_search_toggle.set_tooltip_text("搜索城市")
        self.weather_search_toggle.get_accessible().set_name("搜索城市")
        self.weather_search_toggle.get_style_context().add_class("weather-search-toggle")
        self.weather_search_toggle.connect("toggled", self.toggle_weather_search)
        header.pack_end(self.weather_search_toggle, False, False, 0)
        header.pack_end(self.weather_search, False, False, 0)
        self.forecast = label("点击放大镜搜索城市。", "muted")
        self.weather_result = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.put(page, header, self.forecast, self.weather_result)
        self.weather_restored = False
        return page

    def toggle_weather_search(self, button):
        expanded = button.get_active()
        self.weather_search.set_reveal_child(expanded)
        if expanded:
            self.city.grab_focus()
            self.city.select_region(0, -1)

    def restore_weather(self):
        if self.weather_restored:
            return
        self.weather_restored = True
        try:
            city = CITY_FILE.read_text().strip()
        except OSError:
            return
        if city:
            self.city.set_text(city)
            self.query_weather()

    def appearance_page(self):
        page = self.page()
        self.appearance_status = label("", "muted")
        self.appearance_buttons = {}
        for key, icon, title in (
            ("light", "\uf185", "浅色"),
            ("dark", "\uf186", "深色"),
            ("auto", "\uf017", "定时"),
            ("wallpaper", "\uf03e", "随壁纸明暗"),
        ):
            widget = button(f"{icon}  {title}", lambda mode=key: self.set_appearance(mode))
            self.appearance_buttons[key] = widget
        self.palette_buttons = {
            key: button(title, lambda value=key: self.change_palette(source=value))
            for key, title in (("wallpaper", "壁纸取色"), ("dusk", "Dusk 原色"))
        }
        self.strength_buttons = {
            key: button(title, lambda value=key: self.change_palette(strength=value))
            for key, title in (("soft", "柔和"), ("balanced", "标准"), ("vivid", "鲜明"))
        }
        self.palette_preview = Gtk.DrawingArea()
        self.palette_preview.set_size_request(150, 30)
        self.palette_preview.connect("draw", self.draw_palette)
        self.put(page, row(*self.appearance_buttons.values()), self.appearance_status,
                 label("定时模式在 07:00／19:00 切换，随壁纸明暗模式按画面亮度选择。", "muted"),
                 row(*self.palette_buttons.values()), row(*self.strength_buttons.values(), self.palette_preview))
        self.update_appearance_controls()
        return page

    def set_appearance(self, mode):
        try:
            appearance.apply(mode)
            self.reload_appearance()
        except OSError:
            self.appearance_status.set_text("主题切换失败。")

    def change_palette(self, **settings):
        try:
            appearance.apply(**settings)
            self.reload_appearance()
        except OSError:
            self.appearance_status.set_text("主题配色更新失败。")

    def draw_palette(self, _widget, cr):
        palette = appearance.current_palette()
        colors = [palette.get(name, fallback) for name, fallback in (
            ("surface", "#51435e"), ("accent", "#efbc99"), ("secondary", "#c79fcb"))]
        for index, color in enumerate(colors):
            channels = [int(color[i:i+2], 16)/255 for i in (1,3,5)]
            cr.set_source_rgb(*channels)
            cr.arc(19+37*index, 15, 11, 0, 2*pi)
            cr.fill()
        return False

    def reload_appearance(self):
        active = appearance.effective()
        revision = (HERE / "wallpaper-palette.css").stat().st_mtime_ns
        if (active, revision) != (self.active_theme, getattr(self, "palette_revision", None)):
            self.css.load_from_path(str(HERE / "style.css"))
            self.active_theme = active
            self.palette_revision = revision
            self.window.get_settings().set_property("gtk-application-prefer-dark-theme", active == "dark")
            palette = appearance.current_palette()
            for key, (control, _, _) in getattr(self, "sliders", {}).items():
                value = palette.get("border" if key == "output" else "secondary" if key == "input" else "edge")
                control.wallpaper_color = tuple(int(value[i:i+2],16)/255 for i in (1,3,5)) if value else None
                control.canvas.queue_draw()
        if hasattr(self, "appearance_buttons"):
            self.update_appearance_controls()

    def update_appearance_controls(self):
        mode = appearance.read_mode()
        for key, widget in self.appearance_buttons.items():
            css = widget.get_style_context()
            css.add_class("primary-action") if key == mode else css.remove_class("primary-action")
        source, strength = appearance.palette_options()
        for buttons, current in ((self.palette_buttons, source), (self.strength_buttons, strength)):
            for key, button in buttons.items():
                css = button.get_style_context()
                css.add_class("primary-action") if key == current else css.remove_class("primary-action")
                if buttons is self.strength_buttons:
                    button.set_sensitive(source == "wallpaper")
        self.palette_preview.queue_draw()
        names = {"dark": "深色", "light": "浅色"}
        detail = {"auto":" · 定时", "wallpaper":" · 随壁纸", "dark":"", "light":""}
        self.appearance_status.set_text("当前使用" + names[self.active_theme] + detail[mode] +
                                        (" · 壁纸取色" if source == "wallpaper" else " · Dusk 原色"))

    def wallpaper_page(self):
        page = self.page()
        path = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        self.gallery_path = Path(path or (Path.home() / "Pictures")) / "wallpaper"
        self.wallpaper_state = appearance.STATE / "wallpaper-selection"
        self.wallpaper_status = label("", "muted")
        self.gallery = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=12, row_spacing=12)
        self.gallery.set_homogeneous(True)
        self.gallery.set_min_children_per_line(2)
        self.gallery.set_max_children_per_line(4)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(330)
        scroll.add(self.gallery)
        self.put(page, row(
            button("选择图片", self.choose_wallpaper),
            button("重新扫描", self.refresh_gallery),
            button("恢复系统默认", lambda: self.apply_wallpaper(None)),
        ), label(str(self.gallery_path), "muted"), self.wallpaper_status)
        page.pack_start(scroll, True, True, 0)
        self.gallery_index = {}
        self.gallery_stamp = None
        self.gallery_generation = 0
        return page

    def refresh_gallery(self):
        self.gallery_path.mkdir(parents=True, exist_ok=True)
        extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif", ".tiff"}
        items = sorted((path for path in self.gallery_path.iterdir()
                        if path.is_file() and path.suffix.casefold() in extensions),
                       key=lambda path: (path.name.casefold(), path.name))
        stamp = []
        for path in items:
            try:
                stamp.append((path, path.stat().st_mtime_ns))
            except OSError:
                continue
        if stamp == self.gallery_stamp:
            self.highlight_wallpaper()
            return
        self.gallery_stamp = stamp
        self.gallery_generation += 1
        self.gallery_index.clear()
        for widget in self.gallery.get_children():
            widget.destroy()
        if not stamp:
            self.gallery.add(label("壁纸目录中没有图片。", "muted"))
            self.gallery.show_all()
            return

        pending = iter(path for path, _ in stamp)
        generation = self.gallery_generation
        def load_batch():
            if self.window is None or generation != self.gallery_generation:
                return False
            for _ in range(6):
                path = next(pending, None)
                if path is None:
                    self.highlight_wallpaper()
                    return False
                try:
                    texture = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 148, 87, True)
                except GLib.Error:
                    continue
                card = Gtk.Button()
                card.get_style_context().add_class("wallpaper-thumb")
                card.set_tooltip_text(path.name)
                card.connect("clicked", lambda _button, value=path: self.apply_wallpaper(str(value)))
                preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                image = Gtk.Image.new_from_pixbuf(texture)
                image.set_size_request(148, 87)
                name = label("咖啡壁纸" if path.name == "wanderer_coffee.jpg" else path.stem)
                name.set_ellipsize(Pango.EllipsizeMode.END)
                name.set_max_width_chars(16)
                name.set_xalign(.5)
                self.put(preview, image, name)
                card.add(preview)
                self.gallery_index[str(path)] = card
                self.gallery.add(card)
            self.gallery.show_all()
            self.highlight_wallpaper()
            return True
        GLib.idle_add(load_batch)

    def highlight_wallpaper(self):
        try:
            active = self.wallpaper_state.read_text().strip()
        except OSError:
            active = ""
        default_wall = appearance.CONFIG / "niri"
        if not (HERE / "wallpaper.png").exists() and not any(
            (default_wall / f"system-wallpaper.{extension}").exists() for extension in ("png", "jpg")
        ):
            active = str(self.gallery_path / "wanderer_coffee.jpg")
        for filename, card in self.gallery_index.items():
            style = card.get_style_context()
            if filename == active:
                style.add_class("selected")
            else:
                style.remove_class("selected")

    def command(self, *args):
        try:
            run(*args)
        except (OSError, subprocess.TimeoutExpired):
            pass
        self.refresh()

    def open(self, *args):
        try:
            spawn(*args)
        except OSError as exc:
            self.message(str(exc))
            return
        self.window.destroy()

    def message(self, value):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, buttons=Gtk.ButtonsType.CLOSE, text=value)
        dialog.run()
        dialog.destroy()

    def change_slider(self, scale, key):
        self.sliders[key][2].set_text(f"{round(scale.get_value())}%")
        if key not in self.slider_writes:
            self.slider_writes[key] = GLib.timeout_add(45, self.write_slider, key)

    def write_slider(self, key):
        self.slider_writes.pop(key, None)
        control, _, caption = self.sliders[key]
        value = round(control.scale.get_value())
        if key == "brightness":
            args = ("brightnessctl", "-c", "backlight", "set", f"{max(1, value)}%")
        else:
            endpoint = "@DEFAULT_AUDIO_SINK@" if key == "output" else "@DEFAULT_AUDIO_SOURCE@"
            args = ("wpctl", "set-volume", endpoint, f"{value}%")
        try:
            if run(*args).returncode:
                caption.set_text("调整失败")
        except (OSError, subprocess.TimeoutExpired):
            caption.set_text("调整失败")
        return False

    def sync_slider(self, key, value, status=""):
        control, handler, caption = self.sliders[key]
        if control.pressed or key in self.slider_writes:
            return
        control.set_sensitive(value is not None)
        if value is None:
            caption.set_text(status)
            return
        control.scale.handler_block(handler)
        control.scale.set_value(value)
        control.scale.handler_unblock(handler)
        caption.set_text(f"{value}%" + (f" · {status}" if status else ""))

    def refresh_sliders(self):
        for key, endpoint in (("output", "@DEFAULT_AUDIO_SINK@"), ("input", "@DEFAULT_AUDIO_SOURCE@")):
            state = text("wpctl", "get-volume", endpoint)
            match = re.search(r"[0-9]+(?:\.[0-9]+)?", state)
            value = round(float(match[0]) * 100) if match else None
            self.sync_slider(key, value, "已静音" if "MUTED" in state else "无设备" if not match else "")
        if not any(Path("/sys/class/backlight").glob("*")):
            self.sync_slider("brightness", None, "无背光设备")
            return
        current = text("brightnessctl", "-c", "backlight", "-m", "info")
        match = re.search(r"(\d+)%", current)
        self.sync_slider("brightness", int(match[1]) if match else None, "" if match else "不可用")

    def toggle_wifi(self):
        state = text("nmcli", "radio", "wifi")
        self.command("nmcli", "radio", "wifi", "off" if state == "enabled" else "on")

    def bluetooth_state(self):
        if not any(Path("/sys/class/bluetooth").glob("hci*")):
            return ""
        state = text("bluetoothctl", "--timeout", "1", "show")
        return state if "Powered:" in state else ""

    def toggle_bluetooth(self):
        state = self.bluetooth_state()
        if state:
            self.command("bluetoothctl", "power", "off" if "Powered: yes" in state else "on")

    def query_weather(self):
        city = self.city.get_text().strip()
        if not city or not self.weather_button.get_sensitive():
            return
        self.forecast.set_text("正在查询…")
        self.forecast.show()
        self.weather_button.set_sensitive(False)
        task = self.pool.submit(weather, city)
        task.add_done_callback(lambda future: GLib.idle_add(self.show_weather, future, city))

    def show_weather(self, task, city):
        if self.window is None:
            return False
        self.weather_button.set_sensitive(True)
        try:
            place, now, daily = task.result()
        except ValueError as exc:
            self.forecast.set_text(str(exc))
        except Exception:
            self.forecast.set_text("天气服务暂时无法访问，请稍后重试。")
        else:
            self.forecast.hide()
            self.weather_search_toggle.set_active(False)
            self.render_weather(place, now, daily)
            try:
                CITY_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = CITY_FILE.with_suffix(".tmp")
                tmp.write_text(city + "\n")
                tmp.replace(CITY_FILE)
            except OSError:
                pass
        return False

    def render_weather(self, place, now, daily):
        for child in self.weather_result.get_children():
            child.destroy()
        glyph, condition = weather_condition(now["weather_code"])
        hero = Gtk.Box(spacing=16)
        hero.get_style_context().add_class("weather-hero")
        hero.pack_start(label(f"{glyph}  {now['temperature_2m']:.0f}°", "temperature"), False, False, 0)
        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        locality = " · ".join(dict.fromkeys(filter(None, [place["name"], place.get("admin1"), place.get("country")])))
        self.put(summary, label(locality, "track"), label(f"{condition}   体感 {now['apparent_temperature']:.0f}°", "muted"))
        hero.pack_start(summary, True, True, 0)
        latitude, longitude = place["latitude"], place["longitude"]
        map_url = f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=10/{latitude}/{longitude}"
        self.put(self.weather_result, hero)

        forecast = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        forecast.get_style_context().add_class("forecast")
        low = min(daily["temperature_2m_min"])
        high = max(daily["temperature_2m_max"])
        span = max(1, high - low)
        for index, day in enumerate(daily["time"]):
            minimum = daily["temperature_2m_min"][index]
            maximum = daily["temperature_2m_max"][index]
            chance = daily["precipitation_probability_max"][index]
            symbol, description = weather_condition(daily["weather_code"][index])
            weekday = "今天" if index == 0 else "周" + "一二三四五六日"[date.fromisoformat(day).weekday()]
            name = label(f"{weekday}   {symbol}")
            name.set_size_request(75, -1)
            name.set_tooltip_text(description)
            track = Gtk.DrawingArea()
            track.set_size_request(95, 19)
            track.connect("draw", self.draw_range, (minimum-low)/span, (maximum-low)/span)
            low_text = label(f"{minimum:.0f}°", "muted")
            low_text.set_size_request(28, -1)
            item = row(name, low_text)
            item.pack_start(track, True, True, 0)
            item.pack_start(label(f"{maximum:.0f}°"), False, False, 0)
            chance_text = label(f"{chance}% 降水" if chance is not None else "—", "muted")
            chance_text.set_size_request(68, -1)
            item.pack_start(chance_text, False, False, 0)
            forecast.pack_start(item, True, True, 0)
        forecast_layout = Gtk.Box(spacing=12)
        forecast_layout.pack_start(forecast, True, True, 0)
        forecast_layout.pack_start(self.weather_map(latitude, longitude, map_url), False, False, 0)
        self.put(self.weather_result, forecast_layout)

        metrics = Gtk.Grid(column_spacing=24, row_spacing=10, column_homogeneous=True)
        for index, (title, value) in enumerate((
            ("湿度", f"{now['relative_humidity_2m']}%"),
            ("风速", f"{now['wind_speed_10m']:g} km/h"),
            ("气压", f"{now['surface_pressure']:.0f} hPa"),
            ("紫外线", str(daily["uv_index_max"][0])),
        )):
            tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            tile.get_style_context().add_class("weather-metric")
            self.put(tile, label(title, "muted"), label(value, "metric-value"))
            metrics.attach(tile, index, 0, 1, 1)
        self.put(self.weather_result, metrics, self.sunlight(daily, now["time"]), label(f"更新 {now['time'].split('T')[-1]} · Open-Meteo", "muted"))
        self.weather_result.show_all()

    def sunlight(self, daily, now):
        dawn = daily["sunrise"][0]
        dusk = daily["sunset"][0]
        strip = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        strip.get_style_context().add_class("sunlight")
        header = Gtk.Box()
        for title, stamp, align in (("日出", dawn, 0), ("日落", dusk, 1)):
            cluster = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            cluster.set_halign(Gtk.Align.START if align == 0 else Gtk.Align.END)
            symbol = chr(0xf059c if align == 0 else 0xf059b)
            glyph = label(symbol, "sun-symbol")
            glyph.set_xalign(align)
            time = stamp.split("T")[-1] if stamp else "—"
            caption = label(f"{title}  {time}", "muted")
            caption.set_xalign(align)
            self.put(cluster, glyph, caption)
            header.pack_start(cluster, True, True, 0)
        self.put(strip, header)
        if dawn and dusk:
            start = datetime.fromisoformat(dawn)
            stop = datetime.fromisoformat(dusk)
            duration = (stop - start).total_seconds()
            if duration > 0:
                fraction = (datetime.fromisoformat(now) - start).total_seconds() / duration
                line = Gtk.DrawingArea()
                line.set_size_request(-1, 26)
                line.connect("draw", self.draw_sunlight, max(0, min(1, fraction)))
                self.put(strip, line)
        return strip

    def draw_sunlight(self, widget, cr, fraction):
        width = widget.get_allocated_width()
        y = widget.get_allocated_height() / 2
        start, stop = 4, width - 4
        marker = 12 + (width - 24) * fraction
        cr.set_line_width(7)
        cr.set_line_cap(1)
        for left, right, color in (
            (start, marker - 15, (0.11, 0.09, 0.16, 0.4)),
            (marker + 15, stop, (0.91, 0.65, 0.40, 0.85)),
        ):
            if right > left:
                cr.set_source_rgba(*color)
                cr.move_to(left, y)
                cr.line_to(right, y)
                cr.stroke()
        cr.set_source_rgb(1, 0.82, 0.57)
        cr.arc(marker, y, 4, 0, 2 * pi)
        cr.fill()
        cr.set_line_width(1.5)
        for i in range(8):
            angle = i * pi / 4
            dx, dy = cos(angle), sin(angle)
            cr.move_to(marker + 6 * dx, y + 6 * dy)
            cr.line_to(marker + 9 * dx, y + 9 * dy)
        cr.stroke()
        return False

    def weather_map(self, latitude, longitude, url):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        card.get_style_context().add_class("weather-map")
        canvas = Gtk.DrawingArea()
        canvas.set_size_request(300, 210)
        state = {"tiles": [], "message": "正在加载地图…"}

        def draw(widget, cr):
            cr.save()
            width, height = widget.get_allocated_width(), widget.get_allocated_height()
            radius = min(15, width / 2, height / 2)
            cr.new_sub_path()
            cr.arc(width - radius, radius, radius, -pi / 2, 0)
            cr.arc(width - radius, height - radius, radius, 0, pi / 2)
            cr.arc(radius, height - radius, radius, pi / 2, pi)
            cr.arc(radius, radius, radius, pi, 3 * pi / 2)
            cr.close_path()
            cr.clip()
            cr.set_source_rgb(.20, .17, .26)
            cr.paint()
            for x, y, tile in state["tiles"]:
                Gdk.cairo_set_source_pixbuf(cr, tile, x, y)
                cr.paint()
            if state["tiles"]:
                x, y = 150, 105
                cr.set_source_rgb(1, .91, .82)
                cr.arc(x, y, 10, 0, 2*pi)
                cr.fill()
                cr.set_source_rgb(.42, .27, .50)
                cr.arc(x, y, 6, 0, 2*pi)
                cr.fill()
            else:
                cr.set_source_rgb(.87, .81, .90)
                cr.select_font_face("Noto Sans CJK SC")
                cr.set_font_size(13)
                cr.move_to(16, height / 2)
                cr.show_text(state["message"])
            cr.restore()
            return False

        active = True
        def destroyed(_widget):
            nonlocal active
            active = False

        def display(task):
            if self.window is None or not active:
                return False
            try:
                tiles = []
                for x, y, data in task.result():
                    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                    loader.write(data)
                    loader.close()
                    tiles.append((x, y, loader.get_pixbuf()))
                state["tiles"] = tiles
            except (GLib.Error, ValueError, OSError):
                state["message"] = "地图暂不可用，可在浏览器打开。"
            canvas.queue_draw()
            return False

        canvas.connect("draw", draw)
        canvas.connect("destroy", destroyed)
        attribution = Gtk.LinkButton.new_with_label("https://www.openstreetmap.org/copyright", "© OpenStreetMap")
        open_map = Gtk.LinkButton.new_with_label(url, "打开地图 ↗")
        self.put(card, canvas, row(attribution, open_map))
        task = self.pool.submit(map_tiles, latitude, longitude)
        task.add_done_callback(lambda future: GLib.idle_add(display, future))
        return card

    def draw_range(self, widget, cr, start, end):
        width = widget.get_allocated_width()
        middle = widget.get_allocated_height() / 2
        cr.set_line_cap(1)
        cr.set_line_width(4)
        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.move_to(3, middle)
        cr.line_to(width - 3, middle)
        cr.stroke()
        cr.set_line_width(8)
        cr.set_source_rgb(0.96, 0.74, 0.56)
        cr.move_to(3 + start * (width - 6), middle)
        cr.line_to(3 + end * (width - 6), middle)
        cr.stroke()
        return False

    def choose_wallpaper(self):
        dialog = Gtk.FileChooserNative.new("选择壁纸", self.window, Gtk.FileChooserAction.OPEN, "应用", "取消")
        images = Gtk.FileFilter()
        images.set_name("图片")
        images.add_pixbuf_formats()
        dialog.add_filter(images)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            self.apply_wallpaper(dialog.get_filename())
        dialog.destroy()

    def apply_wallpaper(self, filename):
        target = HERE / "wallpaper.png"
        temp = target.with_name("wallpaper.tmp.png")
        old = target.with_name("wallpaper.previous.png")
        replaced = False
        if old.exists():
            self.wallpaper_status.set_text("上次壁纸切换未完成，请先检查壁纸文件。")
            return
        try:
            if filename:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(filename, 3840, 2160, True)
                pixbuf.savev(str(temp), "png", [], [])
            old_pids = text("pgrep", "-u", str(os.getuid()), "-x", "swaybg").splitlines()
            if target.exists():
                target.replace(old)
            if filename:
                temp.replace(target)
                replaced = True
            process = spawn(str(HERE / "wallpaper"))
            time.sleep(0.2)
            if process.poll() is not None:
                raise OSError("壁纸服务未能启动")
        except (GLib.Error, OSError, subprocess.TimeoutExpired) as exc:
            temp.unlink(missing_ok=True)
            if old.exists():
                old.replace(target)
            elif replaced:
                target.unlink(missing_ok=True)
            self.wallpaper_status.set_text(f"未能应用壁纸：{exc}")
            return
        for pid in old_pids:
            try:
                os.kill(int(pid), 15)
            except ProcessLookupError:
                pass
        old.unlink(missing_ok=True)
        try:
            self.wallpaper_state.parent.mkdir(parents=True, exist_ok=True)
            if filename:
                self.wallpaper_state.write_text(str(Path(filename).resolve()) + "\n")
            else:
                self.wallpaper_state.unlink(missing_ok=True)
        except OSError:
            pass
        self.highlight_wallpaper()
        self.wallpaper_status.set_text("壁纸已更新。")
        try:
            appearance.apply()
            self.reload_appearance()
        except OSError:
            self.wallpaper_status.set_text("壁纸已更新，主题配色未能同步。")

    def refresh(self):
        if self.window is None:
            return False
        self.reload_appearance()
        page = self.stack.get_visible_child_name()
        try:
            if page == "media":
                state = text(*PLAYER, "status")
                title = text(*PLAYER, "metadata", "title") if state else ""
                artist = text(*PLAYER, "metadata", "artist") if state else ""
                self.track.set_text(title or ("正在使用媒体播放器" if state else "当前没有可控制的媒体"))
                self.artist.set_text(artist or ("播放和切换取决于应用提供的控制。" if state else "开始播放后会显示标题和控制键。"))
                self.play.set_label("\uf04c" if state == "Playing" else "\uf04b")
                for widget in (self.play, self.previous, self.next):
                    widget.set_sensitive(bool(state))
            elif page == "sound":
                self.refresh_sliders()

            elif page == "display":
                value = text("niri", "msg", "--json", "outputs")
                outputs = json.loads(value) if value else {}
                lines = []
                for name, output in outputs.items():
                    mode_index = output.get("current_mode")
                    if mode_index is not None:
                        mode = output["modes"][mode_index]
                        lines.append(f"{name}  ·  {mode['width']} × {mode['height']}  ·  {mode['refresh_rate']/1000:g} Hz")
                self.outputs.set_text("\n".join(lines) or "未读取到显示输出。")
            elif page == "wifi":
                state = text("nmcli", "radio", "wifi")
                devices = text("nmcli", "-t", "-f", "TYPE,STATE", "device", "status")
                has_wifi = any(line.startswith("wifi:") for line in devices.splitlines())
                self.wifi.set_sensitive(has_wifi)
                self.network.set_text(("Wi‑Fi 已开启" if state == "enabled" else "Wi‑Fi 已关闭")
                                      if has_wifi else "未检测到 Wi‑Fi 网卡，可在连接设置中管理有线网络。")
            elif page == "bluetooth":
                state = self.bluetooth_state()
                self.bluetooth_toggle.set_sensitive(bool(state))
                self.bluetooth.set_text(("蓝牙已开启" if "Powered: yes" in state else "蓝牙已关闭")
                                        if state else "未检测到蓝牙适配器。")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return True


if __name__ == "__main__":
    raise SystemExit(ControlCenter().run())
