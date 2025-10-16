#!/usr/bin/python

"""

Copyright 2021-2025 Jari Perkiömäki OH6BG

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
import re
import os

plot_base = "/home/user/pythonprop/src/pythonprop"
mufplot = f"{plot_base}/voaAreaPlot.py -f -d 1 -o"
relplot = f"{plot_base}/voaAreaPlot.py -f -d 2 -o"
snrplot = f"{plot_base}/voaAreaPlot.py -f -d 3 -o"
snr90plot = f"{plot_base}/voaAreaPlot.py -f -d 4 -o"
sdbwplot = f"{plot_base}/voaAreaPlot.py -f -d 5 -o"

# Validate external plot tool
tool_path = Path(plot_base) / "voaAreaPlot.py"
if not tool_path.is_file():
    print(f"[ERROR] Plot script not found: {tool_path}")
    sys.exit(1)

# Configuration for selectable map types
MAP_CONFIG = {
    "REL": {"cmd": relplot, "dir": "REL", "tag": "REL"},
    "SNR50": {"cmd": snrplot, "dir": "SNR50", "tag": "SNR50"},
    "SNR90": {"cmd": snr90plot, "dir": "SNR90", "tag": "SNR90"},
    "SDBW": {"cmd": sdbwplot, "dir": "SDBW", "tag": "SDBW"},
    "MUF": {"cmd": mufplot, "dir": "MUF", "tag": "MUF"},
}

# Will be set from user input
SELECTED_MAPS = []
PLOT_TIMEOUT_SEC = 60  # configurable timeout for voaAreaPlot2

# Precompiled regex
RE_UT_HOUR = re.compile(r"\b([01]?\d|2[0-4])\s*(?:UT|UTC|Z)\b", re.IGNORECASE)
RE_MHZ = re.compile(r"(\d+(?:\.\d+)?)\s*MHz\b", re.IGNORECASE)
RE_FREQ = re.compile(r"\bF(?:REQ)?\s*[=:]\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE)
RE_SUFFIX_NUM_END = re.compile(r"(\d+)$")
RE_VG_SUFFIX = re.compile(r"\.vg(\d+)$", re.IGNORECASE)


def _extract_hour_and_mhz_stream(vg):
    """
    Stream-parse VG to find hour and MHz quickly.
    - Hour: first NN followed by UT/UTC/Z (maps 24->00), fallback to 2nd line token.
    - MHz: first '<num> MHz' or 'F=/FREQ='.
    Returns (time_str, freq_str).
    """
    hour = None
    mhz_val = None
    first_lines = []

    try:
        with vg.open("r", errors="ignore") as fp:
            for idx, line in enumerate(fp, 1):
                if idx <= 2:
                    first_lines.append(line)
                if hour is None:
                    m_hour = RE_UT_HOUR.search(line)
                    if m_hour:
                        hour = int(m_hour.group(1)) % 24
                if mhz_val is None:
                    m_mhz = RE_MHZ.search(line)
                    if m_mhz:
                        try:
                            mhz_val = float(m_mhz.group(1))
                        except Exception:
                            mhz_val = None
                    if mhz_val is None:
                        m_mhz = RE_FREQ.search(line)
                        if m_mhz:
                            try:
                                mhz_val = float(m_mhz.group(1))
                            except Exception:
                                mhz_val = None
                if hour is not None and mhz_val is not None:
                    break
    except Exception:
        # Fall back to binary read if needed
        try:
            with vg.open("rb") as fp:
                first_lines = [ln.decode(errors="ignore") for ln in islice(fp, 2)]
                rest = fp.read().decode(errors="ignore")
                text = "".join(first_lines) + rest
                if hour is None:
                    m_hour = RE_UT_HOUR.search(text)
                    if m_hour:
                        hour = int(m_hour.group(1)) % 24
                if mhz_val is None:
                    m_mhz = RE_MHZ.search(text) or RE_FREQ.search(text)
                    if m_mhz:
                        try:
                            mhz_val = float(m_mhz.group(1))
                        except Exception:
                            mhz_val = None
        except Exception:
            pass

    # Legacy fallback for hour
    if hour is None and len(first_lines) >= 2:
        toks = first_lines[1].split()
        if len(toks) >= 4:
            m = re.search(r"\d+", toks[-4])
            if m:
                hour = int(m.group(0)) % 24

    if hour is None:
        hour = 0
    if mhz_val is None:
        mhz_val = 0.0

    time_str = f"{hour:02d}"
    freq_str = f"{int(mhz_val):02d}"
    return time_str, freq_str


def _safe_vg_number(vg):
    """
    Extract the -v selector (VG index) from the filename suffix like '.vg14'.
    Returns None if not found.
    """
    suf = vg.suffix  # e.g., ".vg14"
    m = RE_VG_SUFFIX.match(suf)
    if m:
        return m.group(1)
    m = re.search(r"(\d+)", suf)
    return m.group(1) if m else None


def plot_maps(f):
    print(f"Processing: {f}")

    # Deterministic order: sort VG files by numeric suffix if possible
    vgs = sorted(
        f.parent.glob("*.vg*"),
        key=lambda p: int(RE_SUFFIX_NUM_END.search(p.suffix).group(1))
        if RE_SUFFIX_NUM_END.search(p.suffix)
        else 0,
    )
    if not vgs:
        print(f"[WARN] No VG files found next to {f}")
        return

    for vg in vgs:
        vg_number = _safe_vg_number(vg)
        if not vg_number:
            print(f"[WARN] Skipping VG without selector: {vg}")
            continue

        time_str, freq_str = _extract_hour_and_mhz_stream(vg)

        # Generate only the selected map types
        for map_type in SELECTED_MAPS:
            cfg = MAP_CONFIG[map_type]
            outdir = INPUT_PATH / cfg["dir"]
            try:
                outdir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(
                    f"[ERROR] Cannot create directory for {map_type} maps: {outdir} ({e})"
                )
                continue

            # Filename: "<HH>UT-<FF>MHz.png"
            outfile = outdir / f"{time_str}UT-{freq_str}MHz.png"

            # Skip plotting if up-to-date vs inputs
            try:
                if outfile.exists():
                    out_mtime = outfile.stat().st_mtime
                    if out_mtime >= max(vg.stat().st_mtime, f.stat().st_mtime):
                        continue
            except Exception:
                pass

            # Build command as list and check return code
            args = shlex.split(cfg["cmd"]) + [str(outfile), "-v", vg_number, str(f)]
            try:
                cp = subprocess.run(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=PLOT_TIMEOUT_SEC,
                )
                if cp.returncode != 0:
                    print(
                        f"[ERROR] Plot failed ({map_type}) for {vg} -> {outfile.name}"
                    )
                    if cp.stderr:
                        print(cp.stderr.decode(errors="ignore").strip())
                    continue
            except subprocess.TimeoutExpired:
                print(f"[ERROR] Timeout ({PLOT_TIMEOUT_SEC}s) running plot for {vg}")
                continue
            except Exception as e:
                print(f"[ERROR] {map_type} plot error for {vg}: {e}")
                continue


"""
Set up paths
"""
print(
    "Plot coverage maps from VOACAP VG files.\nCopyright 2025 Jari Perkiömäki OH6BG.\n"
)

INPUT_PATH = Path(input("Enter root path to VG files: ").strip())

# Ask which map types to generate
available = list(MAP_CONFIG.keys())
default_selection = ["REL", "SNR50", "SNR90", "SDBW"]
raw = input(
    f"Select map types to generate (comma-separated; options: {','.join(available)}).\n"
    f"Leave empty for default [{','.join(default_selection)}]: "
).strip()

if raw:
    SELECTED_MAPS = [m.strip().upper() for m in raw.split(",") if m.strip()]
    SELECTED_MAPS = [m for m in SELECTED_MAPS if m in MAP_CONFIG]
    if not SELECTED_MAPS:
        print("No valid map types selected. Exiting.")
        sys.exit(1)
else:
    SELECTED_MAPS = default_selection

print(f"\nSelected maps: {', '.join(SELECTED_MAPS)}")

# Gather .voa files and deduplicate by directory (pick newest per dir)
infiles = list(INPUT_PATH.rglob("*.voa"))
if not infiles:
    print("No .voa files found under the provided path.")
    sys.exit(0)

voa_by_dir = {}
for p in infiles:
    d = p.parent
    try:
        if d not in voa_by_dir or p.stat().st_mtime > voa_by_dir[d].stat().st_mtime:
            voa_by_dir[d] = p
    except Exception:
        voa_by_dir[d] = p
infiles = sorted(voa_by_dir.values())

# Dynamic, bounded concurrency
max_workers = min(16, (os.cpu_count() or 4) * 2)
try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for _ in executor.map(plot_maps, infiles):
            pass
except KeyboardInterrupt:
    print("\nInterrupted. Exiting.")
    sys.exit(130)

print(f"\nMaps complete: {INPUT_PATH}")
