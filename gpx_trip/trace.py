from typing import Tuple

import gpxpy


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
