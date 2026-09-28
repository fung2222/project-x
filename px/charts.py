"""Chart images for Telegram (sendPhoto) and the site.

Uses Pillow when installed (Hermes's venv has it: labels + title); otherwise a
dependency-free PNG writer draws the same line chart without text (numbers go
in the caption). Output: PNG file path."""
import os
import struct
import zlib

W, H, PAD = 900, 420, 40


def _scale(vals, lo, hi, a, b):
    if hi == lo:
        return [(a + b) / 2 for _ in vals]
    return [a + (v - lo) / (hi - lo) * (b - a) for v in vals]


def _points(series_list):
    allv = [v for s in series_list for v in s if v is not None]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    out = []
    for s in series_list:
        n = len(s)
        xs = [PAD + i * (W - 2 * PAD) / max(1, n - 1) for i in range(n)]
        ys = _scale(s, lo, hi, H - PAD, PAD)
        out.append(list(zip(xs, ys)))
    return out, lo, hi


def _png_raw(path, lines, colors):
    px = bytearray(b"\xff" * (W * H * 3))

    def put(x, y, c):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 3
            px[i:i + 3] = bytes(c)

    for x in range(PAD, W - PAD):  # axes
        put(x, H - PAD, (200, 200, 200))
    for y in range(PAD, H - PAD):
        put(PAD, y, (200, 200, 200))
    for pts, col in zip(lines, colors):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
            for k in range(steps + 1):
                x = int(round(x0 + (x1 - x0) * k / steps))
                y = int(round(y0 + (y1 - y0) * k / steps))
                for dx in (0, 1):
                    for dy in (0, 1):
                        put(x + dx, y + dy, col)
    raw = b"".join(b"\x00" + bytes(px[y * W * 3:(y + 1) * W * 3]) for y in range(H))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)


def line_chart(path, series, labels, title="", colors=None):
    """series: list of equal-length value lists (None allowed -> carried forward)."""
    colors = colors or [(15, 118, 110), (148, 163, 184), (234, 88, 12)]
    clean = []
    for s in series:
        last, c = None, []
        for v in s:
            last = v if v is not None else last
            c.append(last if last is not None else next((x for x in s if x is not None), 0))
        clean.append(c)
    lines, lo, hi = _points(clean)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(img)
        d.line([(PAD, H - PAD), (W - PAD, H - PAD)], fill=(200, 200, 200))
        d.line([(PAD, PAD), (PAD, H - PAD)], fill=(200, 200, 200))
        for pts, col in zip(lines, colors):
            d.line(pts, fill=col, width=3)
        d.text((PAD, 10), title, fill=(30, 30, 30))
        d.text((4, PAD), f"{hi:.0f}", fill=(90, 90, 90))
        d.text((4, H - PAD - 10), f"{lo:.0f}", fill=(90, 90, 90))
        if labels:
            d.text((PAD, H - PAD + 8), str(labels[0]), fill=(90, 90, 90))
            d.text((W - PAD - 70, H - PAD + 8), str(labels[-1]), fill=(90, 90, 90))
        img.save(path, "PNG")
    except ImportError:
        _png_raw(path, lines, colors)
    return path


def equity_chart(history, path, spy_rebased=True):
    """Paper-book equity (USD) vs SPY rebased to the same start (grey)."""
    eq = [h.get("equity_usd") for h in history]
    labels = [h.get("date") for h in history]
    series = [eq]
    if spy_rebased and history and history[0].get("spy_close"):
        base_s, base_e = history[0]["spy_close"], eq[0]
        series.append([(h["spy_close"] / base_s * base_e) if h.get("spy_close") else None for h in history])
    return line_chart(path, series, labels, title="Project X paper equity (USD) vs SPY")
