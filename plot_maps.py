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
from pathlib import Path
from itertools import islice
import sys
import subprocess
import shlex

plot_base = "/home/user/pythonprop/src/pythonprop"
mufplot = f"{plot_base}/voaAreaPlot.py -f -d 1 -o"
relplot = f"{plot_base}/voaAreaPlot.py -f -d 2 -o"
snrplot = f"{plot_base}/voaAreaPlot.py -f -d 3 -o"
snr90plot = f"{plot_base}/voaAreaPlot.py -f -d 4 -o"
sdbwplot = f"{plot_base}/voaAreaPlot.py -f -d 5 -o"

print("Plot coverage maps from VOACAP VG files.\n"
"Copyright 2021 Jari Perkiömäki OH6BG.\n")

INPUT_PATH = Path(input("Enter root path to VG files: ").strip())
infiles = list(INPUT_PATH.rglob('*.voa'))


def plot_maps(f):
    prefix = "_".join(str(f.parent).split("/")[-3:])
    print(f"Processing {prefix.replace('_', ' ')}...")

    for vg in f.parent.glob("*.vg*"):
        vg_number = str(vg.suffix)[3:]

        with vg.open(mode='rb') as lines:
            for x in list(islice(lines, 1, 2)):
                # UTC used as part of filename
                utc = x.decode().split()[-4]

        # REL (Reliability), percentage of days when predicted SNR >= REQUIRED SNR
        # REQUIRED SNR is determined by the mode of transmit
        reldir = INPUT_PATH / 'REL'
        if not reldir.exists():
            try:
                reldir.mkdir(parents=True, exist_ok=True)
            except:
                print('[ERROR] Cannot create directory for REL maps: {reldir}')
                sys.exit()

        relplotcmd = f"{relplot} {reldir / f'{prefix}_REL_{utc.upper()}.png'} -v {vg_number} {f}"
        args = shlex.split(relplotcmd)
        try:
            cp = subprocess.run(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE, timeout=10)
        except Exception as msg:
            print("ERROR REL PLOT", msg)
            sys.exit()

        # SNR50 (Median Signal-to-Noise Ratio), achieved 50% of days in month
        snr50dir = INPUT_PATH / 'SNR50'
        if not snr50dir.exists():
            try:
                snr50dir.mkdir(parents=True, exist_ok=True)
            except:
                print('[ERROR] Cannot create directory for SNR50 maps: {snr50dir}')
                sys.exit()

        snrplotcmd = f"{snrplot} {snr50dir / f'{prefix}_SNR50_{utc.upper()}.png'} -v {vg_number} {f}"
        args = shlex.split(snrplotcmd)
        try:
            cp = subprocess.run(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE, timeout=10)
        except Exception as msg:
            print("ERROR SNR50 PLOT", msg)
            sys.exit()

        # SNR90 (Signal-to-Noise Ratio), achieved 90% of days in month
        snr90dir = INPUT_PATH / 'SNR90'
        if not snr90dir.exists():
            try:
                snr90dir.mkdir(parents=True, exist_ok=True)
            except:
                print('[ERROR] Cannot create directory for SNR90 maps: {snr90dir}')
                sys.exit()

        snr90plotcmd = f"{snr90plot} {snr90dir / f'{prefix}_SNR90_{utc.upper()}.png'} -v {vg_number} {f}"
        args = shlex.split(snr90plotcmd)
        try:
            cp = subprocess.run(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE, timeout=10)
        except Exception as msg:
            print("ERROR SNR90 PLOT", msg)
            sys.exit()

        # SDBW (Median Signal Power), achieved 50% of days in month
        sdbwdir = INPUT_PATH / 'SDBW'
        if not sdbwdir.exists():
            try:
                sdbwdir.mkdir(parents=True, exist_ok=True)
            except:
                print('[ERROR] Cannot create directory for SDBW maps: {sdbwdir}')
                sys.exit()

        sdbwplotcmd = f"{sdbwplot} {sdbwdir / f'{prefix}_SDBW_{utc.upper()}.png'} -v {vg_number} {f}"
        args = shlex.split(sdbwplotcmd)
        try:
            cp = subprocess.run(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE, timeout=10)
        except Exception as msg:
            print("ERROR SDBW PLOT", msg)
            sys.exit()


with concurrent.futures.ThreadPoolExecutor(max_workers=90) as executor:
    for _ in executor.map(plot_maps, infiles):
        pass

print(f"\nMaps complete: {INPUT_PATH}")
