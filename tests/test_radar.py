"""Tests for swt/radar.py on a synthetic 10x10 ODIM_H5 file (03_PHASE2_RADAR_PLAN.md step 2.2)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swt.radar import Grid, accum_15min, load_frame  # noqa: E402

# the real file's attributes (step 2.1), with a 10x10 grid
PROJDEF = "+proj=tmerc +lat_0=49 +lon_0=-2 +k=0.999601 +x_0=400000 +y_0=-100000 +ellps=airy +units=m"
WHERE = {"projdef": PROJDEF, "xsize": 10, "ysize": 10, "xscale": 1000.0, "yscale": 1000.0,
         "UL_lon": -1.0, "UL_lat": 52.0, "LL_lon": -1.0, "LL_lat": 51.91}
GAIN, OFFSET, NODATA, UNDETECT = 2.0, 1.0, -1.0, 0.0


@pytest.fixture
def synthetic(tmp_path):
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "synthetic.h5"
    raw = np.full((10, 10), 3.0, dtype="float32")
    raw[0, 0] = UNDETECT
    raw[1, 1] = NODATA
    with h5py.File(path, "w") as f:
        where = f.create_group("/where")
        for key, value in WHERE.items():
            where.attrs[key] = value
        f.create_group("/dataset1/how").attrs["origin"] = "UPPER LEFT"
        what = f.create_group("/dataset1/data1/what")
        for key, value in (("gain", GAIN), ("offset", OFFSET), ("nodata", NODATA), ("undetect", UNDETECT),
                           ("quantity", "RATE")):
            what.attrs[key] = value
        f.create_group("/what").attrs["date"] = "20260916"
        f.create_group("/dataset1/what").attrs["starttime"] = "115842"
        f["/dataset1/data1"].create_dataset("data", data=raw)
    return path


def test_gain_offset_nodata_undetect(synthetic):
    rate, meta = load_frame(synthetic)
    assert meta["quantity"] == "RATE"
    assert (meta["gain"], meta["offset"], meta["nodata"], meta["undetect"]) == (GAIN, OFFSET, NODATA, UNDETECT)
    assert rate[5, 5] == pytest.approx(3.0 * GAIN + OFFSET)   # physical = raw * gain + offset
    assert rate[0, 0] == 0.0                                   # undetect is dry, not missing
    assert np.isnan(rate[1, 1])                                # nodata is missing
    assert np.isnan(rate).sum() == 1


def test_accum_15min():
    assert accum_15min(np.array([0.0, 4.0, 10.0])).tolist() == [0.0, 1.0, 2.5]


def test_corners_map_to_corner_pixels():
    grid = Grid(WHERE)
    assert grid.to_pixel(WHERE["UL_lat"], WHERE["UL_lon"]) == (0, 0)
    # the lower-right corner of the grid: 10 km east and 10 km south of the upper-left corner
    lr_lon, lr_lat = grid.transformer.transform(grid.ul_x + 9.5 * grid.xscale, grid.ul_y - 9.5 * grid.yscale,
                                                direction="INVERSE")
    assert grid.to_pixel(lr_lat, lr_lon) == (grid.ysize - 1, grid.xsize - 1)
    assert grid.in_bounds(0, 0) and grid.in_bounds(9, 9)
    assert not grid.in_bounds(-1, 0) and not grid.in_bounds(0, 10) and not grid.in_bounds(10, 0)


def test_rows_run_north_to_south():
    grid = Grid(WHERE)
    north = grid.to_pixel(WHERE["UL_lat"] - 0.01, WHERE["UL_lon"] + 0.01)
    south = grid.to_pixel(WHERE["UL_lat"] - 0.05, WHERE["UL_lon"] + 0.01)
    assert south[0] > north[0]
