from collections import deque
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from time import monotonic

import gi
from cairo import Region

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, Gio, GLib, Gtk, GtkLayerShell, Pango

import appearance
from docker_widget import DockerWidget
from island import CITY_FILE, cached_weather, metrics
from weather import weather, weather_condition

STYLE = Path(__file__).with_name("desktop-widgets.css").read_text()
STATE_FILE = appearance.STATE / "desktop-widgets.json"
WIDGETS = {
    "docker": ("Docker", .025, .76),
    "clock": ("\u65f6\u949f", .96, .70),
    "date": ("\u65e5\u671f", .96, .77),
    "weather": ("\u5929\u6c14", .96, .825),
    "system": ("\u7cfb\u7edf\u5360\u7528", .96, .91),
}
PALETTES = {
    "light": ("#fff7ed", "#30263a", "#93634d", "#a88ea8"),
    "dark": ("#2b2335", "#fff1f3", "#efbc99", "#ac8eb4"),
}


def clamp(value):
    return max(0.0, min(1.0, value))


def read_layout():
    try:
        data = json.loads(STATE_FILE.read_text())
        return {
            name: (clamp(x), clamp(y))
            for name, (x, y) in data.items()
            if name in WIDGETS and isinstance(x, (int, float)) and isinstance(y, (int, float))
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {name: (x, y) for name, (_, x, y) in WIDGETS.items()}


class DesktopWidgets(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.scaraovo.DuskDesktopWidgets",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        self.positions = read_layout()
        self.windows = {}
        self.editor = None
        self.canvas = None
        self.visible = False
        self.drag = None
        self.workspace_return = None
        self.cpu_history = deque(maxlen=28)
        self.theme = None
        self.city = None
        self.weather_data = None
        self.weather_due = 0
        self.inflight = False
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.refresh_clock()
        for interval, callback in ((1, self.refresh_clock), (4, self.refresh_metrics), (30, self.refresh_weather)):
            GLib.timeout_add_seconds(interval, callback)

    def do_command_line(self, command):
        args = command.get_arguments()[1:]
        action = args[0] if args else "toggle"
        if action == "edit":
            if self.editor:
                self.editor.destroy()
            else:
                self.open_editor()
        elif action == "show":
            self.show_widgets(True)
        elif action == "toggle":
            self.show_widgets(not self.visible)
        else:
            return 2
        return 0

    def save_layout(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = STATE_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.positions, indent=2) + "\n")
            temporary.replace(STATE_FILE)
        except OSError as error:
            print(error, flush=True)

    @staticmethod
    def monitor():
        display = Gdk.Display.get_default()
        return display.get_primary_monitor() or display.get_monitor(0)

    @staticmethod
    def label(style, align=0):
        widget = Gtk.Label(xalign=align)
        widget.get_style_context().add_class(style)
        return widget

    def show_widgets(self, visible):
        if visible == self.visible:
            return
        self.visible = visible
        if not visible and self.editor:
            self.editor.destroy()
        for window in self.windows.values():
            window.destroy()
        self.windows.clear()
        if visible:
            for name in self.positions:
                self.add_widget(name)
            self.refresh_clock()
            self.refresh_metrics()
            self.refresh_weather()

    def add_widget(self, name):
        window = Gtk.ApplicationWindow(application=self, name="dusk-desktop-widget")
        window.set_decorated(False)
        window.set_visual(window.get_screen().get_rgba_visual())
        GtkLayerShell.init_for_window(window)
        GtkLayerShell.set_namespace(window, f"dusk-desktop-widget-{name}")
        GtkLayerShell.set_layer(window, GtkLayerShell.Layer.BOTTOM)
        GtkLayerShell.set_monitor(window, self.monitor())
        GtkLayerShell.set_exclusive_zone(window, -1)
        for edge in (GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.TOP):
            GtkLayerShell.set_anchor(window, edge, True)
        if name == "system":
            window.get_style_context().add_class("system-widget")
            content = self.system_view()
        elif name == "docker":
            window.get_style_context().add_class("system-widget")
            content = DockerWidget()
        else:
            content = self.label(f"desktop-{name}")
            if name == "weather":
                content.set_ellipsize(Pango.EllipsizeMode.END)
                content.set_max_width_chars(24)
        content.set_margin_start(10)
        content.set_margin_end(10)
        content.set_margin_top(5)
        content.set_margin_bottom(5)
        window.add(content)
        self.windows[name] = window
        window.connect("size-allocate", lambda *_: self.place_widget(name))
        window.connect("realize", lambda widget: widget.get_window().input_shape_combine_region(Region(), 0, 0))
        if name != "weather":
            window.show_all()
        self.place_widget(name)

    def widget_bounds(self, name):
        window = self.windows[name]
        geometry = self.monitor().get_geometry()
        child = window.get_child()
        if window.get_mapped():
            size = window.get_size()
            width, height = size.width, size.height
        else:
            width = child.get_preferred_width()[1]
            height = child.get_preferred_height()[1]
        x, y = self.positions[name]
        return (round(x * max(0, geometry.width - width)),
                round(y * max(0, geometry.height - height)), width, height)

    def place_widget(self, name):
        if name not in self.windows:
            return
        x, y, _, _ = self.widget_bounds(name)
        for edge, margin in ((GtkLayerShell.Edge.LEFT, x), (GtkLayerShell.Edge.TOP, y)):
            if GtkLayerShell.get_margin(self.windows[name], edge) != margin:
                GtkLayerShell.set_margin(self.windows[name], edge, margin)

    def system_view(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panel.set_size_request(324, -1)
        title = self.label("system-title")
        title.set_text("系统占用")
        panel.pack_start(title, False, False, 0)
        tiles = Gtk.Box(spacing=7, homogeneous=True)
        panel.pack_start(tiles, False, False, 0)
        self.system_values = {}
        for name, title in (("cpu", "CPU"), ("ram", "内存"), ("disk", "磁盘")):
            tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            tile.get_style_context().add_class("desktop-metric")
            heading = self.label("metric-name")
            heading.set_text(title)
            value = self.label("metric-value")
            if name == "cpu":
                gauge = Gtk.DrawingArea()
                gauge.get_style_context().add_class("cpu-trend")
                gauge.set_size_request(-1, 14)
                gauge.connect("draw", self.draw_cpu)
            else:
                gauge = Gtk.ProgressBar()
                gauge.set_valign(Gtk.Align.CENTER)
            for widget in (heading, value, gauge):
                tile.pack_start(widget, False, False, 0)
            tiles.pack_start(tile, True, True, 0)
            self.system_values[name] = value, gauge
        return panel

    def draw_cpu(self, widget, cr):
        samples = tuple(self.cpu_history)
        if len(samples) < 2:
            return False
        width = max(1, widget.get_allocated_width() - 2)
        height = max(1, widget.get_allocated_height() - 3)
        color = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        cr.set_line_width(1.5)
        cr.move_to(1, 1 + height * (1 - samples[0]))
        for index, sample in enumerate(samples[1:], 1):
            cr.line_to(1 + index * width / (len(samples) - 1), 1 + height * (1 - sample))
        cr.stroke()
        return False

    def refresh_clock(self):
        now = datetime.now()
        mode = appearance.effective()
        palette = appearance.current_palette()
        names = ("surface", "ink", "secondary", "edge")
        colors = tuple(palette.get(name, fallback) for name, fallback in zip(names, PALETTES[mode]))
        if colors != self.theme:
            declarations = "".join(f"@define-color widget_{key} {color};\n" for key, color in
                                   zip(("surface", "ink", "accent", "edge"), colors))
            self.css.load_from_data((declarations + STYLE).encode())
            self.theme = colors
        if "clock" in self.windows:
            self.windows["clock"].get_child().set_text(now.strftime("%H:%M"))
        if "date" in self.windows:
            week = "\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5"[now.weekday()]
            self.windows["date"].get_child().set_text(f"{now.month} \u6708 {now.day} \u65e5  \u00b7  \u661f\u671f{week}")
        return True

    def refresh_metrics(self):
        if "system" not in self.windows:
            return True
        try:
            cpu, ram, used, _, disk = metrics()
        except (OSError, ValueError, KeyError):
            return True
        gib = 1024 ** 3
        self.cpu_history.append(clamp(cpu / 100))
        value, trend = self.system_values["cpu"]
        value.set_text(f"{cpu}%")
        trend.queue_draw()
        for name, text, fraction in (
            ("ram", f"{used / gib:.1f} GiB", ram / 100),
            ("disk", f"{disk.used / disk.total:.0%}", disk.used / disk.total),
        ):
            value, bar = self.system_values[name]
            value.set_text(text)
            bar.set_fraction(clamp(fraction))
        return True

    def show_weather(self):
        window = self.windows.get("weather")
        if window is None:
            return
        if not self.weather_data:
            window.hide()
            return
        place, current, _ = self.weather_data
        glyph, condition = weather_condition(current["weather_code"])
        window.get_child().set_text(f"{glyph}  {current['temperature_2m']:.0f}\u00b0  \u00b7  {place['name']}  {condition}")
        window.show_all()
        self.place_widget("weather")
        if self.canvas:
            self.canvas.queue_draw()

    def refresh_weather(self):
        if "weather" not in self.windows:
            return True
        try:
            city = CITY_FILE.read_text().strip()
        except OSError:
            city = ""
        if city != self.city:
            self.city = city
            self.weather_due = 0
            saved = cached_weather()
            self.weather_data = saved.get("data") if saved.get("city") == city else None
        self.show_weather()
        if not city or self.inflight or monotonic() < self.weather_due:
            return True
        self.inflight = True

        def done(data):
            self.inflight = False
            if city == self.city:
                self.weather_due = monotonic() + (1200 if data else 300)
                if data:
                    self.weather_data = data
                    self.show_weather()
            return False

        def fetch():
            try:
                data = weather(city)
            except (OSError, ValueError, KeyError):
                data = None
            GLib.idle_add(done, data)

        Thread(target=fetch, daemon=True).start()
        return True

    @staticmethod
    def niri(*args):
        return subprocess.run(("niri", "msg", *args), capture_output=True,
                              text=True, check=True, timeout=2).stdout

    def clear_desktop(self):
        workspaces = json.loads(self.niri("--json", "workspaces"))
        focused = next(ws for ws in workspaces if ws["is_focused"])
        if focused["active_window_id"] is None:
            return
        empty = next(ws for ws in workspaces
                     if ws["output"] == focused["output"] and ws["active_window_id"] is None)
        self.niri("action", "focus-workspace", str(empty["idx"]))
        self.workspace_return = focused["id"], empty["id"]

    def restore_desktop(self):
        if self.workspace_return is None:
            return
        original, editing = self.workspace_return
        self.workspace_return = None
        try:
            workspaces = json.loads(self.niri("--json", "workspaces"))
            if any(ws["id"] == editing and ws["is_focused"] for ws in workspaces):
                destination = next(ws for ws in workspaces if ws["id"] == original)
                self.niri("action", "focus-workspace", str(destination["idx"]))
        except (StopIteration, ValueError, OSError, subprocess.SubprocessError) as error:
            print(error, file=sys.stderr)

    def open_editor(self):
        try:
            self.clear_desktop()
        except (StopIteration, ValueError, OSError, subprocess.SubprocessError) as error:
            print(error, file=sys.stderr)
            return

        self.show_widgets(True)
        self.editor = Gtk.ApplicationWindow(application=self, name="dusk-widget-editor")
        self.editor.set_decorated(False)
        self.editor.set_visual(self.editor.get_screen().get_rgba_visual())
        GtkLayerShell.init_for_window(self.editor)
        GtkLayerShell.set_namespace(self.editor, "dusk-widget-editor")
        GtkLayerShell.set_layer(self.editor, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_monitor(self.editor, self.monitor())
        GtkLayerShell.set_exclusive_zone(self.editor, -1)
        GtkLayerShell.set_keyboard_mode(self.editor, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self.editor, edge, True)
        self.editor.connect("destroy", self.editor_closed)
        self.editor.connect("key-press-event", self.editor_key)

        content = Gtk.Overlay()
        self.editor.add(content)
        self.canvas = Gtk.DrawingArea()
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                               Gdk.EventMask.POINTER_MOTION_MASK)
        self.canvas.connect("draw", self.draw_handles)
        self.canvas.connect("button-press-event", self.start_drag)
        self.canvas.connect("motion-notify-event", self.move_drag)
        self.canvas.connect("button-release-event", self.finish_drag)
        content.add(self.canvas)

        toolbar = Gtk.Box(spacing=14, halign=Gtk.Align.CENTER, valign=Gtk.Align.START,
                          margin_top=58, name="widget-editor-card")
        title = self.label("widget-editor-title")
        title.set_text("编辑小组件")
        toolbar.pack_start(title, False, False, 0)
        for name, (label, _, _) in WIDGETS.items():
            check = Gtk.CheckButton(label=label)
            check.set_active(name in self.positions)
            check.connect("toggled", self.change_widget, name)
            toolbar.pack_start(check, False, False, 0)
        done = Gtk.Button(label="完成")
        done.connect("clicked", lambda *_: self.editor.destroy())
        toolbar.pack_start(done, False, False, 0)
        content.add_overlay(toolbar)
        self.editor.show_all()

    def editor_closed(self, _window):
        if self.drag:
            self.save_layout()
        self.drag = None
        self.canvas = None
        self.editor = None
        self.restore_desktop()

    def editor_key(self, window, event):
        if event.keyval == Gdk.KEY_Escape:
            window.destroy()
            return True
        return False

    def change_widget(self, check, name):
        if check.get_active():
            _, x, y = WIDGETS[name]
            self.positions[name] = x, y
            self.add_widget(name)
            self.refresh_clock()
            self.refresh_metrics()
            self.refresh_weather()
        else:
            if self.drag and self.drag[0] == name:
                self.drag = None
            self.windows.pop(name).destroy()
            del self.positions[name]
        self.save_layout()
        self.canvas.queue_draw()

    def draw_handles(self, _canvas, cr):
        cr.set_line_width(1)
        cr.set_dash([4, 4])
        for name, window in self.windows.items():
            if not window.get_mapped():
                continue
            x, y, width, height = self.widget_bounds(name)
            cr.set_source_rgba(.04, .03, .06, .85)
            cr.rectangle(x, y, width, height)
            cr.stroke()
            cr.set_source_rgba(1, 1, 1, .92)
            cr.rectangle(x + 1, y + 1, width - 2, height - 2)
            cr.stroke()
        return False

    def start_drag(self, _canvas, event):
        if event.button != 1:
            return False
        for name in reversed(self.windows):
            if not self.windows[name].get_mapped():
                continue
            x, y, width, height = self.widget_bounds(name)
            if x <= event.x <= x + width and y <= event.y <= y + height:
                self.drag = name, event.x - x, event.y - y
                return True
        return False

    def move_drag(self, canvas, event):
        if not self.drag:
            return False
        name, offset_x, offset_y = self.drag
        _, _, width, height = self.widget_bounds(name)
        geometry = self.monitor().get_geometry()
        self.positions[name] = (
            clamp((event.x - offset_x) / max(1, geometry.width - width)),
            clamp((event.y - offset_y) / max(1, geometry.height - height)),
        )
        self.place_widget(name)
        canvas.queue_draw()
        return True

    def finish_drag(self, canvas, event):
        if not self.drag or event.button != 1:
            return False
        self.move_drag(canvas, event)
        self.drag = None
        self.save_layout()
        return True


if __name__ == "__main__":
    raise SystemExit(DesktopWidgets().run(sys.argv))
