/*
Copyright 2025 Jari Perkiömäki OH6BG

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

/*
Usage examples:

go run ./plot_maps.go
go run ./plot_maps.go --root "/home/user/predictions/24985382" --maps "ALL" --workers 4
go run ./plot_maps.go --root "/home/user/predictions/24985382" --maps "SDBW,SNR50" --progress=false

Compile the code to an executable:

go build -o plotmaps.exe ./plot_maps.go
./plotmaps.exe --root "/home/user/predictions/24985382" --maps "SDBW,SNR50"

The progress counter is ON by default. Use Ctrl+C to cancel plotting.
*/

package main

import (
	"bufio"
	"context"
	"errors"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// Hardcoded tool paths (edit to match your system)
const (
	pythonExe      = `/usr/bin/python`
	plotScriptPath = `/home/user/pythonprop/src/pythonprop/voaAreaPlot.py`
	perPlotTimeout = 60 * time.Second // default timeout; not prompted
)

type mapCfg struct {
	DFlag string // -d flag to voaAreaPlot.py
	Dir   string // subdirectory name
}

var (
	// Map type configuration (extendable)
	mapTypes = map[string]mapCfg{
		"MUF":   {DFlag: "1", Dir: "MUF"},
		"REL":   {DFlag: "2", Dir: "REL"},
		"SNR50": {DFlag: "3", Dir: "SNR50"},
		"SNR90": {DFlag: "4", Dir: "SNR90"},
		"SDBW":  {DFlag: "5", Dir: "SDBW"},
	}

	// Patterns
	reVgNum  = regexp.MustCompile(`(?i)\.vg(\d+)$`)
	reUtHour = regexp.MustCompile(`(?i)\b([01]?\d|2[0-4])\s*(?:UT|UTC|Z)\b`)
	reMHz    = regexp.MustCompile(`(?i)(\d+(?:\.\d+)?)\s*MHz\b`)
	reFreq   = regexp.MustCompile(`(?i)\bF(?:REQ)?\s*[=:]\s*(\d+(?:\.\d+)?)\b`)
)

// CLI flags
var (
	rootPath = flag.String("root", "", "Root path to VOACAP outputs (contains year/month subfolders with .voa/.vg* files)")
	mapsFlag = flag.String("maps", "", "Comma-separated map types: MUF,REL,SNR50,SNR90,SDBW (or ALL)")
	workers  = flag.Int("workers", max(1, runtime.NumCPU()), "Max parallel plots")
	progress = flag.Bool("progress", true, "Show live progress")
)

func main() {
	flag.Parse()

	// Interactive prompts if required fields are missing
	if strings.TrimSpace(*rootPath) == "" {
		*rootPath = askUntilValidDir("Enter ROOT directory (contains year/month subfolders): ")
	}
	if strings.TrimSpace(*mapsFlag) == "" {
		fmt.Println("Select maps to plot (comma-separated) from: MUF, REL, SNR50, SNR90, SDBW or 'ALL'")
		*mapsFlag = ask("Maps: ")
	}

	// Validate hardcoded tool paths
	if st, err := os.Stat(pythonExe); err != nil || st.IsDir() {
		fmt.Fprintf(os.Stderr, "Error: python interpreter not found: %s\n", pythonExe)
		os.Exit(2)
	}
	if st, err := os.Stat(plotScriptPath); err != nil || st.IsDir() {
		fmt.Fprintf(os.Stderr, "Error: plot script not found: %s\n", plotScriptPath)
		os.Exit(2)
	}

	root := filepath.Clean(*rootPath)

	// Normalize/validate selected maps
	selected, err := parseSelectedMaps(*mapsFlag)
	if err != nil || len(selected) == 0 {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(2)
	}

	// Discover newest .voa per directory once
	voaFiles, err := newestVoaPerDir(root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error scanning .voa files: %v\n", err)
		os.Exit(1)
	}
	if len(voaFiles) == 0 {
		fmt.Fprintf(os.Stderr, "No .voa files found under %s\n", root)
		os.Exit(1)
	}

	start := time.Now()
	fmt.Printf("Plotting maps (%s) with %d workers...\n", strings.Join(selected, ","), *workers)

	// Shared context and Ctrl+C handling
	rootCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Build tasks = combinations of (.voa, matching .vg*, selected map types)
	tasks := make(chan task, 1024)
	var wg sync.WaitGroup

	// Optional progress tracking
	doneCh := make(chan struct{}, 4096)
	var printerWG sync.WaitGroup
	var completed int
	var total int

	// Start worker pool
	nw := max(1, *workers)
	for i := 0; i < nw; i++ {
		wg.Add(1)
		go worker(rootCtx, tasks, &wg, pythonExe, plotScriptPath, perPlotTimeout, doneCh)
	}

	// Enqueue tasks
	enqCount := 0
enqueue:
	for _, voa := range voaFiles {
		select {
		case <-rootCtx.Done():
			break enqueue
		default:
		}
		vgList, err := listSiblingVG(voa)
		if err != nil || len(vgList) == 0 {
			fmt.Fprintf(os.Stderr, "Warn: no matching VG files near %s: %v\n", voa, err)
			continue
		}

		// Determine Year/Month from the VOA directory relative to ROOT
		year, month := yearMonthFrom(filepath.Dir(voa), root)

		for _, vg := range vgList {
			select {
			case <-rootCtx.Done():
				break enqueue
			default:
			}
			vgNum := vgNumber(vg)
			if vgNum == "" {
				fmt.Fprintf(os.Stderr, "Warn: skip VG without selector (.vgN): %s\n", vg)
				continue
			}
			hh, ff := extractHourAndMHz(vg)
			for _, m := range selected {
				cfg := mapTypes[m]
				// Output under ROOT/<TYPE>/<Year>/<Month>/
				outDir := filepath.Join(root, cfg.Dir, year, month)
				outFile := filepath.Join(outDir, fmt.Sprintf("%sUT-%sMHz.png", hh, ff))
				// Skip enqueue if the target already exists
				if _, err := os.Stat(outFile); err == nil {
					continue
				}
				t := task{
					VOA:     voa,
					VG:      vg,
					VGNum:   vgNum,
					MapType: m,
					DFlag:   cfg.DFlag,
					OutDir:  outDir,
					OutFile: outFile,
				}
				select {
				case tasks <- t:
					enqCount++
				case <-rootCtx.Done():
					break enqueue
				}
			}
		}
	}

	close(tasks)
	total = enqCount

	// Progress printer
	if *progress {
		printerWG.Add(1)
		go func() {
			defer printerWG.Done()
			ticker := time.NewTicker(500 * time.Millisecond)
			defer ticker.Stop()
			for {
				select {
				case <-ticker.C:
					fmt.Printf("\rProgress: %d/%d", completed, total)
				case _, ok := <-doneCh:
					if !ok {
						fmt.Printf("\rProgress: %d/%d\n", completed, total)
						return
					}
					completed++
				}
			}
		}()
	}

	wg.Wait()

	if *progress {
		close(doneCh)
		printerWG.Wait()
	}

	if err := rootCtx.Err(); err != nil && err != context.Canceled {
		fmt.Fprintf(os.Stderr, "Stopped: %v\n", err)
	}
	fmt.Printf("Done. Plots attempted: %d in %s\n", enqCount, time.Since(start).Truncate(time.Millisecond))
}

func parseSelectedMaps(raw string) ([]string, error) {
	r := strings.TrimSpace(strings.ToUpper(raw))
	if r == "ALL" {
		out := make([]string, 0, len(mapTypes))
		for k := range mapTypes {
			out = append(out, k)
		}
		sort.Strings(out)
		return out, nil
	}
	parts := strings.Split(r, ",")
	seen := map[string]bool{}
	var sel []string
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		if _, ok := mapTypes[p]; !ok {
			return nil, fmt.Errorf("unknown map type %q (valid: %s)", p, strings.Join(keys(mapTypes), ","))
		}
		if !seen[p] {
			seen[p] = true
			sel = append(sel, p)
		}
	}
	sort.Strings(sel)
	return sel, nil
}

