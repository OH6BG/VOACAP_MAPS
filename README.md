# VOACAP MAPS

![](https://voacap.com/maps/2021_Nov_21.200_SDBW_13UT.png)

VOACAP_MAPS is a collection of scripts to generate a matrix of VOACAP point-to-point propagation predictions, covering the entire planet. This matrix can be used to plot various coverage area maps. Currently, in this collection, there are two scripts just to do this and one to store results in a database:

- **run_p2p_matrix.py** which helps you generate tens of thousands of point-to-point predictions
- **plot_maps.py** which helps you plot the point-to-point predictions
- **collect_data_to_database.py** helps you to parse massive point-to-point prediction files and store results in SQLite database

Make the scripts executable by setting the "execute" bit as follows:

    chmod +x run_p2p_matrix.py plot_maps.py collect_data_to_database.py

However, to be able to plot VOACAP coverage area maps, you will need to first install James Watson's pythonprop package at https://github.com/jawatson/pythonprop

Then, after having backed up the original voaAreaPlot.py from pythonprop in a safe place, replace that file with the one provided here. Also note that plotting the maps require a lot of other packages to be installed. See James Watson's page for further info.

## VOACAP.INI

Please review this file carefully. In the "default" section, change the txlat and txlon coordinates to yours. Also, adjust power (in kilowatts) to your typical level. You can keep gridsize = 120 but I would recommend the value of 73 to start with.

The "frequency" section should be fine for ham radio purposes.

The "antenna" section is again something you will need to adjust. Note that I am using antenna models which are not available so you will need to use models of your own, or select proper models from the "default" or "samples" directories that are provided with the PC version of VOACAP.

## SSN.TXT

This file contains the latest predictions of smoothed sunspot numbers (SSN) until June 2022. You will need to update this file periodically by downloading the latest data e.g. via cron from: https://wwwbis.sidc.be/silso/FORECASTS/KFprediML.txt

# Examples

## 1. Run 24 hours of predictions for Sep, Oct and Nov 2021 for all ham bands

The month numbers can be given in any order, separated by a space; they will be sorted. The same applies to year numbers. In the beginning, start experimenting with a couple of months only if you want to run 24 hours of predictions on all bands as the data to be produced will be quite massive.

    user:~/voa$ ./run_p2p_matrix.py
    Create Point-to-Point VOACAP prediction matrix.
    Copyright 2021 OH6BG Jari Perkiömäki.

    Enter year(s): 2021
    Enter month number(s) (1..12): 9 10 11
    Enter start time UTC (0..23): 0
    Enter time range in hours (1..24): 24

    SSN for Sep 2021: 26

    Processing 3.500 MHz...
    Processing 5.300 MHz...
    Processing 7.100 MHz...
    Processing 10.100 MHz...
    Processing 14.100 MHz...
    Processing 18.100 MHz...
    Processing 21.200 MHz...
    Processing 24.900 MHz...
    Processing 28.200 MHz...

    SSN for Oct 2021: 29

    Processing 3.500 MHz...
    Processing 5.300 MHz...
    Processing 7.100 MHz...
    Processing 10.100 MHz...
    Processing 14.100 MHz...
    Processing 18.100 MHz...
    Processing 21.200 MHz...
    Processing 28.200 MHz...
    Processing 24.900 MHz...

    SSN for Nov 2021: 31

    Processing 3.500 MHz...
    Processing 5.300 MHz...
    Processing 7.100 MHz...
    Processing 10.100 MHz...
    Processing 14.100 MHz...
    Processing 18.100 MHz...
    Processing 21.200 MHz...
    Processing 24.900 MHz...
    Processing 28.200 MHz...

    Output directory: /home/user/voa/predictions/12631402

## 2. Convert VOACAP prediction matrix to coverage maps

In Example 1 we generated a considerable number of prediction matrices, and the script below can be used to plot all of it to coverage maps. Running the maps will take a few minutes to complete!

    user:~/voa$ ./plot_maps.py
    Plot coverage maps from VOACAP VG files.
    Copyright 2021 OH6BG Jari Perkiömäki.

    Enter root path to VG files:  /home/user/voa/predictions/12631402

    Processing 2021 Sep 24.900...
    Processing 2021 Sep 28.200...
    Processing 2021 Sep 21.200...
    Processing 2021 Sep 10.100...
    Processing 2021 Sep 7.100...
    Processing 2021 Sep 18.100...
    Processing 2021 Sep 3.500...
    Processing 2021 Sep 5.300...
    Processing 2021 Sep 14.100...
    Processing 2021 Oct 24.900...
    Processing 2021 Oct 28.200...
    Processing 2021 Oct 21.200...
    Processing 2021 Oct 10.100...
    Processing 2021 Oct 7.100...
    Processing 2021 Oct 18.100...
    Processing 2021 Oct 3.500...
    Processing 2021 Oct 5.300...
    Processing 2021 Oct 14.100...
    Processing 2021 Nov 24.900...
    Processing 2021 Nov 28.200...
    Processing 2021 Nov 21.200...
    Processing 2021 Nov 10.100...
    Processing 2021 Nov 7.100...
    Processing 2021 Nov 18.100...
    Processing 2021 Nov 3.500...
    Processing 2021 Nov 5.300...
    Processing 2021 Nov 14.100...

    Maps complete: /home/user/voa/predictions/12631402

The root path (=directory) looks like this:

    user:~/voa/predictions/12631402$ ls -la
    total 180
    drwxr-xr-x 7 jpe jpe  4096 Aug 29 18:31 .
    drwxr-xr-x 3 jpe jpe  4096 Aug 29 18:19 ..
    drwxr-xr-x 5 jpe jpe  4096 Aug 29 18:21 2021
    drwxr-xr-x 2 jpe jpe 36864 Aug 29 18:44 REL
    drwxr-xr-x 2 jpe jpe 36864 Aug 29 18:44 SDBW
    drwxr-xr-x 2 jpe jpe 40960 Aug 29 18:44 SNR50
    drwxr-xr-x 2 jpe jpe 40960 Aug 29 18:44 SNR90

The directories of REL, SDBW, SNR50 and SNR90 contain all the maps. In this example, each map directory contains 648 maps (3 months x 24 hours x 9 bands), a total of 250+ MB for one directory. The "2021" directory contains the raw VOACAP predictions.

## 3. Store all prediction output to database

You can store all the VOACAP prediction results into an SQLite3 database. While processing (i.e. parsing) the VOACAP output files, the script will calculate the distances and the beam headings from your QTH to all the receive points in the global matrix. When the results are in the database, you can create a number of SQL queries to leverage the information.

    user:~/voa$ ./collect_data_to_database.py
    Store output from VOACAP VG files to SQlite3 database.
    Copyright 2021 Jari Perkiömäki OH6BG.

    Enter root path to VG files:  /home/user/voa/predictions/12631402

    Parsing Nov  3.5 MHz 01 UTC: 0.2 secs
    Parsing Nov  3.5 MHz 10 UTC: 0.2 secs
    Parsing Nov  3.5 MHz 11 UTC: 0.2 secs
    Parsing Nov  3.5 MHz 12 UTC: 0.2 secs

    [... removed 640 processed lines here ...]

    Parsing Sep 28.2 MHz 06 UTC: 0.3 secs
    Parsing Sep 28.2 MHz 07 UTC: 0.2 secs
    Parsing Sep 28.2 MHz 08 UTC: 0.3 secs
    Parsing Sep 28.2 MHz 09 UTC: 0.3 secs

    Enter database name: sep_oct_nov_2021.db

    TEST: Reading results from database 'sep_oct_nov_2021.db'...

    UT MON   FREQ MUF   SDBW  SNR50    REL  SNR90  RXLAT   RXLON     KM   DEG   MODE
    01 Nov  3.500  99 -132.0   23.4  0.778    6.6   42.9   130.8   6713    53    2F2
    01 Nov  5.300  93 -130.4   29.9  0.811    6.9   41.2   136.2   7088    50   F2F2
    01 Nov  7.100  75 -130.3   33.0  0.821    6.3   40.0   137.0   7241    50   F2F2
    01 Oct  5.300  98 -134.9   25.4  0.842   10.4   43.6   133.9   6761    50    2F2
    01 Oct  7.100  82 -135.6   27.8  0.781    4.2   40.9   135.5   7096    50   F2F2
    01 Oct 10.100  38 -144.8   21.4  0.658   -5.2   38.1   138.8   7495    49   F2F2
    01 Sep  5.300  99 -138.8   21.5  0.799    8.6   41.2   125.0   6639    58    2F2
    01 Sep  7.100  93 -138.1   25.2  0.796    6.9   42.7   133.6   6840    51   F2F2
    01 Sep 10.100  63 -137.7   28.8  0.776    2.2   40.0   137.0   7241    50   F2F2
    01 Sep 14.100   7 -138.2   31.0  0.806    4.5   37.5   138.3   7543    50   F2F2

    Database complete: sep_oct_nov_2021.db
    user:~/voa$

The size of the 'sep_oct_nov_2021.db' database is approximately 860 MB.

## 4. How to analyze VOACAP prediction results with SQLite?

When all VOACAP prediction data is available from a database, you can then create simple and more sophisticated queries to understand how signal propagation behaves by month, by hour, by frequency from your TX QTH. Note that here we do not talk about propagation in a certain day in a month because this is what VOACAP cannot predict.

The Python code you can use for extracting data from the database can be as simple as this:

    #!/usr/bin/python
    import sqlite3
    DATABASE_NAME = 'sep_oct_nov_2021.db'
    con = sqlite3.connect(DATABASE_NAME)
    c = con.cursor()

    print(f"UT MON FREQ  MUF   SDBW  SNR50    REL  SNR90  RXLAT   RXLON     KM  DEG")
    # 'MUF' is MUFday (percentage, not a frequency)

    with con:
        query = ("SELECT DISTINCT * FROM points "
                "WHERE utc = 3 "
                "and sdbw > -153 "
                "and rel >= 0.1 "
                "and snrxx >= 10 "
                "and freq = 7.100")
        c.execute(query)
        result = c.fetchall()
        for r in result:
            print(f"{r[0]:02d} {r[1]} {r[2]:.3f} {int(r[12]*100):>3} {r[15]:>6} {r[17]:>6}  "
                f"{r[19]:.3f} {r[24]:6}  {r[5]:>5}  {r[6]:>6} {r[31]:>6.0f}  {r[32]:3.0f}")

Typically, you would change the line starting with "c.execute" which is where you define your query in detail. Also, you may need to change the "print" line according to what details you want to show from the lines found in the database. There is a lot of data which may not be interesting to show.

In this example, the above query will return all the 7679 rows in the database at 03 UTC on 7.100 MHz where SDBW (the Signal Power) is greater than -153 dBW (close to the noise level) and the REL (Reliability) is equal to or greater than 0.1 or 10%. Moreover, the predicted SNRXX or SNR90 (the Signal-to-Noise Ratio, SNR achieved at 90% of the days, or 27 days, in a month) needs to be equal to or more than 10 (dB/Hz), which is slightly less than the minimum acceptable SNR level (13 dB/Hz) for FT8.

Please note that the query evaluates the entire global matrix in the months of September, October and November, and most probably there are results which are not of interest at all.

Obviously, we will need to restrict the query further. What options do we have? For instance,

- select a specific month only
- select an area of interest (e.g. by coordinates, by beam range, or by distance range)

### 4.1. Select a specific month

Selecting a certain month for analysis is easy. In the SELECT query above, just add another WHERE clause for "month" (e.g. month = 'Nov') as follows:

    query = ("SELECT DISTINCT * FROM points "
            "WHERE month = 'Nov' "
            "and utc = 3 "
            "and sdbw > -153 "
            "and rel >= 0.1 "
            "and snrxx >= 10 "
            "and freq = 7.100")
    c.execute(query)

Note that all months can be referred to by their three-letter abbreviation: Jan, Feb, Mar, Apr, May, Jun, etc.

### 4.2. Select a range of distances

The above query will still result in 2695 hits. So, the query should be more restrictive. Let's focus on the predictions on circuits between distances of 6,000 and 10,000 km. Let's add another WHERE clause: "km BETWEEN 6000 and 10000".

    query = ("SELECT DISTINCT * FROM points "
            "WHERE month = 'Nov' "
            "and utc = 3 "
            "and sdbw > -153 "
            "and rel >= 0.1 "
            "and snrxx >= 10 "
            "and freq = 7.100 "
            "and km BETWEEN 6000 and 10000")
    c.execute(query)

### 4.3. Select a range of beam headings

Adding the distance range still yielded 779 hits which is perhaps too much. Now we can try to restrict our query to a certain range of beam headings from our QTH. Let's add the following WHERE clause ("deg BETWEEN 270 and 300") to focus on the beam headings between 270 and 300 degrees, which is the Caribbean and Eastern USA region from my QTH.

    query = ("SELECT DISTINCT * FROM points "
            "WHERE month = 'Nov' "
            "and utc = 3 "
            "and sdbw > -153 "
            "and rel >= 0.1 "
            "and snrxx >= 10 "
            "and freq = 7.100 "
            "and km BETWEEN 6000 and 10000 "
            "and deg BETWEEN 270 and 300")
    c.execute(query)

Now the number of results is 82, which is pretty reasonable. The data shows that RX latitudes range from 5 to 42.5 degrees North, and RX longitudes from 55 to 90 degrees West.

### 4.4. Select an area defined by coordinates

If you are interested in exploring the propagation to a well-defined coordinate area, you can easily do so by using the following WHERE clause:

    rxlat BETWEEN 35 and 60 and rxlon BETWEEN -10 and 30

When you use coordinates, you would not use the beam heading or distance clauses. So, your query can now look like this:

    query = ("SELECT DISTINCT * FROM points "
            "WHERE month = 'Nov' "
            "and utc = 3 "
            "and sdbw > -153 "
            "and rel >= 0.1 "
            "and snrxx >= 10 "
            "and freq = 7.100 "
            "and rxlat BETWEEN 35 and 60 "
            "and rxlon BETWEEN -10 and 30")
    c.execute(query)

In my example case, this query would yield 78 rows, starting as follows:

    UT MON FREQ  MUF   SDBW  SNR50    REL  SNR90  RXLAT   RXLON     KM  DEG
    03 Nov 7.100  71 -101.9   54.7  0.995   33.9   35.0   -10.0   3799  230
    03 Nov 7.100  63 -102.3   53.9  0.989   30.9   35.0    -5.0   3617  223
    03 Nov 7.100  98 -102.3   53.4  0.997   35.1   35.0     0.0   3457  215
    03 Nov 7.100  98 -101.6   53.9  1.000   40.5   35.0     5.0   3325  208
    03 Nov 7.100  98 -102.6   53.0  1.000   42.3   35.0    10.0   3223  200
    03 Nov 7.100  97 -101.1   54.6  1.000   43.7   35.0    15.0   3157  191
