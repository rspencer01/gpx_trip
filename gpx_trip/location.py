from dataclasses import dataclass
from typing import Union
import hashlib

from geopy import distance, exc


@dataclass
class Location:
    name: Union[str, None]
    short_name: str
    emoji_name: Union[str, None]
    country: Union[str, None]
    latitude: float
    longitude: float

    def distance_to(self, latitude: float, longitude: float):
        return distance.distance((self.latitude, self.longitude), (latitude, longitude)).meters

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
