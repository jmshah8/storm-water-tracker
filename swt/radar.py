"""ODIM_H5 radar reader and grid projection (03_PHASE2_RADAR_PLAN.md step 2.2).

The Met Office UK composite holds a surface rain rate in mm/h on a 1 km British National Grid,
one frame every 15 minutes. Everything needed to read it is in the file's own attributes; nothing
about the grid is hard-coded.
"""
import numpy as np
import pyproj


def load_frame(path):
    """(rate_mm_per_h as float32 with NaN where there is no data, meta dict)."""
    import h5py

    with h5py.File(path, "r") as f:
        what = dict(f["/dataset1/data1/what"].attrs)
        raw = np.asarray(f["/dataset1/data1/data"][:], dtype="float32")
        gain = float(what.get("gain", 1.0))
        offset = float(what.get("offset", 0.0))
        nodata = float(what["nodata"]) if "nodata" in what else None
        undetect = float(what["undetect"]) if "undetect" in what else None
        meta = {
            "quantity": _text(what.get("quantity")),
            "gain": gain, "offset": offset, "nodata": nodata, "undetect": undetect,
            "where": {k: _value(v) for k, v in f["/where"].attrs.items()},
            "what": {k: _value(v) for k, v in f["/what"].attrs.items()},
            "dataset_what": {k: _value(v) for k, v in f["/dataset1/what"].attrs.items()},
            "origin": _text(f["/dataset1/how"].attrs.get("origin")) if "/dataset1/how" in f else None,
        }

    rate = raw * gain + offset
    if undetect is not None:
        rate = np.where(raw == undetect, 0.0, rate)
    if nodata is not None:
        rate = np.where(raw == nodata, np.nan, rate)
    return rate.astype("float32"), meta


def _text(value):
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def _value(value):
    value = _text(value)
    return value.item() if hasattr(value, "item") else value


def accum_15min(rate):
    """A 15-minute accumulation in mm from a rate in mm/h."""
    return rate / 4.0


class Grid:
    """Maps WGS84 coordinates to pixels using the file's own projection and corner attributes."""

    def __init__(self, where, origin="UPPER LEFT"):
        self.projdef = _text(where["projdef"])
        self.xsize, self.ysize = int(where["xsize"]), int(where["ysize"])
        self.xscale, self.yscale = float(where["xscale"]), float(where["yscale"])
        self.origin = (origin or "UPPER LEFT").upper()
        # always_xy=True keeps the order (lon, lat); without it pyproj expects (lat, lon) and every point
        # lands in the wrong place.
        self.transformer = pyproj.Transformer.from_crs("EPSG:4326", self.projdef, always_xy=True)
        self.ul_x, self.ul_y = self.transformer.transform(float(where["UL_lon"]), float(where["UL_lat"]))
        self.ll_x, self.ll_y = self.transformer.transform(float(where["LL_lon"]), float(where["LL_lat"]))
        # Rows run away from the upper-left corner: southwards when that corner is the northern one.
        self.row_sign = -1.0 if self.ul_y > self.ll_y else 1.0

    def to_pixel(self, lat, lon):
        """(row, col) of the pixel containing this point; may be outside the grid."""
        x, y = self.transformer.transform(lon, lat)
        col = int(np.floor((x - self.ul_x) / self.xscale))
        row = int(np.floor((y - self.ul_y) * self.row_sign / self.yscale))
        return row, col

    def in_bounds(self, row, col):
        return 0 <= row < self.ysize and 0 <= col < self.xsize
