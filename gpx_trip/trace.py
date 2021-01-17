# Copyright (C) 2021  R. A. Spencer
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
from typing import Tuple, List

from geopy import distance, exc, geocoders

import gpxpy

from loguru import logger

import pandas as pd

from sklearn.mixture import GaussianMixture

import traces

from .location import Location


class Trace:
    def __init__(self, filename : str):
        logger.info("Constructing trace from {}", filename)
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

    def extract_stops(self, predefined_stops:List[Location]=[], geocode=True):
        """Extract likely stop locations from the track."""
        logger.debug("Extracting stops from trace")
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
        dat = dat.drop(["lat_shift", "lon_shift"], axis=1)

        # TODO(robert) Built-in 10 meter cutoff
        dat = dat[dat["dist"] < 10.0]

        logger.debug("Filtered to {} stationary points", len(dat))
        lst = 1e20
        clss = None
        kmlast = None
        # TODO(robert) Limit of at most 20 stops per trace
        for n in range(1, 20):
            kmeans = GaussianMixture(n, random_state=0)
            kmeans.fit(dat[["lat", "lon"]])
            y_kmeans = kmeans.predict(dat[["lat", "lon"]])
            fitness = kmeans.bic(dat[["lat", "lon"]])
            logger.debug("Fitting {} points has fitness {}", n, -fitness)
            if fitness > lst:
                break
            clss = y_kmeans
            kmlast = kmeans
            lst = fitness
        y_kmeans = clss
        kmeans = kmlast

        if kmlast is not None:
            stops = [
                p
                for n, p in enumerate(kmeans.means_)
                # TODO(robert) Hard-coded filtering on the BIC
                if kmeans.bic(dat.iloc[y_kmeans == n][["lat", "lon"]]) < -30
            ]
        else:
            stops = []

        stops_dict = []
        if geocode:
            geocoder = geocoders.Photon()
        for stop in stops:
            location = None
            logger.debug("Fitting stop {} to predefined stops", stop)
            for predefined_stop in predefined_stops:
                dist = predefined_stop.distance_to(*stop)
                logger.debug("Stop {} is {}m away", predefined_stop.name, dist)
                # TODO(robert) Each stop should be able to specify a size
                if dist < 90:
                    location = predefined_stop
                    break
            else:
                if geocoder is not None:
                    location = Location.from_geocoder(geocoder, *stop)
                else:
                    location = Location.from_coordinates(*stop)

            stops_dict.append(location)
        return stops_dict
