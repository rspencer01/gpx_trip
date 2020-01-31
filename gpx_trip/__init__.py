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

import hashlib
import logging
from math import cos, sin

import cairo

from geopy import distance, exc, geocoders

import geotiler

import gpxpy

import pandas as pd

from sklearn.mixture import GaussianMixture

import traces

logger = logging.getLogger(__name__)


def extract_segment(input_file):
    """Extract the single list of points from the file."""
    gpxin = gpxpy.parse(input_file)
    assert len(gpxin.tracks) == 1, "Input file must have a single track"
    track = gpxin.tracks[0]
    assert len(track.segments) == 1, "Input track must have a single segment"
    return track.segments[0]


def get_extent(segment):
    """Find the extent of the segment for map rendering."""
    lats = [p.latitude for p in segment.points]
    lons = [p.longitude for p in segment.points]
    return (min(lons), min(lats), max(lons), max(lats))


def extract_trips(segment, stops):
    """Find the trips between stops."""
    num_stops = len(stops)

    dat = pd.DataFrame(
        [
            {"timestamp": p.time, "lat": p.latitude, "lon": p.longitude}
            for p in segment.points
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
    for i in range(1, len(stop) - 1):
        if stop[i - 1] == stop[i + 1]:
            stop[i] = stop[i - 1]
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
    segment = extract_segment(input_file)
    logger.info("Extracting stops")
    stops = extract_stops(segment, predefined_stops, geocode)
    logger.info("Extracting trips")
    trips = extract_trips(segment, stops)
    trips.update({"stops": stops, "extent": get_extent(segment), "segment": segment})
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
    for pt in info["segment"].points:
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


def extract_stops(segment, predefined_stops=[], geocode=True):
    """Extract likely stop locations from the track."""
    lats = traces.TimeSeries([(p.time, p.latitude) for p in segment.points])
    lons = traces.TimeSeries([(p.time, p.longitude) for p in segment.points])
    dat = pd.DataFrame(lats.moving_average(300, pandas=True), columns=["lat"])
    dat["lon"] = lons.moving_average(300, pandas=True)

    lst = 0
    clss = None
    kmlast = None
    for n in range(1, 20):
        kmeans = GaussianMixture(n, random_state=0)
        kmeans.fit(dat[["lat", "lon"]])
        y_kmeans = kmeans.predict(dat[["lat", "lon"]])
        if kmeans.bic(dat[["lat", "lon"]]) > lst:
            break
        clss = y_kmeans
        kmlast = kmeans
        lst = kmeans.bic(dat[["lat", "lon"]])
    y_kmeans = clss
    kmeans = kmlast

    stops = [
        p
        for n, p in enumerate(kmeans.means_)
        if kmeans.bic(dat.iloc[y_kmeans == n][["lat", "lon"]]) < -30
    ]
    stops_dict = []
    if geocode:
        geocoder = geocoders.Photon()
    for stop in stops:
        for predefined_stop in predefined_stops:
            if (
                distance.distance(
                    stop, (predefined_stop["lat"], predefined_stop["lon"])
                ).meters
                < 90
            ):
                location_name = short_location_name = predefined_stop["name"]
                emoji_name = predefined_stop["emoji_name"]
                break
        else:
            emoji_name = ''
            try:
                if not geocode:
                    raise exc.GeocoderTimedOut
                location_name = geocoder.reverse("{}, {}".format(*stop)).address
                short_location_name = " ".join(location_name.split(",")[:2])
            except (exc.GeocoderTimedOut, exc.GeocoderServiceError):
                location_name = None
                short_location_name = hashlib.sha256(
                    str(stop).encode("utf-8")
                ).hexdigest()[:5]
        stops_dict.append(
            {
                "short_name": short_location_name,
                "name": location_name,
                "emoji_name": emoji_name,
                "lat": stop[0],
                "lon": stop[1],
            }
        )
    return stops_dict
