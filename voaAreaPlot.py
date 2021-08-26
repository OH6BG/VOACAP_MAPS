#!/usr/bin/python3
#
# File: voaAreaPlot.py
#
# Copyright (c) 2008 J.Watson
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#

# Modified 2021 by Jari Perkiömäki OH6BG

import argparse
import datetime
import math
import numpy as np
import os
import re
import sys

import cartopy.crs as ccrs
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
from cartopy.mpl.geoaxes import GeoAxes
import cartopy.feature as cfeature
from cartopy.feature.nightshade import Nightshade

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import ListedColormap
from mpl_toolkits.axes_grid1 import AxesGrid

from voaFile import VOAFile

class VOAAreaPlot:
    IMG_TYPE_DICT = {
        1: {'plot_type': 'MUF', 'title': ('Maximum Usable Frequency (MUF)'), 'min': 2, 'max': 30,
            'y_labels': (2, 4, 7, 10, 14, 18, 21, 24, 28, 30), 'formatter': 'frequency_format', 'first_char': 27,
            'last_char': 32},
        2: {'plot_type': 'REL', 'title': ('Circuit Reliability (%)'), 'min': 0, 'max': 1,
            'y_labels': (0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1), 'formatter': 'percent_format',
            'first_char': 98, 'last_char': 104},
        3: {'plot_type': 'SNR', 'title': ('Median SNR (dB/Hz)'), 'min': 0, 'max': 100,
            'y_labels': (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100), 'formatter': 'SNR_format', 'first_char': 86,
            'last_char': 92},
        4: {'plot_type': 'SNRXX', 'title': ('SNR90 (dB/Hz)'), 'min': 0, 'max': 100,
            'y_labels': (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100), 'formatter': 'SNR_format', 'first_char': 128,
            'last_char': 134},
        5: {'plot_type': 'SDBW', 'title': ('Signal Power (dBW)'), 'min': -160, 'max': -60,
            'y_labels': (-160, -150, -140, -130, -120, -110, -100, -90, -80, -70, -60), 'formatter': 'SDBW_format',
            'first_char': 74, 'last_char': 80},
        6: {'plot_type': 'SMETESNRXXR', 'title': ('S-Meter'), 'min': -151.18, 'max': -43.01,
            'y_labels': (-151.18, -139.13, -127.09, -115.05, -103.01, -83.01, -63.01, -43.01),
            'formatter': 'SMETER_format', 'first_char': 74, 'last_char': 80}
    }

    show_subplot_frame = False

    def __init__(self, in_file,
                 vg_files=[1],
                 data_type=1,
                 time_zone=0,
                 color_map='oh6bg',
                 face_colour="white",
                 filled_contours=True,
                 plot_contours=True,
                 plot_meridians=True,
                 plot_parallels=True,
                 plot_nightshade=True,
                 resolution='f',
                 save_file='',
                 run_quietly=False,
                 dpi=300,
                 parent=None,
                 datadir=None):

        self.run_quietly = run_quietly
        self.dpi = float(dpi)
        self.datadir = datadir

        plot_parameters = VOAFile((in_file))
        plot_parameters.parse_file()

        img_grid_size = plot_parameters.get_gridsize()
        self.image_defs = VOAAreaPlot.IMG_TYPE_DICT[int(data_type)]

        imageBuf = np.zeros([img_grid_size, img_grid_size], float)

        area_rect = plot_parameters.get_area_rect()

        oh6bg = ListedColormap(
            ['#FFFFFF', '#BEF0FF', '#6DD6FD', '#00BFFF', '#1FBE3D', '#BFFF00', '#FFFF00', '#FFCD2E', '#FF7602',
             '#FF0000'])
        plt.register_cmap(name='oh6bg', cmap=oh6bg)
        projection = ccrs.PlateCarree(central_longitude=0)
        axes_class = (GeoAxes, dict(map_projection=projection))

        number_of_subplots = len(vg_files)

        matplotlib.rcParams['font.family'] = 'sans-serif'
        matplotlib.rcParams['axes.edgecolor'] = 'black'
        matplotlib.rcParams['axes.facecolor'] = 'white'
        matplotlib.rcParams['axes.linewidth'] = 0.1
        matplotlib.rcParams['axes.ymargin'] = 0.1
        matplotlib.rcParams['figure.facecolor'] = face_colour
        matplotlib.rcParams['figure.frameon'] = False
        matplotlib.rcParams['figure.figsize'] = (6.0, 2.7)
        colorbar_fontsize = 10

        if number_of_subplots <= 1:
            num_rows = 1
            self.main_title_fontsize = 10
            matplotlib.rcParams['legend.fontsize'] = 4
            matplotlib.rcParams['axes.labelsize'] = 6
            matplotlib.rcParams['axes.titlesize'] = 4
            matplotlib.rcParams['xtick.labelsize'] = 4
            matplotlib.rcParams['ytick.labelsize'] = 4
            matplotlib.rcParams['ytick.major.width'] = 0.3
            matplotlib.rcParams['ytick.labelsize'] = 4
        elif ((number_of_subplots >= 2) and (number_of_subplots <= 6)):
            num_rows = 2
            self.main_title_fontsize = 18
            matplotlib.rcParams['legend.fontsize'] = 10
            matplotlib.rcParams['axes.labelsize'] = 10
            matplotlib.rcParams['axes.titlesize'] = 11
            matplotlib.rcParams['xtick.labelsize'] = 8
            matplotlib.rcParams['ytick.labelsize'] = 8
        else:
            num_rows = 3
            self.main_title_fontsize = 10
            matplotlib.rcParams['legend.fontsize'] = 8
            matplotlib.rcParams['axes.labelsize'] = 8
            matplotlib.rcParams['axes.titlesize'] = 10
            matplotlib.rcParams['xtick.labelsize'] = 6
            matplotlib.rcParams['ytick.labelsize'] = 6

        num_cols = 1

        fig = plt.figure()
        axgr = AxesGrid(fig, 111, axes_class=axes_class,
                        nrows_ncols=(num_rows, num_cols),
                        axes_pad=0.6,
                        cbar_location='right',
                        cbar_mode='single',
                        cbar_pad=0.1,
                        cbar_size='3%',
                        label_mode='')

        for plot_idx, ax, vg_file in zip(range(number_of_subplots), axgr, vg_files):

            points = np.zeros([img_grid_size, img_grid_size], float)

            lons = np.arange(area_rect.get_sw_lon(), area_rect.get_ne_lon() + 0.001,
                             (area_rect.get_ne_lon() - area_rect.get_sw_lon()) / float(img_grid_size - 1))
            lons[-1] = min(180.0, lons[-1])
            lats = np.arange(area_rect.get_sw_lat(), area_rect.get_ne_lat() + 0.001,
                             (area_rect.get_ne_lat() - area_rect.get_sw_lat()) / float(img_grid_size - 1))
            lats[-1] = min(90.0, lats[-1])

            vgFile = open(f"{os.path.splitext(in_file)[0]}.vg{vg_file}")
            pattern = re.compile(r"[a-z]+")

            for line in vgFile:
                match = pattern.search(line)
                if not match:
                    value = float(line[int(self.image_defs['first_char']):int(self.image_defs['last_char'])])
                    value = max(self.image_defs['min'], value)
                    value = min(self.image_defs['max'], value)
                    points[int(line[3:6]) - 1][int(line[0:3]) - 1] = value
            vgFile.close()

            ax.set_extent([area_rect.get_sw_lon(),
                           area_rect.get_ne_lon(),
                           area_rect.get_sw_lat(),
                           area_rect.get_ne_lat()], projection)

            ax.coastlines(linewidth=0.3)
            ax.add_feature(cfeature.BORDERS, linewidth=0.25, alpha=0.5)
            ax.outline_patch.set_linewidth(0.1)  # the edge linewidth of the world map

            lons, lats = np.meshgrid(lons, lats)
            points = np.clip(points, self.image_defs['min'], self.image_defs['max'])
            
            im = ''
            if filled_contours:
                im = ax.contourf(lons, lats, points, self.image_defs['y_labels'],
                                 cmap='oh6bg',
                                 transform=projection)
                plot_contours = True

            if plot_contours:
                ct = ax.contour(lons, lats, points, self.image_defs['y_labels'][1:],
                                linestyles='solid',
                                linewidths=0.1,
                                colors='k',
                                vmin=self.image_defs['min'],
                                vmax=self.image_defs['max'],
                                transform=projection)

            if plot_nightshade:
                d2 = datetime.datetime.utcnow()
                utc = plot_parameters.get_utc(vg_files[plot_idx] - 1)
                month = plot_parameters.get_month(vg_files[plot_idx] - 1)
                date = datetime.datetime(d2.year, int(month), d2.day, int(utc))
                ax.add_feature(Nightshade(date, alpha=0.2))

            gl = ax.gridlines(crs=projection, draw_labels=False, linewidth=0.3, color='gray', alpha=0.5, linestyle='--')
            gl.xlocator = mticker.FixedLocator(range(-180, 190, 30))
            gl.ylocator = mticker.FixedLocator(range(-90, 100, 30))
            gl.xformatter = LONGITUDE_FORMATTER
            gl.yformatter = LATITUDE_FORMATTER

            if plot_meridians:
                if (area_rect.get_lon_delta() <= 90.0):
                    meridians = np.arange(-180, 190.0, 10.0)
                elif (area_rect.get_lon_delta() <= 180.0):
                    meridians = np.arange(-180.0, 210.0, 30.0)
                else:
                    meridians = np.arange(-180, 240.0, 60.0)
                gl.xlines = True
                gl.xlabels_bottom = True
                gl.xformatter = LONGITUDE_FORMATTER
                gl.xlocator = mticker.FixedLocator(meridians)

            if plot_parallels:
                if (area_rect.get_lat_delta() <= 90.0):
                    parallels = np.arange(-90.0, 120.0, 60.0)
                else:
                    parallels = np.arange(-90.0, 120.0, 30.0)
                gl.ylines = True
                gl.ylabels_right = True
                gl.yformatter = LATITUDE_FORMATTER
                gl.ylocator = mticker.FixedLocator(parallels)

            # add a title
            title_str = plot_parameters.get_plot_description_string(vg_files[plot_idx] - 1,
                                                                    self.image_defs['plot_type'], time_zone=time_zone)
            if number_of_subplots == 1:
                now = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                title_str = title_str + "\n" + plot_parameters.get_detailed_plot_description_string(
                    vg_files[plot_idx] - 1) + "\n© Jari Perkiömäki OH6BG, " + now
            else:
                title_str = plot_parameters.get_minimal_plot_description_string(vg_files[plot_idx] - 1,
                                                                                self.image_defs['plot_type'],
                                                                                time_zone=time_zone)
            self.subplot_title_label = ax.set_title(title_str)

        # Hide any unused subplots
        for ax in axgr[number_of_subplots:]:
            ax.set_visible(False)

        axgr.cbar_axes[0].colorbar(im,
                                   ticks=self.image_defs['y_labels'],
                                   format=mticker.FuncFormatter(eval('self.' + self.image_defs['formatter'])))

        plt.subplots_adjust(left=0.1, right=0.9, top=0.95, bottom=0)

        if save_file:
            plt.savefig(save_file,
                        dpi=self.dpi,
                        facecolor=fig.get_facecolor(),
                        edgecolor='none',
                        format='png')

    def percent_format(self, x, pos):
        return f"{x * 100:>3.0f}%"

    def SNR_format(self, x, pos):
        return f"{x:>3} dB"

    def SDBW_format(self, x, pos):
        return f"{x:>3} dBW"

    """
    The values below are derived from material
    presented at http://www.voacap.com/s-meter.html
    """

    def SMETER_format(self, x, pos):
        S_DICT = {-151.18: 'S1', -145.15: 'S2', -139.13: 'S3', -133.11: 'S4', -127.09: 'S5', \
                  -121.07: 'S6', -115.05: 'S7', -109.03: 'S8', -103.01: 'S9', -93.01: 'S9+10dB', \
                  -83.01: 'S9+20dB', -73.01: 'S9+30dB', -63.01: 'S9+40dB', -53.01: 'S9+50dB', -43.01: 'S9+60dB'}
                  
        if x in S_DICT:
            return f"{S_DICT[x]}"
        else:
            return f"{x:3}"

    def frequency_format(self, x, pos):
        return f"{x:>2}MHz"

    def default_format(self, x, pos):
        return f"{x}"


