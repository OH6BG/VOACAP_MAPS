/*

Copyright 2025 Jari Perkiömäki OH6BG

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

*/

/*
run_p2p.go - produce VOACAP area prediction data by running voacapl.

- Reads config from voacap.ini (default, frequency, antenna sections)
- Prompts for years, months, start hour, and time range
- Builds VOACAP .voa decks under /home/user/voacap_maps/predictions/<id>/<Year>/<Mon>/<freq>/
- Invokes voacapl with area/calc
- Cleans up temp files

Usage examples:

go run run_p2p.go
go run run_p2p.go --workers 6

Compile the code to an executable:

go build -o run_p2p.exe ./run_p2p.go

*/

package main

import (
	"bufio"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"math/rand"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Config struct {
	// [default]
	TxLat    float64
	TxLon    float64
	Power    float64
	Mode     int
	Es       float64
	Method   int
	MinToa   float64
	Noise    int
	GridSize int
	PathFlag string

	// [frequency]
	FList []string

	// [antenna]
	TxAnt map[string]string
	RxAnt map[string]string
}

var (
	// Defaults and paths (Linux)
	basePredDir = "/home/user/voacap_maps/predictions"
	voacaplBin  = "/usr/local/bin/voacapl"
	itshfbcDir  = "/home/user/itshfbc"
	ssnFile     = "/home/user/voacap_maps/ssn.txt"

	monthsList = []string{"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}
	stdin      = bufio.NewReader(os.Stdin)
	logger     = func(format string, a ...any) { fmt.Printf(format+"\n", a...) }

	// User-settable workers (default 4)
	workersFlag = flag.Int("workers", 4, "Max parallel voacapl runs")
)

func main() {
	flag.Parse()

	fmt.Println("Create raw VOACAP prediction data for coverage maps.")
	fmt.Println("Copyright 2025 Jari Perkiömäki OH6BG.")
	fmt.Println()

	// Read INI
	cfg, err := readINI("voacap.ini")
	if err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: reading voacap.ini: %v\n", err)
		os.Exit(1)
	}

	// Validate voacapl
	if st, err := os.Stat(voacaplBin); err != nil || st.IsDir() {
		fmt.Fprintf(os.Stderr, "ERROR: voacapl binary not found: %s\n", voacaplBin)
		os.Exit(1)
	}
	if st, err := os.Stat(itshfbcDir); err != nil || !st.IsDir() {
		fmt.Fprintf(os.Stderr, "ERROR: ITSHFBC directory not found: %s\n", itshfbcDir)
		os.Exit(1)
	}

	// Interactive prompts
	runYears := askYears("Enter year(s): ")
	runMonths := askMonths("Enter month number(s) (1..12): ")
	startTime := askIntInRange("Enter start time UTC (0..23): ", 0, 23)
	timeRange := askIntInRange("Enter time range in hours (1..24): ", 1, 24)

	// Derived values
	txName := latlon2loc(cfg.TxLat, cfg.TxLon, 3)
	tLat := fmt.Sprintf("%6.2f", cfg.TxLat)
	tLon := fmt.Sprintf("%7.2f", cfg.TxLon)

	// Unique prediction ID (8 hex chars)
	preID := randomID8()
	predRoot := filepath.Join(basePredDir, preID)
	if err := os.MkdirAll(predRoot, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: cannot create base prediction directory %s: %v\n", predRoot, err)
		os.Exit(1)
	}

	// Total calculations for progress (one per frequency per year-month)
	totalCalcs := len(cfg.FList) * len(runYears) * len(runMonths)
	if totalCalcs == 0 {
		fmt.Println("Nothing to do (no frequencies/years/months).")
		return
	}
	fmt.Printf("Total calculations: %d\n", totalCalcs)

	// Determine and print worker count
	workersUsed := *workersFlag
	if workersUsed < 1 {
		workersUsed = 1
	}
	fmt.Printf("Total workers: %d\n", workersUsed)

	// Timer start
	start := time.Now()

	// Progress indicator (each update on its own line)
	doneCh := make(chan string, totalCalcs)
	var progressWG sync.WaitGroup
	progressWG.Add(1)
	go func() {
		defer progressWG.Done()
		completed := 0
		for freq := range doneCh {
			completed++
			// Print a new line per completion, with explicit " ... "
			fmt.Printf("Progress %d/%d ... Finished %s MHz\n", completed, totalCalcs, freq)
		}
	}()

	for _, year := range runYears {
		for _, month := range runMonths {
			ssn := getSSN(ssnFile, year, month)
			for ssn < 0 || ssn > 300 {
				ssn = askIntInRange(fmt.Sprintf("\nEnter sunspot number (SSN) for %s %d: ", monthsList[month-1], year), 0, 300)
			}
			fmt.Printf("\nSSN for %s %d: %d\n\n", monthsList[month-1], year, ssn)

			// Precompute repeated strings for hours block
			hours := make([]int, timeRange)
			for i := 0; i < timeRange; i++ {
				hours[i] = (startTime + i) % 24
			}
			monthList := "Months   :" + repeatFloat(float64(month), len(hours), 7, 2)
			ssnList := "Ssns     :" + repeatInt(ssn, len(hours), 7)
			hourList := "Hours    :" + joinInts(hours, 7)

			// Concurrency (bounded by --workers)
			maxWorkers := workersUsed
			if maxWorkers < 1 {
				maxWorkers = 1
			}
			var wg sync.WaitGroup
			sem := make(chan struct{}, maxWorkers)

			for _, f := range cfg.FList {
				freq := f // capture
				wg.Add(1)
				sem <- struct{}{}
				go func() {
					defer wg.Done()
					defer func() { <-sem }()
					makeVOACAPPrediction(cfg, predRoot, year, month, hours, monthList, ssnList, hourList, tLat, tLon, txName, ssn, freq)
					// Mark one calculation done with the finished frequency
					doneCh <- freq
				}()
			}
			wg.Wait()
		}
	}

	// Finish progress and timer
	close(doneCh)
	progressWG.Wait()
	fmt.Printf("Elapsed: %s\n\n", time.Since(start).Truncate(time.Millisecond))

	fmt.Printf("Output directory: %s\n", predRoot)
}

// Build deck, write atomically, run voacapl, cleanup
func makeVOACAPPrediction(cfg Config, predRoot string, year, month int, hours []int, monthList, ssnList, hourList, tLat, tLon, txName string, ssn int, freq string) {
	// Antenna mapping
	txAnt, rxAnt := antForFreq(cfg, freq)

	// Freq column repeated for hours
	freqList := "Freqs    :" + repeatString(freq, len(hours), 7)

	// Input deck content
	deck := strings.Join([]string{
		"Model    :VOACAP",
		"Colors   :Black    :Blue     :Ignore   :Ignore   :Red      :Black with shading",
		"Cities   :Receive.cty",
		"Nparms   :    1",
		"Parameter:REL      0",
		fmt.Sprintf("Transmit : %s   %s   %-20s %s", tLat, tLon, txName, cfg.PathFlag),
		fmt.Sprintf("Pcenter  : %s   %s   %-20s", tLat, tLon, txName),
		"Area     :    -180.0     180.0     -90.0      90.0",
		fmt.Sprintf("Gridsize :  %3d    1", cfg.GridSize),
		fmt.Sprintf("Method   :   %d", cfg.Method),
		"Coeffs   :CCIR",
		monthList,
		ssnList,
		hourList,
		freqList,
		fmt.Sprintf("System   :  %3d     %.2f   90   %2d     3.000     0.100", cfg.Noise, cfg.MinToa, cfg.Mode),
		fmt.Sprintf("Fprob    : 1.00 1.00 1.00 %.2f", cfg.Es),
		fmt.Sprintf("Rec Ants :[voaant/%-14s]  gain=   0.0   0.0", rxAnt),
		fmt.Sprintf("Tx Ants  :[voaant/%-14s]  0.000  -1.0   %8.4f", txAnt, cfg.Power),
	}, "\n")

	// Paths: ROOT/<Year>/<Mon>/<freq>/
	monthName := monthsList[month-1]
	runDir := filepath.Join(predRoot, strconv.Itoa(year), monthName, freq)
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		logger("ERROR: Cannot create directory %s: %v", runDir, err)
		return
	}

	// Deck file name: cap_<freq>.voa (06.3f)
	fv, _ := strconv.ParseFloat(freq, 64)
	voaName := fmt.Sprintf("cap_%06.3f.voa", fv)
	voaPath := filepath.Join(runDir, voaName)

	// Atomic write
	tmp := voaPath + ".tmp"
	if err := os.WriteFile(tmp, []byte(deck+"\n"), 0o644); err != nil {
		logger("ERROR: Failed to write temp deck %s: %v", tmp, err)
		_ = os.Remove(tmp)
		return
	}
	if err := os.Rename(tmp, voaPath); err != nil {
		logger("ERROR: Failed to move deck into place %s: %v", voaPath, err)
		_ = os.Remove(tmp)
		return
	}

	// Run voacapl (synchronously)
	args := []string{
		fmt.Sprintf("--run-dir=%s", runDir),
		"--absorption-mode=a",
		"-s",
		itshfbcDir,
		"area",
		"calc",
		voaName,
	}
	cmd := exec.Command(voacaplBin, args...)
	cmd.Dir = runDir
	var outBuf, errBuf strings.Builder
	cmd.Stdout = &outBuf
	cmd.Stderr = &errBuf

	if err := cmd.Run(); err != nil {
		logger("ERROR: voacapl failed for %s MHz: %v\n%s", freq, err, errBuf.String())
		return
	}

	// Cleanup
	_ = os.Remove(filepath.Join(runDir, "type14.tmp"))
	removeGlob(runDir, "*.da*")

	// Do not print here to avoid interleaving; the progress lines handle reporting.
}