func keys(m map[string]mapCfg) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func newestVoaPerDir(root string) ([]string, error) {
	dirNewest := map[string]string{}
	dirMtime := map[string]time.Time{}
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if strings.EqualFold(filepath.Ext(path), ".voa") {
			info, e := d.Info()
			if e != nil {
				return e
			}
			dir := filepath.Dir(path)
			mt := info.ModTime()
			if prev, ok := dirNewest[dir]; !ok {
				dirNewest[dir] = path
				dirMtime[dir] = mt
			} else if mt.After(dirMtime[dir]) {
				dirNewest[dir] = path
				dirMtime[dir] = mt
			} else if mt.Equal(dirMtime[dir]) && path > prev {
				dirNewest[dir] = path
			}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	out := make([]string, 0, len(dirNewest))
	for _, p := range dirNewest {
		out = append(out, p)
	}
	sort.Strings(out)
	return out, nil
}

func listSiblingVG(voa string) ([]string, error) {
	dir := filepath.Dir(voa)
	base := strings.TrimSuffix(filepath.Base(voa), filepath.Ext(voa))
	wantPrefix := strings.ToLower(base) + ".vg"

	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []string
	for _, e := range ents {
		if e.IsDir() {
			continue
		}
		name := e.Name()
		lname := strings.ToLower(name)
		// only VG files that belong to this VOA basename
		if strings.HasPrefix(lname, wantPrefix) {
			out = append(out, filepath.Join(dir, name))
		}
	}
	// Sort by numeric suffix (vg index) if present, else by name
	sort.Slice(out, func(i, j int) bool {
		ni, _ := strconv.Atoi(vgNumber(out[i]))
		nj, _ := strconv.Atoi(vgNumber(out[j]))
		if ni != 0 && nj != 0 {
			return ni < nj
		}
		return out[i] < out[j]
	})
	return out, nil
}

func vgNumber(vg string) string {
	m := reVgNum.FindStringSubmatch(strings.ToLower(vg))
	if len(m) == 2 {
		return m[1]
	}
	// fallback: last digits of extension
	ext := strings.ToLower(filepath.Ext(vg))
	for i := len(ext) - 1; i >= 0; i-- {
		if ext[i] < '0' || ext[i] > '9' {
			return ext[i+1:]
		}
	}
	return ""
}

// Robust hour/frequency extraction: scan up to N lines with regex; fallback to second-line heuristic
func extractHourAndMHz(vg string) (hh2, ff2 string) {
	f, err := os.Open(vg)
	if err != nil {
		return "00", "00"
	}
	defer f.Close()

	sc := bufio.NewScanner(f)
	// allow larger lines
	buf := make([]byte, 0, 64*1024)
	sc.Buffer(buf, 1<<20)

	hour := -1
	freq := -1
	second := ""
	lineIdx := 0

	for sc.Scan() {
		line := sc.Text()
		lineIdx++
		if lineIdx == 2 {
			second = line
		}
		if hour < 0 {
			if m := reUtHour.FindStringSubmatch(line); len(m) == 2 {
				if h, err := atoiSafe(m[1]); err == nil {
					hour = ((h % 24) + 24) % 24
				}
			}
		}
		if freq < 0 {
			if m := reMHz.FindStringSubmatch(line); len(m) == 2 {
				if v, err := atoiSafe(m[1]); err == nil {
					freq = clamp(v, 0, 99)
				}
			} else if m := reFreq.FindStringSubmatch(line); len(m) == 2 {
				if v, err := atoiSafe(m[1]); err == nil {
					freq = clamp(v, 0, 99)
				}
			}
		}
		if hour >= 0 && freq >= 0 {
			break
		}
		if lineIdx >= 50 { // don't scan entire file
			break
		}
	}

	// Heuristic fallbacks
	if hour < 0 && second != "" {
		toks := strings.Fields(second)
		if len(toks) >= 4 {
			if h, err := atoiSafe(toks[len(toks)-4]); err == nil {
				hour = ((h % 24) + 24) % 24
			}
		}
	}
	if freq < 0 && second != "" {
		toks := strings.Fields(second)
		for i := len(toks) - 1; i >= 0; i-- {
			t := strings.TrimSuffix(strings.ToUpper(toks[i]), "MHZ")
			if v, err := atoiSafe(t); err == nil {
				freq = clamp(v, 0, 99)
				break
			}
		}
	}

	if hour < 0 {
		hour = 0
	}
	if freq < 0 {
		freq = 0
	}
	return fmt.Sprintf("%02d", hour), fmt.Sprintf("%02d", freq)
}

func atoiSafe(s string) (int, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0, errors.New("empty")
	}
	// parse leading integer part
	sign := 1
	if s[0] == '-' {
		sign = -1
		s = s[1:]
	}
	n := 0
	did := false
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c < '0' || c > '9' {
			break
		}
		did = true
		n = n*10 + int(c-'0')
	}
	if !did {
		return 0, errors.New("no digits")
	}
	return sign * n, nil
}

