import hashlib
from typing import Tuple

from geopy import distance, exc, geocoders

import gpxpy

import pandas as pd

from sklearn.mixture import GaussianMixture

import traces


class Trace:
    def __init__(self, filename):
        gpxin = gpxpy.parse(filename)
        assert len(gpxin.tracks) == 1, "Input file must have a single track"
        track = gpxin.tracks[0]
        assert len(track.segments) == 1, "Input track must have a single segment"
        self.segment = track.segments[0]

    def extent(self) -> Tuple[float, float, float, float]:
        """Find the extent of the segment for map rendering."""
        lats = [p.latitude for p in self.segment.points]
        lons = [p.longitude for p in self.segment.points]
        return (min(lons), min(lats), max(lons), max(lats))

    def extract_stops(self, predefined_stops=[], geocode=True):
        """Extract likely stop locations from the track."""
        lats = traces.TimeSeries([(p.time, p.latitude) for p in self.segment.points])
        lons = traces.TimeSeries([(p.time, p.longitude) for p in self.segment.points])
        # TODO(robert): Built-in 5 minute average
        dat = pd.DataFrame(
            {
                "lat": lats.moving_average(300, pandas=True),
                "lon": lons.moving_average(300, pandas=True),
            }
        )
        # TODO(robert): Built-in 10 minute shift
        dat["lat_shift"] = dat["lat"].shift(2)
        dat["lon_shift"] = dat["lon"].shift(2)

        def distance_calculate(row):
            if row.lat_shift != row.lat_shift or row.lon_shift != row.lon_shift:
                return float("nan")
            return distance.distance(
                (row.lat, row.lon), (row.lat_shift, row.lon_shift)
            ).meters

        dat["dist"] = dat.apply(distance_calculate, axis=1)
        dat.drop(["lat_shift", "lon_shift"], axis=1)

        # TODO(robert) Built-in 10 meter cutoff
        dat = dat[dat["dist"] < 10.0]

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

        if kmlast is not None:
            stops = [
                p
                for n, p in enumerate(kmeans.means_)
                if kmeans.bic(dat.iloc[y_kmeans == n][["lat", "lon"]]) < -30
            ]
        else:
            stops = []

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
                    emoji_name = predefined_stop.get("emoji_name", "")
                    break
            else:
                emoji_name = ""
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
