#!/usr/bin/python

"""

Copyright 2021 Jari Perkiömäki OH6BG

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""

import concurrent.futures
from math import floor
from pathlib import Path
from uuid import uuid4
import configparser
import datetime
from pygeodesy.sphericalTrigonometry import LatLon
from pygeodesy.dms import latDMS, lonDMS
import shlex
import struct
import subprocess
import sys


def latlon2loc(lat, lon, precision=3):
    """
    Construct Maidenhead grid locator from latitude and longitude
    """
    A = ord('A')
    a = divmod(lon + 180, 20)
    b = divmod(lat + 90, 10)
    astring = chr(A + int(a[0])) + chr(A + int(b[0]))
    lon = a[1] / 2.
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
    Read Smoothed Sunspot Number from file
    """
    if ssn_file.is_file():
        myssn = ' '.join([str(year), f"{month:02}"])
        ssn = -1
        for line in open(ssn_file):
            if myssn in line:
                ssn = line.split()[4]
                if year >= datetime.datetime.utcnow().year:
                    ssn = round_half_up(float(ssn) * 0.7)
                else:
                    ssn = float(ssn)
                break
        return f"{ssn:.0f}"
    else:
        return -1


def round_half_up(n, decimals=0):
    multiplier = 10 ** decimals
    return floor(n * multiplier + 0.5) / multiplier


def make_voacap_predictions(freq):
    """
    Collect input, create input decks, run voacapl
    """
    month_list = "Months   :"
    ssn_list = "Ssns     :"
    hour_list = "Hours    :"
    freq_list = "Freqs    :"

    if freq == "3.500":
        txantenna = txant80
        rxantenna = rxant80
    elif freq == "5.300":
        txantenna = txant60
        rxantenna = rxant60
    elif freq == "7.100":
        txantenna = txant40
        rxantenna = rxant40
    elif freq == "10.100":
        txantenna = txant30
        rxantenna = rxant30
    elif freq == "14.100":
        txantenna = txant20
        rxantenna = rxant20
    elif freq == "18.100":
        txantenna = txant17
        rxantenna = rxant17
    elif freq == "21.200":
        txantenna = txant15
        rxantenna = rxant15
    elif freq == "24.900":
        txantenna = txant12
        rxantenna = rxant12
    elif freq == "28.200":
        txantenna = txant10
        rxantenna = rxant10
    else:
        txantenna = "d10m.ant"
        rxantenna = "d10m.ant"

    for i in range(start_time, start_time + time_range):
        tm = i % 24
        month_list += f"{month:>7.2f}"
        ssn_list += f"{ssn:>7}"
        hour_list += f"{tm:>7}"
        freq_list += f"{freq:>7}"

    voa_infile = f"cap_{float(freq):06.3f}.voa"
    print(f"Processing {freq:>6} MHz...")
    input_deck = ("Model    :VOACAP\n"
                  "Colors   :Black    :Blue     :Ignore   :Ignore   :Red      :Black with shading\n"
                  "Cities   :Receive.cty\n"
                  "Nparms   :    1\n"
                  "Parameter:REL      0\n"
                  f"Transmit : {tlat:>6}   {tlon:>7}   {txname:<20} {path}\n"
                  f"Pcenter  : {tlat:>6}   {tlon:>7}   {txname:<20}\n"
                  "Area     :    -180.0     180.0     -90.0      90.0\n"
                  f"Gridsize :  {gridsize:>3}    1\n"
                  f"Method   :   {method}\n"
                  "Coeffs   :CCIR\n"
                  f"{month_list}\n"
                  f"{ssn_list}\n"
                  f"{hour_list}\n"
                  f"{freq_list}\n"
                  f"System   :  {noise:>3}     {mintoa:.2f}   90   {mode:>2}     3.000     0.100\n"
                  f"Fprob    : 1.00 1.00 1.00 {es:.2f}\n"
                  f"Rec Ants :[voaant/{rxantenna:<14}]  gain=   0.0   0.0\n"
                  f"Tx Ants  :[voaant/{txantenna:<14}]  0.000  -1.0   {power:>8.4f}\n")

    # create prediction directories by year, by month, by frequency
    rundir = pdir / str(year) / months_list[month-1] / freq
    if not rundir.exists():
        try:
            rundir.mkdir(parents=True, exist_ok=True)
        except:
            print('[ERROR] Cannot create directory for predictions.')
            sys.exit()

    (rundir / voa_infile).write_text(input_deck)
    voacapl_bin = f"/usr/local/bin/voacapl --run-dir={rundir} --absorption-mode=a -s"
    voacap_cmd = f"{voacapl_bin} {itshfbc_dir} area calc {voa_infile}"
    args = shlex.split(voacap_cmd)
    try:
        cp = subprocess.run(args, stderr=subprocess.PIPE,
                            stdout=subprocess.PIPE, timeout=240)
    except Exception as msg:
        print('[ERROR] While running voacapl:', msg)
        sys.exit()

    # delete temp files
    (rundir / "type14.tmp").unlink()

    for p in rundir.glob("*.da*"):
        p.unlink()