type task struct {
	VOA     string
	VG      string
	VGNum   string
	MapType string
	DFlag   string
	OutDir  string
	OutFile string
}

func worker(ctx context.Context, jobs <-chan task, wg *sync.WaitGroup, python, plot string, perTimeout time.Duration, done chan<- struct{}) {
	defer wg.Done()
	for {
		select {
		case <-ctx.Done():
			return
		case t, ok := <-jobs:
			if !ok {
				return
			}
			// If the target already exists (race), mark done and skip
			if _, err := os.Stat(t.OutFile); err == nil {
				if done != nil {
					done <- struct{}{}
				}
				continue
			}
			if err := os.MkdirAll(t.OutDir, 0o755); err != nil {
				fmt.Fprintf(os.Stderr, "ERROR: mkdir %s: %v\n", t.OutDir, err)
				if done != nil {
					done <- struct{}{}
				}
				continue
			}

			taskCtx, cancel := context.WithTimeout(ctx, perTimeout)
			cmd := exec.CommandContext(taskCtx, python, plot, "-f", "-d", t.DFlag, "-o", t.OutFile, "-v", t.VGNum, t.VOA)
			out, err := cmd.CombinedOutput()
			cancel()

			if taskCtx.Err() == context.DeadlineExceeded {
				fmt.Fprintf(os.Stderr, "Timeout plotting %s for %s\n", t.MapType, filepath.Base(t.VG))
			} else if err != nil {
				fmt.Fprintf(os.Stderr, "Plot failed [%s] %s -> %s: %v\n%s\n",
					t.MapType, filepath.Base(t.VG), filepath.Base(t.OutFile), err, string(out))
			}
			if done != nil {
				done <- struct{}{}
			}
		}
	}
}

func yearMonthFrom(voaDir, root string) (year, month string) {
	rel, err := filepath.Rel(root, voaDir)
	if err != nil || rel == "." || strings.HasPrefix(rel, "..") {
		return "Unknown", "Unknown"
	}
	parts := strings.Split(rel, string(os.PathSeparator))
	switch len(parts) {
	case 0:
		return "Unknown", "Unknown"
	case 1:
		return parts[0], "Unknown"
	default:
		return parts[0], parts[1]
	}
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

// --------------- Minimal interactive helpers ---------------

var stdin = bufio.NewReader(os.Stdin)

func ask(prompt string) string {
	fmt.Print(prompt)
	s, _ := stdin.ReadString('\n')
	return strings.TrimSpace(s)
}

func askUntilValidDir(prompt string) string {
	for {
		p := ask(prompt)
		if p == "" {
			continue
		}
		p = filepath.Clean(p)
		if st, err := os.Stat(p); err == nil && st.IsDir() {
			return p
		}
		fmt.Println("Path does not exist or is not a directory. Try again.")
	}
}
