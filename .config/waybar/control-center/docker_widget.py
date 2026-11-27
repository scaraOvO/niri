import json
import re
import subprocess
from threading import Thread

from gi.repository import GLib, Gtk, Pango

UNITS = {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4,
         "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
MAX_CARDS = 4


def docker_rows(*args):
    result = subprocess.run(("docker", *args, "--format", "{{json .}}"),
                            text=True, capture_output=True, check=True, timeout=6)
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def memory_bytes(value):
    match = re.fullmatch(r"\s*([\d.]+)\s*([A-Za-z]+)\s*", value)
    if not match or match[2] not in UNITS:
        return 0
    return round(float(match[1]) * UNITS[match[2]])


def memory_label(size):
    return f"{size / 1024**3:.1f} GiB" if size >= 1024**3 else f"{size / 1024**2:.1f} MiB"


def snapshot():
    containers = docker_rows("ps", "-a")
    running = [row for row in containers if row["State"] == "running"]
    stats = []
    if running:
        try:
            stats = docker_rows("stats", "--no-stream")
        except (subprocess.SubprocessError, ValueError):
            pass
    resources = {}
    for row in stats:
        try:
            cpu = float(row["CPUPerc"].rstrip("%"))
            memory, _, limit = row["MemUsage"].partition("/")
            resources[row["Name"]] = (cpu, memory_bytes(memory) if memory_bytes(limit) else None)
        except (KeyError, ValueError):
            continue
    containers.sort(key=lambda row: row["State"] != "running")
    return len(running), containers, resources


class DockerWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_size_request(324, -1)
        self.alive = True
        self.busy = False

        header = Gtk.Box(spacing=8)
        title = self.label("Docker", "system-title")
        self.status = self.label("", "docker-subtle")
        header.pack_start(title, True, True, 0)
        header.pack_end(self.status, False, False, 0)
        self.pack_start(header, False, False, 0)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.pack_start(self.content, False, False, 0)
        self.draw_content(None, "\u6b63\u5728\u8bfb\u53d6\u5bb9\u5668\u2026")
        self.timer = GLib.timeout_add_seconds(7, self.refresh)
        self.connect("destroy", self.closed)
        self.refresh()

    @staticmethod
    def label(text, style):
        label = Gtk.Label(label=text, xalign=0)
        label.get_style_context().add_class(style)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        return label

    def closed(self, _widget):
        self.alive = False
        GLib.source_remove(self.timer)

    def refresh(self):
        if self.busy:
            return True
        self.busy = True

        def fetch():
            try:
                data = snapshot()
                message = ""
            except FileNotFoundError:
                data, message = None, "\u672a\u5b89\u88c5 Docker CLI"
            except subprocess.TimeoutExpired:
                data, message = None, "Docker \u54cd\u5e94\u8d85\u65f6"
            except (subprocess.CalledProcessError, OSError, ValueError, KeyError):
                data, message = None, "\u65e0\u6cd5\u8fde\u63a5 Docker"
            GLib.idle_add(self.finish, data, message)

        Thread(target=fetch, daemon=True).start()
        return True

    def finish(self, data, message):
        self.busy = False
        if self.alive:
            self.draw_content(data, message)
        return False

    def tile(self, title, value):
        tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        tile.get_style_context().add_class("desktop-metric")
        tile.pack_start(self.label(title, "metric-name"), False, False, 0)
        tile.pack_start(self.label(value, "metric-value"), False, False, 0)
        return tile

    def draw_content(self, data, message):
        for child in self.content.get_children():
            child.destroy()
        if data is None:
            self.status.set_text("")
            self.content.pack_start(self.label(message, "docker-subtle"), False, False, 0)
            self.content.show_all()
            return

        running, containers, resources = data
        self.status.set_text(f"{running} \u8fd0\u884c\u4e2d")
        cpu_total = sum(cpu for cpu, _ in resources.values())
        memory = [used for _, used in resources.values() if used is not None]
        summary = Gtk.Box(spacing=7, homogeneous=True)
        for title, value in (("\u8fd0\u884c", f"{running}/{len(containers)}"),
                             ("CPU", f"{cpu_total:.1f}%" if resources else "\u2014"),
                             ("\u5185\u5b58", memory_label(sum(memory)) if memory else "\u2014")):
            summary.pack_start(self.tile(title, value), True, True, 0)
        self.content.pack_start(summary, False, False, 0)

        if containers:
            grid = Gtk.Grid(column_homogeneous=True, column_spacing=7, row_spacing=7)
            for index, row in enumerate(containers[:MAX_CARDS]):
                name, image = row["Names"], row["Image"]
                active = row["State"] == "running"
                cpu, used = resources.get(name, (None, None))
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                card.get_style_context().add_class("desktop-metric")
                header = Gtk.Box(spacing=5)
                badge = self.label("\u25cf" if active else "\u25cb", "docker-running" if active else "docker-subtle")
                header.pack_start(badge, False, False, 0)
                header.pack_start(self.label(name, "docker-container-name"), True, True, 0)
                card.pack_start(header, False, False, 0)
                card.pack_start(self.label(image, "docker-subtle"), False, False, 0)
                if active:
                    cpu_label = f"{cpu:.1f}%" if cpu is not None else "\u2014"
                    ram_label = memory_label(used) if used is not None else "\u2014"
                    detail = f"CPU {cpu_label}  \u00b7  {ram_label}"
                else:
                    detail = row["Status"]
                card.pack_start(self.label(detail, "docker-detail"), False, False, 0)
                card.set_tooltip_text(f"{name}  \u00b7  {image}\n{row['Status']}")
                grid.attach(card, index % 2, index // 2, 1, 1)
            self.content.pack_start(grid, False, False, 0)
            remaining = len(containers) - MAX_CARDS
            if remaining > 0:
                self.content.pack_start(self.label(f"\u8fd8\u6709 {remaining} \u4e2a\u5bb9\u5668", "docker-subtle"), False, False, 0)
        self.content.show_all()
