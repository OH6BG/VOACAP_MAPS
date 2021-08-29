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
from natsort import natsorted, ns
from pathlib import Path
from math import acos, atan2, cos, pi, sin, sqrt


def calculate_km_deg(lat1, lon1, lat2, lon2):
    """
    Adapted from hamlocation.py (c) 2009 James Watson
    https://github.com/jawatson/pythonprop/blob/master/src/pythonprop/hamlocation.py
    """
    lo1 = -lon1 * pi / 180.0   # Convert degrees to radians
    la1 = lat1 * pi / 180.0
    lo2 = -lon2 * pi / 180.0
    la2 = lat2 * pi / 180.0

    # Get local earth radius
    radius = local_earth_radius(lat1)

    # Calculates distance in km
    km = acos(cos(la1) * cos(lo1) * cos(la2) * cos(lo2) + cos(la1) *
              sin(lo1) * cos(la2) * sin(lo2) + sin(la1) * sin(la2)) * radius

    # Calculates initial beam heading
    deg = atan2(sin(lo1 - lo2) * cos(la2), cos(la1) * sin(la2) -
                sin(la1) * cos(la2) * cos(lo1 - lo2)) / pi * 180
    if deg < 0:
        deg += 360
    return km, deg


def local_earth_radius(lat):
    """
    Adapted from hamlocation.py (c) 2009 James Watson
    https://github.com/jawatson/pythonprop/blob/master/src/pythonprop/hamlocation.py
    """
    # Hayford axes (1909)
    a = 6378.388  # earth major axis (km) (equatorial axis)
    b = 6356.912  # earth minor axis (km) (polar axis)
    esq = (a * a - b * b) / (a * a)  # calculates eccentricity^2
    la = lat * pi / 180.0  # convert latitude in radians
    sla = sin(la)  # calculates sinus of latitude
    return a * sqrt(1 - esq) / (1 - esq * sla * sla)


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
            km, deg = calculate_km_deg(txlat, txlon, float(d1), float(d2))
            rows.append(tuple(list(map(convert, (utc[:-2], month, freq[:-3], txlat, txlon, d1, d2, d3, d4, d5, d6,
                        d7, d8, d9, d10, d11, d12, d13, d14, d15, d16, d17, d18, d19, d20, d21, d22, d23, d24, d25, d26, km, deg)))))
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
    km real,
    deg real
)""")

c.executemany(
    "INSERT INTO points (utc,month,freq,txlat,txlon,rxlat,rxlon,muf,mode,tangle,delay,vhite,mufday,loss,dbu,sdbw,ndbw,snr,rpwrg,rel,mprob,sprob,tgain,rgain,snrxx,du,dl,siglw,sigup,pwrct,rangle,km,deg) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", rows)
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
