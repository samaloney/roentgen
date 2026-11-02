"""
One-off script to download per-element photon cross-section tables from the NIST XCOM web
service (the same tabular download as the form's "Download data" button) and write them as
CSV files in the same format as ``roentgen/data/xcom`` (see extract_xcom.py).

NIST returns its standard energy grid plus absorption edges, with 4 significant figures.
Use compare_xcom.py to compare the result with the bundled data.

Usage:
    python scripts/download_xcom.py [--output DIR] [Z ...]    # default: all elements
"""

import argparse
import time
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np

from astropy.io import ascii
from astropy.table import Table

import roentgen

URL = "https://physics.nist.gov/cgi-bin/Xcom/data.pl"

DEFAULT_OUTPUT_DIR = (
    Path(__file__).parent.parent / "roentgen" / "data" / f"xcom_nist_{date.today():%Y-%m-%d}"
)

NAMES = dict(
    zip(*(ascii.read(roentgen._data_directory / "elements.csv")[c] for c in ("z", "name")))
)
# the table checkboxes NIST's form offers, in the order it returns the columns after the energy
NIST_COLUMNS = ["coherent", "incoherent", "photoelectric", "nuclear", "electron", "with", "without"]
COLUMNS = [
    "energy_kev",
    "coherent",
    "incoherent",
    "photoelectric",
    "pair_nuclear",
    "pair_electron",
    "total_with_coherent",
    "total_without_coherent",
]

HEADER_COMMENT = """\
# Data Source: NIST XCOM (https://physics.nist.gov/PhysRefData/Xcom/html/xcom1.html)
# Downloaded from the XCOM web service (scripts/download_xcom.py), values are
# given by NIST to 4 significant figures.
#
# energy_kev: photon energy, keV
# coherent, incoherent, photoelectric, pair_nuclear, pair_electron,
# total_with_coherent, total_without_coherent: cm2/g
#
# Valid from 1 keV to 1e8 keV. K/L/M-edges appear as duplicate energy rows
# (low-energy-side then high-energy-side value), same convention as
# roentgen's other NIST-sourced per-element data files.
"""


def download(z):
    """
    Fetch NIST's table for element ``z`` as an array of shape (n, 8): energy [MeV], coherent,
    incoherent, photoelectric, pair nuclear, pair electron, total with coherent, total without.
    """
    # the form's "Download data" request: the standard grid is returned when Energies is empty.
    # NIST's CGI only accepts a browser-style multipart body (curl's is rejected) and returns 403
    # for urllib's default User-Agent.
    fields = {"character": "bar", "Name": NAMES[z], "Method": 1, "ZNum": z, "OutOpt": "PIC",
              "NumAdd": 1, "Energies": "", "Output": "on", "WindowXmin": 0.001, "WindowXmax": 100000,
              **dict.fromkeys(NIST_COLUMNS, "on")}  # fmt: skip
    boundary = "----WebKitFormBoundaryroentgen"
    body = "".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
        for k, v in fields.items()
    )
    request = urllib.request.Request(
        URL,
        f"{body}--{boundary}--\r\n".encode(),
        headers={
            "User-Agent": "roentgen-download-xcom",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode()
    # bar-delimited rows of 8 numbers, after a 3 line header
    rows = [line.strip("|").split("|") for line in text.splitlines()[3:] if line.strip()]
    if not rows or any(len(row) != 8 for row in rows):
        raise RuntimeError(f"Unexpected NIST response for z={z}: {text[:200]!r}")
    return np.array(rows, dtype=float)


def main(zs, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for z in zs:
        data = download(z)
        table = Table(data, names=COLUMNS)
        table["energy_kev"] = np.round(data[:, 0] * 1e3, 9)  # MeV -> keV without float noise
        out_path = output_dir / f"z{z:02d}.csv"
        out_path.write_text(HEADER_COMMENT + f"# Element: {NAMES[z]} (z={z})\n")
        with open(out_path, "a") as f:
            table.write(f, format="ascii.csv")
        print(f"z={z:2d} {NAMES[z]:12s} -> {out_path.name} ({len(table)} points)")
        time.sleep(0.5)  # be polite to NIST


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("zs", nargs="*", type=int, help="atomic numbers (default: 1-92)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="output directory")
    args = parser.parse_args()
    main(args.zs or range(1, 93), args.output)
    print(f"Wrote element CSVs to {args.output}")
