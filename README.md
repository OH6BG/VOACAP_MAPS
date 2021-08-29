# VOACAP MAPS

VOACAP_MAPS is a collection of scripts to generate a matrix of VOACAP point-to-point propagation predictions, covering the entire planet. This matrix can be used to plot various coverage area maps. Currently, in this collection, there are two scripts just to do this and one to store results in a database:

- **run_p2p_matrix.py** which helps you generate tens of thousands of point-to-point predictions
- **plot_maps.py** which helps you plot the point-to-point predictions
- **collect_data_to_database.py** helps you to parse massive point-to-point prediction files and store results in SQLite database

However, to be able to plot VOACAP coverage area maps, you will need to first install James Watson's pythonprop package at https://github.com/jawatson/pythonprop

Then, after having backed up the original voaAreaPlot.py from pythonprop in a safe place, replace that file with the one provided here. Also note that plotting the maps require a lot of other packages to be installed. See James Watson's page for further info.

## VOACAP.INI

Please review this file carefully. In the "default" section, change the txlat and txlon coordinates to yours. Also, adjust power (in kilowatts) to your typical level. You can keep gridsize = 120 but I would recommend the value of 73 to start with.

The "frequency" section should be fine for ham radio purposes.

The "antenna" section is again something you will need to adjust. Note that I am using antenna models which are not available so you will need to use models of your own, or select proper models from the "default" or "samples" directories that are provided with the PC version of VOACAP.

## SSN.TXT

This file contains the latest predictions of smoothed sunspot numbers (SSN) until June 2022. You will need to update this file periodically by downloading the latest data e.g. via cron from: https://wwwbis.sidc.be/silso/FORECASTS/KFprediML.txt