def main(in_file, datadir=None):
    parser = argparse.ArgumentParser(description="Plot voacap area data")

    parser.add_argument("in_file",
                        help=(
                            "Path to the .voa file.  This should be in the same directory as the associated .vgx files."))

    parser.add_argument("-c", "--contours",
                        dest="plot_contours",
                        action="store_true",
                        default=True,
                        help=("Enables contour plotting."))

    parser.add_argument("-d", "--datatype",
                        dest="data_type",
                        default=1,
                        help=(
                            "DATATYPE - an integer number representing the data to plot. Valid values are 1 (MUF), 2 (REL) and 3 3 (SNR) 4 (SNRxx), 5 (SDBW) and 6 (SDBW - formatted as S-Meter values).  Default value is 1 (MUF)."))

    parser.add_argument("-f", "--filled-contour",
                        dest="plot_filled_contours",
                        action="store_true",
                        default=False,
                        help=("Produces a filled contour plot."))

    parser.add_argument("-i", "--meridian",
                        dest="plot_meridians",
                        action="store_true",
                        default=False,
                        help=("Plot meridians."))

    parser.add_argument("-k", "--background",
                        dest="face_colour",
                        default='white',
                        help=(
                            "Specify the colour of the background. Any legal HTML color specification is supported e.g '-k red', '-k #eeefff' (default = white)"))

    parser.add_argument("-l", "--parallels",
                        dest="plot_parallels",
                        action="store_true",
                        default=False,
                        help=("Plot meridians."))

    parser.add_argument("-m", "--cmap",
                        dest="color_map",
                        default='jet',
                        choices=['autumn', 'bone', 'cool', 'copper', 'gray', \
                                 'hot', 'hsv', 'jet', 'pink', 'spring', 'summer', 'winter', 'portland'],
                        help=(
                            "COLOURMAP - may be one of 'autumn', 'bone', 'cool', 'copper', 'gray', 'hot', 'hsv', 'jet', 'pink', 'spring', 'summer', 'winter' or 'portland'.  Default = 'jet'"))

    parser.add_argument("-o", "--outfile",
                        dest="save_file",
                        help="Save to FILE.",
                        metavar="FILE")

    parser.add_argument("-q", "--quiet",
                        dest="run_quietly",
                        action="store_true",
                        default=False,
                        help=("Process quietly (don't display plot on the screen)"))

    parser.add_argument("-r", "--resolution",
                        dest="resolution",
                        default='f',
                        choices=['c', 'l', 'i', 'h', 'f'],
                        help=(
                            "RESOLUTION - may be one of 'c' (crude), 'l' (low), 'i' (intermediate), 'h' (high), 'f' (full)"))

    parser.add_argument("-s", "--size",
                        dest="dpi",
                        default=300,
                        help=("Dots per inch (dpi) of saved file."))

    parser.add_argument("-t", "--terminator",
                        dest="plot_nightshade",
                        action="store_true",
                        default=True,
                        help=("Plot day/night regions on the map"))

    parser.add_argument("-v", "--vg_files",
                        dest="vg_files",
                        default='1',
                        help=(
                            "VG_FILES number of plots to process, e.g '-v 1,3,5,6' or use '-v a' to print all plots."))

    parser.add_argument("-z", "--timezone",
                        dest="timezone",
                        default=0,
                        help=("Time zone (integer, default = 0)"))

    args = parser.parse_args()
    vg_files, time_zone = [], 0

    if args.data_type:
        if int(args.data_type) not in VOAAreaPlot.IMG_TYPE_DICT:
            print("Unrecognised plot type: Defaulting to MUF")
            args.dataType = 1

    if args.vg_files:
        args.vg_files.strip()
        if args.vg_files == 'a':
            for file_num in range(1, 13):
                if os.path.exists(f"{in_file}.vg{file_num}"):
                    print(f"found: {in_file}.vg{file_num}")
                    vg_files.append(file_num)
        else:
            try:
                if args.vg_files.find(','):
                    vg_files = args.vg_files.split(',')
                else:
                    vg_files = [args.vg_files]

                for i in range(0, len(vg_files)):
                    try:
                        vg_files[i] = int(vg_files[i])
                    except:
                        vg_files.pop(i)
                if len(vg_files) == 0:
                    print("Error reading vg files (1), resetting to '1'")
                    vg_files = [1]
            except:
                print("Error reading vg files, resetting to '1'")
                vg_files = [1]

    VOAAreaPlot(in_file,
                vg_files=vg_files,
                data_type=args.data_type,
                time_zone=time_zone,
                color_map=args.color_map,
                face_colour=args.face_colour,
                filled_contours=args.plot_filled_contours,
                plot_contours=args.plot_contours,
                plot_meridians=args.plot_meridians,
                plot_parallels=args.plot_parallels,
                plot_nightshade=args.plot_nightshade,
                resolution=args.resolution,
                save_file=args.save_file,
                run_quietly=args.run_quietly,
                dpi=args.dpi,
                datadir=datadir)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        main(sys.argv[-1])
    else:
        print('voaAreaPlot error: No data file specified')
        print('voaAreaPlot [options] filename')
        sys.exit(1)