func removeGlob(dir, pattern string) {
	matches, _ := filepath.Glob(filepath.Join(dir, pattern))
	for _, p := range matches {
		_ = os.Remove(p)
	}
}

// Antenna mapping per band (keys like "3.500", "14.100", etc.)
func antForFreq(cfg Config, freq string) (string, string) {
	key := freqKey(freq)
	tx := cfg.TxAnt[key]
	rx := cfg.RxAnt[key]
	if tx == "" {
		tx = cfg.TxAnt["28.200"] // default to 10m as in Python fallback
	}
	if rx == "" {
		rx = cfg.RxAnt["28.200"]
	}
	return tx, rx
}

func freqKey(s string) string {
	// Normalize to 1 decimal or 3 decimals like in INI keys
	s = strings.TrimSpace(s)
	if s == "" {
		return "28.200"
	}
	// Keep as-is; INI uses exact strings (e.g., "14.100")
	return s
}

// ===================== INI parsing =====================

func readINI(path string) (Config, error) {
	f, err := os.Open(path)
	if err != nil {
		return Config{}, err
	}
	defer f.Close()

	sec := "default"
	c := Config{
		TxAnt: make(map[string]string),
		RxAnt: make(map[string]string),
	}
	r := bufio.NewReader(f)
	for {
		line, err := r.ReadString('\n')
		if err != nil && !errors.Is(err, io.EOF) {
			return Config{}, err
		}
		line = strings.TrimSpace(line)
		if i := strings.Index(line, "#"); i >= 0 {
			line = strings.TrimSpace(line[:i])
		}
		if i := strings.Index(line, ";"); i >= 0 {
			line = strings.TrimSpace(line[:i])
		}
		if line == "" {
			if errors.Is(err, io.EOF) {
				break
			}
			if errors.Is(err, nil) {
				continue
			}
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			sec = strings.ToLower(strings.Trim(line, "[]"))
		} else if kv := strings.SplitN(line, "=", 2); len(kv) == 2 {
			k := strings.ToLower(strings.TrimSpace(kv[0]))
			v := strings.TrimSpace(kv[1])
			switch sec {
			case "default":
				switch k {
				case "txlat":
					c.TxLat, _ = strconv.ParseFloat(v, 64)
				case "txlon":
					c.TxLon, _ = strconv.ParseFloat(v, 64)
				case "power":
					c.Power, _ = strconv.ParseFloat(v, 64)
				case "mode":
					c.Mode, _ = strconv.Atoi(v)
				case "es":
					c.Es, _ = strconv.ParseFloat(v, 64)
				case "method":
					c.Method, _ = strconv.Atoi(v)
				case "mintoa":
					c.MinToa, _ = strconv.ParseFloat(v, 64)
				case "noise":
					c.Noise, _ = strconv.Atoi(v)
				case "gridsize":
					c.GridSize, _ = strconv.Atoi(v)
				case "path":
					c.PathFlag = v
				}
			case "frequency":
				if k == "flist" {
					parts := strings.Fields(v)
					c.FList = make([]string, 0, len(parts))
					for _, p := range parts {
						if p != "" {
							c.FList = append(c.FList, p)
						}
					}
				}
			case "antenna":
				// Expect keys like txant20, rxant20, etc.
				if strings.HasPrefix(k, "txant") {
					c.TxAnt[antKeyFrom(k)] = v
				} else if strings.HasPrefix(k, "rxant") {
					c.RxAnt[antKeyFrom(k)] = v
				}
			}
		}
		if errors.Is(err, io.EOF) {
			break
		}
	}

	// Basic validation
	if len(c.FList) == 0 {
		return Config{}, fmt.Errorf("frequency.flist is empty")
	}
	return c, nil
}

