from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import calendar
import json
import os
import shutil
import socket
import signal
import time

import appearance
from usage import available_usage

MODE_FILE = appearance.STATE / "island-page"
MODE_NAMES = {"time": "时间", "date": "日期", "tokens": "Token 用量", "system": "系统占用"}


def pages(usage):
    return ["time", "date", "tokens", "system"] if usage else ["time", "date", "system"]


def current_page(available):
    try:
        page = MODE_FILE.read_text().strip()
    except OSError:
        page = "time"
    return page if page in available else "time"


def cycle(amount, available):
    MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    page = available[(available.index(current_page(available)) + amount) % len(available)]
    temporary = MODE_FILE.with_name(f"{MODE_FILE.name}.{os.getpid()}.tmp")
    temporary.write_text(page)
    temporary.replace(MODE_FILE)


def cpu_ticks():
    with Path("/proc/stat").open() as source:
        ticks = [int(field) for field in source.readline().split()[1:9]]
    return sum(ticks), ticks[3] + ticks[4]


def metrics():
    total, idle = cpu_ticks()
    time.sleep(.065)
    ending, idle_end = cpu_ticks()
    cpu = round(100 * (1 - (idle_end - idle) / max(1, ending - total)))
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, _, value = line.partition(":")
        if name in ("MemTotal", "MemAvailable"):
            memory[name] = int(value.split()[0]) * 1024
    mem_total = memory["MemTotal"]
    mem_used = mem_total - memory["MemAvailable"]
    disk = shutil.disk_usage("/")
    return cpu, round(mem_used / mem_total * 100), mem_used, mem_total, disk


def compact(value):
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1000, "k")):
        if value >= limit:
            return f"{value / limit:.1f}{suffix}"
    return str(value)


def waybar_text(page, usage):
    now = datetime.now()
    if page == "time":
        return "  " + now.strftime("%H:%M")
    if page == "date":
        return "  " + now.strftime("%m/%d")
    if page == "tokens":
        return "  " + "  ·  ".join(f"{short} {compact(counts['total_tokens'])}" for _, short, counts, _ in usage)
    cpu, ram, *_ = metrics()
    return f" {cpu}%   󰍛 {ram}%"


def marker():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return runtime / "dusk-island-expanded"


def expanded():
    try:
        pid = int(marker().read_text())
        return b"island.py" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except (ValueError, OSError):
        return False


def refresh_waybar():
    appearance.notify("pkill", f"-{signal.SIGRTMIN + 12}", "-u", str(os.getuid()), "-x", "waybar")