"""
Set up paths
"""
pre_id = str(uuid4().fields[-1])[:8]
base_dir = Path("/home/user/voa/predictions")
pdir = base_dir / str(pre_id)
itshfbc_dir = "/home/user/itshfbc"
ssn_path = Path("/home/user/voa")
ssn_file = ssn_path / "ssn.txt"

"""
Read input from voacap.ini
"""
config = configparser.ConfigParser()
config.read('voacap.ini')
txlat = float(config['default']['txlat'])
txlon = float(config['default']['txlon'])
power = float(config['default']['power'])
mode = int(config['default']['mode'])
es = float(config['default']['es'])
method = int(config['default']['method'])
mintoa = float(config['default']['mintoa'])
noise = int(config['default']['noise'])
gridsize = int(config['default']['gridsize'])
path = config['default']['path']
flist = config['frequency']['flist'].split()
months_list = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

txant80 = config['antenna']['txant80']
txant60 = config['antenna']['txant60']
txant40 = config['antenna']['txant40']
txant30 = config['antenna']['txant30']
txant20 = config['antenna']['txant20']
txant17 = config['antenna']['txant17']
txant15 = config['antenna']['txant15']
txant12 = config['antenna']['txant12']
txant10 = config['antenna']['txant10']

rxant80 = config['antenna']['rxant80']
rxant60 = config['antenna']['rxant60']
rxant40 = config['antenna']['rxant40']
rxant30 = config['antenna']['rxant30']
rxant20 = config['antenna']['rxant20']
rxant17 = config['antenna']['rxant17']
rxant15 = config['antenna']['rxant15']
rxant12 = config['antenna']['rxant12']
rxant10 = config['antenna']['rxant10']

# read years, months, start time, and time range from user
print("Create Point-to-Point VOACAP prediction matrix.\n"
      "Copyright 2021 Jari Perkiömäki OH6BG.\n")
run_years = []
while not len(run_years):
    try:
        run_years = input("Enter year(s): ").split()
        run_years = [int(x) for x in run_years if x.isdigit()]
        run_years = list(set(run_years))
        run_years = sorted([x for x in run_years if 2021 <= x <= 2022])
    except ValueError:
        run_years = []

run_months = []
while not len(run_months):
    try:
        run_months = input("Enter month number(s) (1..12): ").split()
        run_months = [int(x) for x in run_months if x.isdigit()]
        run_months = list(set(run_months))
        run_months = sorted([x for x in run_months if 1 <= x <= 12])
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

"""
Run predictions in multithreaded mode
"""
txname = latlon2loc(txlat, txlon)
tlat = latDMS(txlat, form="deg")  # for input decks
tlon = lonDMS(txlon, form="deg")

for year in run_years:
    for month in run_months:
        ssn = int(get_ssn(year, month))
        # no SSN found in file, ask for it
        while not 0 <= ssn <= 200:
            try:
                ssn = int(
                    input(f"\nEnter sunspot number (SSN) for {months_list[month-1]} {year}: "))
            except ValueError:
                ssn = -1

        print(f"\nSSN for {months_list[month-1]} {year}: {ssn}\n")

        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
            for _ in executor.map(make_voacap_predictions, flist):
                pass

print(f"\nOutput directory: {pdir}")
