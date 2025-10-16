#!/usr/bin/python
"""
run_p2p_matrix.py - produce VOACAP point-to-point prediction decks and run voacapl.

Patched: more consistent pathlib usage, safer subprocess invocation,
atomic file writes, defensive cleanup, and tuned concurrency.

Copyright 2021-2025 Jari Perkiömäki OH6BG

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""

from concurrent.futures import ThreadPoolExecutor
from math import floor
from pathlib import Path
from uuid import uuid4
import configparser
import datetime
from pygeodesy.dms import latDMS, lonDMS
import subprocess
import sys
import os
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def latlon2loc(lat, lon, precision=3):
    """
    Construct Maidenhead grid locator from latitude and longitude
    """
    A = ord("A")
    a = divmod(lon + 180, 20)
    b = divmod(lat + 90, 10)
    astring = chr(A + int(a[0])) + chr(A + int(b[0]))
    lon = a[1] / 2.0
    lat = b[1]
    i = 1

    while i < precision:
        i += 1
        a = divmod(lon, 1)
        b = divmod(lat, 1)
        if not (i % 2):
            astring += str(int(a[0])) + str(int(b[0]))
            lon = 24 * a[1]
            lat = 24 * b[1]
        else:
            astring += chr(A + int(a[0])) + chr(A + int(b[0]))
            lon = 10 * a[1]
            lat = 10 * b[1]

    if len(astring) >= 6:
        astring = astring[:4] + astring[4:6].lower() + astring[6:]

    return astring.upper()


def get_ssn(year, month):
    """
    Read Smoothed Sunspot Number from ssn_file (Path).
    Returns an integer SSN or -1 if not found.
    """
    if ssn_file.is_file():
        myssn = f"{year} {month:02}"
        ssn_val = -1
        try:
            with ssn_file.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if myssn in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            ssn_val = parts[4]
                            try:
                                ssn_val = float(ssn_val)
                                # reduce forecasted future months slightly (original behaviour)
                                if year >= datetime.datetime.utcnow().year:
                                    ssn_val = round_half_up(ssn_val * 0.7)
                            except Exception:
                                ssn_val = -1
                        break
        except Exception as e:
            logging.warning("Could not read SSN file %s: %s", ssn_file, e)
            return -1
        try:
            return int(ssn_val)
        except Exception:
            return -1
    else:
        return -1


def round_half_up(n, decimals=0):
    multiplier = 10**decimals
    return floor(n * multiplier + 0.5) / multiplier


def make_voacap_predictions(freq):
    """
    For the provided frequency (string), assemble the voacapl input deck,
    ensure a run directory exists, write the .voa deck and run voacapl.
    """
    # Antenna mapping (strings taken from config)
    ANT_MAP = {
        "3.500": (txant80, rxant80),
        "5.300": (txant60, rxant60),
        "7.100": (txant40, rxant40),
        "10.100": (txant30, rxant30),
        "14.100": (txant20, rxant20),
        "18.100": (txant17, rxant17),
        "21.200": (txant15, rxant15),
        "24.900": (txant12, rxant12),
        "28.200": (txant10, rxant10),
    }
    txantenna, rxantenna = ANT_MAP.get(freq, (txant10, rxant10))

    # Precompute repeated strings for the hours block
    hours = [((start_time + i) % 24) for i in range(time_range)]
    month_list_s = "Months   :" + "".join(f"{month:>7.2f}" for _ in hours)
    ssn_list_s = "Ssns     :" + "".join(f"{ssn:>7}" for _ in hours)
    hour_list_s = "Hours    :" + "".join(f"{h:>7}" for h in hours)
    freq_list_s = "Freqs    :" + "".join(f"{freq:>7}" for _ in hours)

    voa_infile = f"cap_{float(freq):06.3f}.voa"
    logging.info("Processing %s MHz ...", freq)

    input_deck = (
        "Model    :VOACAP\n"
        "Colors   :Black    :Blue     :Ignore   :Ignore   :Red      :Black with shading\n"
        "Cities   :Receive.cty\n"
        "Nparms   :    1\n"
        "Parameter:REL      0\n"
        f"Transmit : {tlat:>6}   {tlon:>7}   {txname:<20} {path_flag}\n"
        f"Pcenter  : {tlat:>6}   {tlon:>7}   {txname:<20}\n"
        "Area     :    -180.0     180.0     -90.0      90.0\n"
        f"Gridsize :  {gridsize:>3}    1\n"
        f"Method   :   {method}\n"
        "Coeffs   :CCIR\n"
        f"{month_list_s}\n"
        f"{ssn_list_s}\n"
        f"{hour_list_s}\n"
        f"{freq_list_s}\n"
        f"System   :  {noise:>3}     {mintoa:.2f}   90   {mode:>2}     3.000     0.100\n"
        f"Fprob    : 1.00 1.00 1.00 {es:.2f}\n"
        f"Rec Ants :[voaant/{rxantenna:<14}]  gain=   0.0   0.0\n"
        f"Tx Ants  :[voaant/{txantenna:<14}]  0.000  -1.0   {power:>8.4f}\n"
    )

    # create prediction directory structure
    rundir = pdir / str(year) / months_list[month - 1] / freq
    try:
        rundir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.error("Cannot create directory %s: %s", rundir, e)
        return

    # write the .voa input deck atomically
    voa_path = rundir / voa_infile
    try:
        tmp = rundir / (voa_infile + ".tmp")
        tmp.write_text(input_deck, encoding="utf-8")
        tmp.replace(voa_path)
    except Exception as e:
        logging.error("Failed to write %s: %s", voa_path, e)
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return

    # construct voacapl args as a list and run the process
    voacapl_exe = Path(voacapl_bin)
    if not voacapl_exe.exists():
        logging.error("voacapl binary not found: %s", voacapl_exe)
        return

    args = [
        str(voacapl_exe),
        f"--run-dir={str(rundir)}",
        "--absorption-mode=a",
        "-s",
        str(itshfbc_dir),
        "area",
        "calc",
        voa_infile,
    ]

    try:
        cp = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=240,
            check=True,
            text=True,
            cwd=str(rundir),
        )
        logging.debug("voacapl stdout: %s", cp.stdout)
    except subprocess.CalledProcessError as e:
        logging.error("voacapl failed (rc=%s) for %s: %s", e.returncode, freq, e.stderr)
        return
    except subprocess.TimeoutExpired as e:
        logging.error("voacapl timed out for %s: %s", freq, e)
        return
    except Exception as e:
        logging.error("Error running voacapl for %s: %s", freq, e)
        return

    # best-effort cleanup of temp files created by voacapl
    try:
        tmp_file = rundir / "type14.tmp"
        if tmp_file.exists():
            tmp_file.unlink()
    except Exception:
        pass

    for p in rundir.glob("*.da*"):
        try:
            p.unlink()
        except Exception:
            pass

    logging.info("Finished %s MHz", freq)


# -----------------------
# Setup configuration / paths
# -----------------------
pre_id = str(uuid4().fields[-1])[:8]
base_dir = Path("/home/user/voa/predictions")
pdir = base_dir / str(pre_id)
# ensure base prediction dir exists
try:
    pdir.mkdir(parents=True, exist_ok=True)
except Exception as e:
    logging.error("Cannot create base prediction directory %s: %s", pdir, e)
    sys.exit(1)

# Configure the voacapl binary and supporting paths
voacapl_bin = "/usr/local/bin/voacapl"
itshfbc_dir = Path("/home/user/itshfbc")
ssn_path = Path("/home/user/voa")
ssn_file = ssn_path / "ssn.txt"

# read configuration
config = configparser.ConfigParser()
config.read("voacap.ini")

txlat = float(config["default"]["txlat"])
txlon = float(config["default"]["txlon"])
power = float(config["default"]["power"])
mode = int(config["default"]["mode"])
es = float(config["default"]["es"])
method = int(config["default"]["method"])
mintoa = float(config["default"]["mintoa"])
noise = int(config["default"]["noise"])
gridsize = int(config["default"]["gridsize"])
path_flag = config["default"]["path"]
flist = config["frequency"]["flist"].split()
months_list = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

txant80 = config["antenna"]["txant80"]
txant60 = config["antenna"]["txant60"]
txant40 = config["antenna"]["txant40"]
txant30 = config["antenna"]["txant30"]
txant20 = config["antenna"]["txant20"]
txant17 = config["antenna"]["txant17"]
txant15 = config["antenna"]["txant15"]
txant12 = config["antenna"]["txant12"]
txant10 = config["antenna"]["txant10"]

rxant80 = config["antenna"]["rxant80"]
rxant60 = config["antenna"]["rxant60"]
rxant40 = config["antenna"]["rxant40"]
rxant30 = config["antenna"]["rxant30"]
rxant20 = config["antenna"]["rxant20"]
rxant17 = config["antenna"]["rxant17"]
rxant15 = config["antenna"]["rxant15"]
rxant12 = config["antenna"]["rxant12"]
rxant10 = config["antenna"]["rxant10"]

# interactive inputs
print(
    "Create Point-to-Point VOACAP prediction matrix.\n"
    "Copyright 2025 Jari Perkiömäki OH6BG.\n"
)

run_years = []
while not len(run_years):
    try:
        run_years = input("Enter year(s): ").split()
        run_years = [int(x) for x in run_years if x.isdigit()]
        run_years = sorted(list(set([x for x in run_years if 2021 <= x <= 2100])))
    except ValueError:
        run_years = []

run_months = []
while not len(run_months):
    try:
        run_months = input("Enter month number(s) (1..12): ").split()
        run_months = [int(x) for x in run_months if x.isdigit()]
        run_months = sorted(list(set([x for x in run_months if 1 <= x <= 12])))
    except ValueError:
        run_months = []

start_time = -1
while not 0 <= start_time <= 23:
    try:
        start_time = int(input("Enter start time UTC (0..23): "))
    except ValueError:
        start_time = -1

time_range = 0
while not 1 <= time_range <= 24:
    try:
        time_range = int(input("Enter time range in hours (1..24): "))
    except ValueError:
        time_range = 0

txname = latlon2loc(txlat, txlon)
tlat = latDMS(txlat, form="deg")  # for input decks
tlon = lonDMS(txlon, form="deg")

# iterate years/months and run predictions
for year in run_years:
    for month in run_months:
        ssn = int(get_ssn(year, month))
        # prompt if SSN missing or out of expected range
        while not 0 <= ssn <= 300:
            try:
                ssn = int(
                    input(
                        f"\nEnter sunspot number (SSN) for {months_list[month - 1]} {year}: "
                    )
                )
            except ValueError:
                ssn = -1

        print(f"\nSSN for {months_list[month - 1]} {year}: {ssn}\n")

        # thread count: voacapl spawns native work; keep a modest concurrency
        max_workers = min((os.cpu_count() or 1), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # pass frequency strings as provided in flist
            futures = [executor.submit(make_voacap_predictions, f) for f in flist]
            for fut in futures:
                try:
                    fut.result()
                except Exception as e:
                    logging.error("Task failed: %s", e)

print(f"\nOutput directory: {pdir}")