func antKeyFrom(k string) string {
	// Map INI keys to exact frequency strings used in Python mapping
	// txant80 -> "3.500", txant60 -> "5.300", txant40 -> "7.100",
	// txant30 -> "10.100", txant20 -> "14.100", txant17 -> "18.100",
	// txant15 -> "21.200", txant12 -> "24.900", txant10 -> "28.200"
	switch {
	case strings.HasSuffix(k, "80"):
		return "3.500"
	case strings.HasSuffix(k, "60"):
		return "5.300"
	case strings.HasSuffix(k, "40"):
		return "7.100"
	case strings.HasSuffix(k, "30"):
		return "10.100"
	case strings.HasSuffix(k, "20"):
		return "14.100"
	case strings.HasSuffix(k, "17"):
		return "18.100"
	case strings.HasSuffix(k, "15"):
		return "21.200"
	case strings.HasSuffix(k, "12"):
		return "24.900"
	case strings.HasSuffix(k, "10"):
		return "28.200"
	default:
		return "28.200"
	}
}

// ===================== SSN =====================

func getSSN(path string, year, month int) int {
	f, err := os.Open(path)
	if err != nil {
		return -1
	}
	defer f.Close()

	target := fmt.Sprintf("%d %02d", year, month)
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if strings.Contains(line, target) {
			parts := strings.Fields(line)
			if len(parts) >= 5 {
				val := parts[4]
				if f64, err := strconv.ParseFloat(val, 64); err == nil {
					// Reduce forecasted future or current year slightly as in Python
					if year >= time.Now().UTC().Year() {
						f64 = roundHalfUp(f64*0.7, 0)
					}
					return int(f64)
				}
			}
			break
		}
	}
	return -1
}

