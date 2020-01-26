"""Setup for the `gpx_trip` package."""

from setuptools import setup

setup(
    name="gpx_trip",
    description="Extract stops and journeys from gpx traces",
    version="0.0.0dev",
    author="R. A. Spencer",
    author_email="general@robertandrewspencer.com",
    packages=["gpx_trip"],
    scripts=["bin/gpx_trip"],
    license="LICENCE.txt",
    long_description=open("README.md").read(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
    ],
    python_requires=">=3.5",
    install_requires=["gpxpy==1.3.5","pandas==0.25.3","traces==0.5.2"]
)
