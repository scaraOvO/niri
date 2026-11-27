from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from math import asinh, cos, floor, pi, radians, sin, tan
from pathlib import Path
import time
from urllib.request import Request, urlopen

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from weather import weather_condition

MAP_POOL = ThreadPoolExecutor(max_workers=1)


def label(value="", style=None):
    widget = Gtk.Label(label=value, xalign=0)
    widget.set_line_wrap(True)
    if style:
        widget.get_style_context().add_class(style)
    return widget


def row(*widgets):
    box = Gtk.Box(spacing=9)
    for widget in widgets:
        box.pack_start(widget, False, False, 0)
    return box


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


class WeatherView:
    def __init__(self, result):
        self.weather_result = result

    @staticmethod
    def put(container, *widgets):
        for widget in widgets:
            container.pack_start(widget, False, False, 0)

    def render(self, place, now, daily):
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
            if not active:
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
        task = MAP_POOL.submit(map_tiles, latitude, longitude)
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