func roundHalfUp(n float64, decimals int) float64 {
	mult := math.Pow(10, float64(decimals))
	return math.Floor(n*mult+0.5) / mult
}

// ===================== Helpers =====================

func repeatFloat(v float64, count, width, prec int) string {
	var b strings.Builder
	for i := 0; i < count; i++ {
		b.WriteString(fmt.Sprintf("%*.*f", width, prec, v))
	}
	return b.String()
}

func repeatInt(v, count, width int) string {
	var b strings.Builder
	for i := 0; i < count; i++ {
		b.WriteString(fmt.Sprintf("%*d", width, v))
	}
	return b.String()
}

func repeatString(s string, count, width int) string {
	var b strings.Builder
	for i := 0; i < count; i++ {
		b.WriteString(fmt.Sprintf("%*s", width, s))
	}
	return b.String()
}

func joinInts(vals []int, width int) string {
	var b strings.Builder
	for _, v := range vals {
		b.WriteString(fmt.Sprintf("%*d", width, v))
	}
	return b.String()
}

func ask(prompt string) string {
	fmt.Print(prompt)
	s, _ := stdin.ReadString('\n')
	return strings.TrimSpace(s)
}

func askYears(prompt string) []int {
	for {
		raw := ask(prompt)
		fields := strings.Fields(raw)
		var ys []int
		for _, f := range fields {
			if v, err := strconv.Atoi(f); err == nil && v >= 2021 && v <= 2100 {
				ys = append(ys, v)
			}
		}
		ys = uniqueInts(ys)
		sort.Ints(ys)
		if len(ys) > 0 {
			return ys
		}
	}
}