def show_panel():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, Gio, GLib, Gtk, GtkLayerShell

    class Island(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="io.github.scaraovo.DuskIsland",
                             flags=Gio.ApplicationFlags.FLAGS_NONE)
            self.panel = None
            self.closing = False
            self.displayed = None

        def do_activate(self):
            if self.panel:
                self.close()
                return
            self.panel = Gtk.ApplicationWindow(application=self)
            self.panel.set_name("dusk-island")
            self.panel.set_decorated(False)
            self.panel.set_default_size(-1, -1)
            self.panel.set_resizable(True)
            self.panel.set_app_paintable(True)
            self.panel.set_visual(self.panel.get_screen().get_rgba_visual())
            self.panel.connect("key-press-event", self.keys)
            self.panel.connect("destroy", self.closed)
            GtkLayerShell.init_for_window(self.panel)
            GtkLayerShell.set_namespace(self.panel, "dusk-island")
            GtkLayerShell.set_layer(self.panel, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self.panel, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_margin(self.panel, GtkLayerShell.Edge.TOP, 8)
            GtkLayerShell.set_keyboard_mode(self.panel, GtkLayerShell.KeyboardMode.ON_DEMAND)
            GtkLayerShell.set_exclusive_zone(self.panel, -1)

            self.css = Gtk.CssProvider()
            self.css_revision = None
            Gtk.StyleContext.add_provider_for_screen(self.panel.get_screen(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.frame.set_name("island-frame")
            self.frame.set_size_request(109, 36)
            self.panel.add(self.frame)
            self.head = Gtk.Button()
            self.head.set_name("island-head")
            self.head.set_size_request(107, 34)
            self.head.connect("clicked", lambda *_: self.close())
            self.frame.pack_start(self.head, False, False, 0)
            self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.content.set_name("island-content")
            self.content.set_size_request(350, -1)
            self.frame.pack_start(self.content, True, True, 0)
            self.refresh()
            self.expanded_size = self.measure()
            self.content.hide()
            self.content.set_no_show_all(True)
            self.panel.show_all()
            marker().write_text(str(os.getpid()))
            refresh_waybar()
            GLib.idle_add(self.reveal)
            GLib.timeout_add_seconds(1, self.refresh)

        def measure(self):
            width = max(350, self.content.get_preferred_width()[1])
            height = self.content.get_preferred_height_for_width(width)[1]
            return width + 2, self.compact_size()[1] + height

        def compact_size(self):
            return max(109, self.head.get_preferred_width()[1] + 2), 36

        def morph(self, target, duration, finished):
            initial = self.panel.get_size()
            started = GLib.get_monotonic_time()
            if not self.panel.get_settings().get_property("gtk-enable-animations"):
                self.frame.set_size_request(*target)
                finished()
                return

            def step(_widget, _clock):
                progress = min(1.0, (GLib.get_monotonic_time() - started) / (duration * 1000))
                eased = 1 - (1 - progress) ** 3
                self.frame.set_size_request(*(round(a + (b - a) * eased) for a, b in zip(initial, target)))
                if progress >= 1:
                    self.tick_id = None
                    finished()
                    return False
                return True

            if getattr(self, "tick_id", None):
                self.panel.remove_tick_callback(self.tick_id)
            self.tick_id = self.panel.add_tick_callback(step)

        def fade_content(self):
            self.content.set_opacity(0)
            self.content.show()
            started = GLib.get_monotonic_time()
            def step(_widget, _clock):
                if self.closing:
                    return False
                progress = min(1.0, (GLib.get_monotonic_time() - started) / 125000)
                self.content.set_opacity(1 - (1 - progress) ** 2)
                return progress < 1
            self.panel.add_tick_callback(step)

        def closed(self, _window):
            try:
                if marker().read_text() == str(os.getpid()):
                    marker().unlink()
                    refresh_waybar()
            except OSError:
                pass

        def reveal(self):
            if not self.closing:
                self.morph(self.expanded_size, 300, self.fade_content)
            return False

        def keys(self, _widget, event):
            if event.keyval == Gdk.KEY_Escape:
                self.close()
                return True
            return False

        def close(self):
            if self.closing:
                return
            self.closing = True
            self.content.hide()
            self.morph(self.compact_size(), 245, self.panel.destroy)

        def print_line(self, line, style, parent=None):
            widget = Gtk.Label(label=line, xalign=0)
            widget.get_style_context().add_class(style)
            (parent or self.content).pack_start(widget, False, False, 0)
            return widget

        def metric(self, name, value, description):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self.content.pack_start(box, False, False, 0)
            self.print_line(f"{name}  {value}%   {description}", "detail", box)
            bar = Gtk.ProgressBar(fraction=value / 100)
            box.pack_start(bar, False, False, 0)

        def refresh(self):
            if self.closing:
                return False
            usage = available_usage()
            available = pages(usage)
            page = current_page(available)
            now = datetime.now()
            mode = appearance.effective()
            revision = Path(__file__).with_name("island-wallpaper.css").stat().st_mtime_ns
            if revision != self.css_revision:
                self.css.load_from_path(str(Path(__file__).with_name("island.css")))
                self.css_revision = revision
            if page == "system":
                payload = metrics()
            elif page == "tokens":
                payload = usage
            elif page == "time":
                payload = now.strftime("%H:%M:%S")
            else:
                payload = now.date()
            caption = f" {payload[0]}%   󰍛 {payload[1]}%" if page == "system" else waybar_text(page, usage)
            self.head.set_label(caption)
            if (page, payload, mode) == self.displayed:
                return True
            if page == "date" and self.displayed is not None and self.displayed[0] == "date":
                if self.displayed[1] == payload:
                    self.palette(mode)
                    self.displayed = (page, payload, mode)
                    return True
            self.displayed = page, payload, mode
            self.palette(mode)
            for child in self.content.get_children():
                child.destroy()
            self.print_line(MODE_NAMES[page], "heading")
            weekdays = "一二三四五六日"
            if page in ("time", "date"):
                long_date = f"{now.year} 年 {now.month} 月 {now.day} 日  周{weekdays[now.weekday()]}"
                if page == "time":
                    self.print_line(payload, "hero")
                    self.print_line(f"{long_date}  ·  {now.astimezone().tzname() or '本机时间'}", "detail")
                else:
                    self.print_line(long_date, "hero date")
                    grid = Gtk.Calendar()
                    grid.select_month(now.month - 1, now.year)
                    grid.select_day(now.day)
                    self.content.pack_start(grid, False, False, 0)
            elif page == "tokens":
                self.print_line("各工具最新本机会话累计", "footnote")
                for name, _, counts, timestamp in payload:
                    self.print_line(f"{name}   {counts['total_tokens']:,}", "source")
                    fields = (("输入", "input_tokens"), ("缓存读取", "cached_input_tokens"),
                              ("缓存写入", "cache_write_input_tokens"), ("输出", "output_tokens"),
                              ("推理输出", "reasoning_output_tokens"))
                    for label, key in fields:
                        value = counts.get(key)
                        if isinstance(value, int):
                            self.print_line(f"{label}   {value:,}", "detail")
                    if timestamp:
                        try:
                            stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone()
                            self.print_line(stamp.strftime("更新 %m/%d %H:%M"), "footnote")
                        except ValueError:
                            pass
            else:
                cpu, ram, used, total, disk = payload
                gib = 1024 ** 3
                self.metric("CPU", cpu, f"{os.cpu_count()} 线程")
                self.metric("内存", ram, f"{used / gib:.1f} / {total / gib:.1f} GiB")
                self.metric("磁盘", round(disk.used / disk.total * 100),
                            f"{disk.used / gib:.0f} / {disk.total / gib:.0f} GiB")
                uptime = int(float(Path("/proc/uptime").read_text().split()[0]))
                self.print_line(f"{socket.gethostname()}  ·  已运行 {uptime // 3600} 小时 {(uptime // 60) % 60} 分钟", "footnote")
            for child in self.content.get_children():
                child.show_all()
            if not self.panel.get_mapped() or self.content.get_visible():
                self.content.show()
            return True

        def palette(self, mode):
            style = self.panel.get_style_context()
            style.remove_class("light" if mode == "dark" else "dark")
            style.add_class(mode)

    return Island().run()


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("action", choices=("status", "next", "previous", "panel"))
    args = parser.parse_args()
    if args.action == "panel":
        raise SystemExit(show_panel())
    usage = available_usage()
    available = pages(usage)
    if args.action == "status":
        print(json.dumps({"text": waybar_text(current_page(available), usage),
                          "class": "expanded" if expanded() else "compact"}, ensure_ascii=False))
    else:
        cycle(1 if args.action == "next" else -1, available)
