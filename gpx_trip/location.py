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
from dataclasses import dataclass
from typing import Union, List
import hashlib

from geopy import distance, exc, geocoders
from loguru import logger


@dataclass
class Location:
    name: Union[str, None]
    short_name: str
    emoji_name: Union[str, None]
    country: Union[str, None]
    latitude: float
    longitude: float

    def distance_to(self, latitude: float, longitude: float):
        return distance.distance(
            (self.latitude, self.longitude), (latitude, longitude)
        ).meters

    @classmethod
    def from_coordinates(cls, latitude: float, longitude: float) -> "Location":
        return Location(
            name=None,
            short_name=hashlib.sha256(
                str("{:.4f} {:.4f}".format(latitude, longitude)).encode("utf-8")
            ).hexdigest()[:5],
            emoji_name=None,
            country=None,
            latitude=latitude,
            longitude=longitude,
        )

    @classmethod
    def from_geocoder(cls, geocoder, latitude: float, longitude: float) -> "Location":
        coded_address = geocoder.reverse("{}, {}".format(latitude, longitude))
        try:
            return Location(
                name=coded_address.address,
                short_name=" ".join(coded_address.address.split(",")[:2]),
                emoji_name=None,
                country=coded_address.raw.get("properties", {}).get("country", None),
                latitude=latitude,
                longitude=longitude,
            )
        except (exc.GeocoderTimedOut, exc.GeocoderServiceError):
            return Location.from_coordinates(latitude, longitude)

    @classmethod
    def from_dict(cls, d: dict) -> "Location":
        return Location(
            name=d.get("name", None),
            short_name=d.get("short_name", None) or d["name"],
            latitude=d["lat"],
            longitude=d["lon"],
            country=d.get("country", None),
            emoji_name=d.get("emoji_name", None),
        )


def get_location(
    latitude: float, longitude: float, geocode, predefined: List[Location]
) -> Location:
    logger.debug("Fitting location ({}) to predefined locations", latitude, longitude)
    for predefined_stop in predefined:
        dist = predefined_stop.distance_to(latitude, longitude)
        logger.debug("Stop {} is {}m away", predefined_stop.name, dist)
        # TODO(robert) Each stop should be able to specify a size
        if dist < 90:
            return predefined_stop
    if geocode:
        return Location.from_geocoder(geocoders.Photon(), latitude, longitude)
    return Location.from_coordinates(latitude, longitude)