func askMonths(prompt string) []int {
	for {
		raw := ask(prompt)
		fields := strings.Fields(raw)
		var ms []int
		for _, f := range fields {
			if v, err := strconv.Atoi(f); err == nil && v >= 1 && v <= 12 {
				ms = append(ms, v)
			}
		}
		ms = uniqueInts(ms)
		sort.Ints(ms)
		if len(ms) > 0 {
			return ms
		}
	}
}

func askIntInRange(prompt string, lo, hi int) int {
	for {
		raw := ask(prompt)
		if v, err := strconv.Atoi(strings.TrimSpace(raw)); err == nil && v >= lo && v <= hi {
			return v
		}
	}
}

func uniqueInts(in []int) []int {
	seen := map[int]struct{}{}
	out := make([]int, 0, len(in))
	for _, v := range in {
		if _, ok := seen[v]; !ok {
			seen[v] = struct{}{}
			out = append(out, v)
		}
	}
	return out
}

// Maidenhead grid locator (precision fields: 3 -> 6 chars)
func latlon2loc(lat, lon float64, precision int) string {
	// Mirror Python logic
	A := int('A')
	a0 := divmod(lon+180, 20)
	b0 := divmod(lat+90, 10)
	as := string(rune(A+int(a0.quot))) + string(rune(A+int(b0.quot)))
	lonR := a0.rem / 2.0
	latR := b0.rem
	i := 1
	for i < precision {
		i++
		a := divmod(lonR, 1)
		b := divmod(latR, 1)
		if i%2 == 0 {
			as += fmt.Sprintf("%d%d", int(a.quot), int(b.quot))
			lonR = 24 * a.rem
			latR = 24 * b.rem
		} else {
			as += string(rune(A+int(a.quot))) + string(rune(A+int(b.quot)))
			lonR = 10 * a.rem
			latR = 10 * b.rem
		}
	}
	if len(as) >= 6 {
		as = as[:4] + strings.ToLower(as[4:6]) + as[6:]
	}
	return strings.ToUpper(as)
}

type div struct {
	quot float64
	rem  float64
}

func divmod(x, y float64) div {
	q := math.Floor(x / y)
	r := x - q*y
	return div{q, r}
}

func randomID8() string {
	rand.Seed(time.Now().UnixNano())
	return fmt.Sprintf("%08x", rand.Uint32())
}
