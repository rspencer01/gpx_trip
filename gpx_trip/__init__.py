# Copyright (C) 2020  R. A. Spencer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Find trips from a gpx track."""

import logging
from math import cos, sin

import cairo

from geopy import distance, exc, geocoders

import geotiler

import pandas as pd

from sklearn.mixture import GaussianMixture

import traces

from .trace import Trace

logger = logging.getLogger(__name__)


def extract_trips(trace, stops):
    """Find the trips between stops."""
    num_stops = len(stops)

    dat = pd.DataFrame(
        [
            {"timestamp": p.time, "lat": p.latitude, "lon": p.longitude}
            for p in trace.segment.points
        ]
    )
    stop = []
    for t in dat.index:
        for n, s in enumerate(stops):
            if (
                distance.distance(
                    (dat.iloc[t].lat, dat.iloc[t].lon), (s["lat"], s["lon"])
                ).meters
                < 40
            ):
                stop.append(n)
                break
        else:
            stop.append(-1)
    # Smooth out errors
    for i in range(2, len(stop) - 1):
        if stop[i - 2] == stop[i + 1]:
            stop[i] = stop[i - 2]
            stop[i - 1] = stop[i - 2]
    dat["stop"] = stop

    time_at_stops = dict(
        [(i, dat["timestamp"].diff()[dat["stop"] == i].sum()) for i in range(num_stops)]
    )
    trip_start = 1
    while dat["stop"][trip_start] != -1:
        trip_start += 1
    trips = []
    while trip_start < len(dat) - 1:
        trip_end = trip_start
        while (
            trip_end < len(dat) - 2
            and dat["stop"][trip_end + 1] == dat["stop"][trip_start]
        ):
            trip_end += 1
        trips.append(
            {
                "start": dat["timestamp"][trip_start],
                "end": dat["timestamp"][trip_end],
                "from": dat["stop"][trip_start - 1],
                "to": dat["stop"][trip_end + 1],
                "time": dat["timestamp"][trip_end] - dat["timestamp"][trip_start],
            }
        )
        trip_start = trip_end + 1
        while trip_start < len(dat) and dat["stop"][trip_start] != -1:
            trip_start += 1

    return {"time_at_stops": time_at_stops, "trips": trips}


def extract_info(input_file, predefined_stops=[], geocode=True):
    """Get all the information from the input file."""
    logger.info("Extracting segment")
    trace = Trace(input_file)
    logger.info("Extracting stops")
    stops = trace.extract_stops(predefined_stops, geocode)
    logger.info("Extracting trips")
    trips = extract_trips(trace, stops)
    trips.update({"stops": stops, "extent": trace.extent(), "segment": trace})
    return trips


def construct_trip_map(input_file, output_file, predefined_stops=[]):
    """Save an image of trip infos."""
    info = extract_info(input_file, predefined_stops, False)
    logger.info("Rendering image")

    mm = geotiler.Map(extent=info["extent"], size=(768, 768))
    width, height = mm.size

    img = geotiler.render_map(mm)

    buff = bytearray(img.convert("RGBA").tobytes("raw", "BGRA"))
    surface = cairo.ImageSurface.create_for_data(
        buff, cairo.FORMAT_ARGB32, width, height
    )
    cr = cairo.Context(surface)

    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_width(8)
    n = 0
    for pt in info["segment"].segment.points:
        cr.set_source_rgba(0.5, 0.0, 0.0, 0.9)
        cr.arc(*mm.rev_geocode((pt.longitude, pt.latitude)), 3, 0, 2 * 3.1415)
        cr.close_path()
        cr.fill()
        n += 1

    for n, p in enumerate(info["stops"]):
        cr.set_source_rgba(0.5 + 0.5 * cos(n * 4.0), 0.5 + 0.5 * sin(n * 9.0), 0.0, 0.9)
        cr.arc(*mm.rev_geocode((p["lon"], p["lat"])), 10, 0, 2 * 3.1415)
        cr.close_path()
        cr.stroke()
    surface.write_to_png(open(output_file, "wb"))
