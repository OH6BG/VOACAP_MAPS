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
import struct
import time
import sqlite3
import threading
from natsort import natsorted, ns  # https://pypi.org/project/natsort/
from pathlib import Path
from pygeodesy.sphericalTrigonometry import LatLon
from pygeodesy.dms import parseDMS2


def get_midpoint(lat1, lon1, lat2, lon2):
    a = LatLon(lat1, lon1)
    b = LatLon(lat2, lon2)
    mplat, mplon = a.midpointTo(b).toStr().split(",")
    return parseDMS2(mplat, mplon)


def get_distance_bearing(lat1, lon1, lat2, lon2):
    a = LatLon(lat1, lon1)
    b = LatLon(lat2, lon2)
    km = a.distanceTo(b) / 1000
    deg = a.initialBearingTo(b)
    return km, deg


def maiden2latlon(loc):
    lat = (ord(loc[1:2]) - 65) * 10 - 90 + \
        (ord(loc[3:4]) - 48) + (ord(loc[5:6]) - 65) / 24 + 1 / 48
    lon = (ord(loc[0:1]) - 65) * 20 - 180 + (ord(loc[2:3]) -
                                             48) * 2 + (ord(loc[4:5]) - 65) / 12 + 1 / 24
    return lat, lon


def convert(s):
    try:
        return float(s)
    except:
        try:
            return s.decode().strip()
        except:
            return s.strip()


def collect_data(line):
    global txlat
    global txlon
    global utc
    global month
    global freq

    with global_lock:

        if line.startswith(b'VOACAPL'):
            return

        if line.endswith(b'PWRCTANGLER'):
            return

        # KP03QA [1/4 wl Gud] 1.5kW -1deg 24ut 3.500MHz Oct 25ssn
        if line.endswith(b'ssn'):
            data_line = line.decode().strip().split("]")
            _, _, utc, freq, month, _ = data_line[1].strip().split()
            grid = data_line[0].split("[")[0].strip()
            txlat, txlon = maiden2latlon(grid)

        try:
            (_,
                _,
                d1,
                d2,
                d3,
                d4,
                d5,
                d6,
                d7,
                d8,
                d9,
                d10,
                d11,
                d12,
                d13,
                d14,
                d15,
                d16,
                d17,
                d18,
                d19,
                d20,
                d21,
                d22,
                d23,
                d24,
                d25,
                d26) = struct.unpack(col_format, line)
            midlat, midlon = get_midpoint(txlat, txlon, d1, d2)
            km, deg = get_distance_bearing(txlat, txlon, d1, d2)
            rows.append(tuple(list(map(convert, (utc[:-2], month, freq[:-3], txlat, txlon, d1, d2, d3, d4, d5, d6,
                        d7, d8, d9, d10, d11, d12, d13, d14, d15, d16, d17, d18, d19, d20, d21, d22, d23, d24, d25, d26, midlat, midlon, km, deg)))))
        except:
            return


"""
Set up paths
"""
print("Store output from VOACAP VG files to SQlite3 database.\n"
      "Copyright 2021 Jari Perkiömäki OH6BG.\n")

col_format = '3s3s10s10s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s6s'
rows = []
txlat, txlon, utc, month, freq = -1, -1, -1, -1, -1

global_lock = threading.Lock()
INPUT_PATH = Path(input("Enter root path to VG files: ").strip())
print()
infiles = list(INPUT_PATH.rglob('*.voa'))
infiles = natsorted(infiles, alg=ns.PATH)

for f in infiles:
    month_processed = str(f).split("/")[-3]
    for fn in sorted(f.parent.glob("*.vg*")):
        start_time = time.time()
        lines = open(fn, 'rb').read().splitlines()

        with concurrent.futures.ThreadPoolExecutor(max_workers=170) as executor:
            for _ in executor.map(collect_data, lines):
                pass

        parse_freq, parse_utc = str(fn).split("cap_")[1].rsplit(".", 1)
        parse_utc = parse_utc.split("vg")[1]
        end_time = time.time()
        print(
            f"Parsing {month_processed} {float(parse_freq):>4} MHz {int(parse_utc):02} UTC: {end_time - start_time:.1f} secs")

database_name = input("\nEnter database name: ").strip()
con = sqlite3.connect(database_name)
c = con.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS points (
    utc integer,
    month text,
    freq real,
    txlat real,
    txlon real,
    rxlat real,
    rxlon real,
    muf real,
    mode text,
    tangle real,
    delay real,
    vhite real,
    mufday real,
    loss real,
    dbu real,
    sdbw real,
    ndbw real,
    snr real,
    rpwrg real,
    rel real,
    mprob real,
    sprob real,
    tgain real,
    rgain real,
    snrxx real,
    du real,
    dl real,
    siglw real,
    sigup real,
    pwrct real,
    rangle real,
    midlat real,
    midlon real,
    km real,
    deg real
)""")

c.executemany(
    "INSERT INTO points (utc,month,freq,txlat,txlon,rxlat,rxlon,muf,mode,tangle,delay,vhite,mufday,loss,dbu,sdbw,ndbw,snr,rpwrg,rel,mprob,sprob,tgain,rgain,snrxx,du,dl,siglw,sigup,pwrct,rangle,midlat,midlon,km,deg) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", rows)
con.commit()

print(f"\nTEST: Reading results from database '{database_name}'...\n")
with con:
    c.execute(
        f"SELECT DISTINCT utc, month, freq, AVG(mufday), AVG(sdbw), AVG(snr), AVG(rel), AVG(snrxx), AVG(rxlat), AVG(rxlon), AVG(km), AVG(deg), mode FROM points WHERE utc = 1 and snr >= 19 and km BETWEEN 6500 and 8000 and deg BETWEEN 40 and 60 GROUP BY utc, month, freq")
    result = c.fetchall()
    if result:
        print(f"UT MON   FREQ Mdy   SDBW  SNR50    REL  SNR90  RXLAT   RXLON     KM    DEG  MODE")
        for r in result:
            print(f"{r[0]:02d} {r[1]} {r[2]:>6.3f} {int(r[3]*100):>3} {r[4]:>6.1f} {r[5]:>6.1f}  {r[6]:.3f} {r[7]:>6.1f} {r[8]:>6.1f}  {r[9]:>6.1f}  {r[10]:>5.0f}    {r[11]:>3.0f}  {r[12]:>4}")
con.close()

print(f"\nDatabase complete: {database_name}")
