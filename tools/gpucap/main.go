// gpucap: view and set the power cap on every amdgpu card, persistently.
//
//	gpucap status          show cap/min/max/draw per card
//	gpucap set <watts>     write config and apply now (needs root)
//	gpucap undervolt <mV>  write config and apply a GFX voltage offset now (e.g. -50; 0 clears; needs root)
//	gpucap apply [watts]   apply configured (or given) cap and voltage offset; used by systemd
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	confPath = "/etc/gpucap.conf"

	// defaultCap is the cap in watts used when /etc/gpucap.conf does not exist or has no
	// CAP_W line. 230 is just the value for the machine this was written for.
	// To make a different cap persist across reboots, either run `sudo gpucap set <watts>`
	// (writes CAP_W to /etc/gpucap.conf, which is what the boot/resume units read), or change
	// this value (and the matching CAP_W in install.sh) and rebuild.
	defaultCap = 230
)

type card struct {
	name  string
	dev   string // .../card0/device
	hwmon string // .../hwmon/hwmonN
}

func readInt(path string) (int64, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return 0, err
	}
	return strconv.ParseInt(strings.TrimSpace(string(b)), 10, 64)
}

func findCards() []card {
	var out []card
	devs, _ := filepath.Glob("/sys/class/drm/card[0-9]*/device")
	for _, d := range devs {
		if v, err := os.ReadFile(d + "/vendor"); err != nil || strings.TrimSpace(string(v)) != "0x1002" {
			continue
		}
		hm, _ := filepath.Glob(d + "/hwmon/hwmon*/power1_cap")
		if len(hm) == 0 {
			continue
		}
		out = append(out, card{filepath.Base(filepath.Dir(d)), d, filepath.Dir(hm[0])})
	}
	return out
}

func waitCards(timeout time.Duration) []card {
	deadline := time.Now().Add(timeout)
	for {
		if c := findCards(); len(c) > 0 || time.Now().After(deadline) {
			if len(c) > 0 {
				time.Sleep(2 * time.Second) // let the driver settle
				return findCards()
			}
			return c
		}
		time.Sleep(time.Second)
	}
}

type conf struct {
	capW int // power cap in watts
	uvMV int // GFX voltage offset in mV; 0 = stock, negative = undervolt
}

func loadConf() conf {
	c := conf{capW: defaultCap}
	b, err := os.ReadFile(confPath)
	if err != nil {
		return c
	}
	for _, l := range strings.Split(string(b), "\n") {
		k, v, ok := strings.Cut(strings.TrimSpace(l), "=")
		if !ok {
			continue
		}
		n, err := strconv.Atoi(strings.TrimSpace(v))
		if err != nil {
			continue
		}
		switch strings.TrimSpace(k) {
		case "CAP_W":
			c.capW = n
		case "UV_MV":
			c.uvMV = n
		}
	}
	return c
}

func saveConf(c conf) error {
	return os.WriteFile(confPath, []byte(fmt.Sprintf("CAP_W=%d\nUV_MV=%d\n", c.capW, c.uvMV)), 0o644)
}

// Voltage offset (RDNA3/RDNA4). Needs amdgpu.ppfeaturemask with the OverDrive bit (0x4000) set;
// otherwise pp_od_clk_voltage does not exist and the offset is reported as unavailable.
const odFile = "/pp_od_clk_voltage"

var (
	reOffset = regexp.MustCompile(`(?m)^OD_VDDGFX_OFFSET:\s*\n\s*(-?\d+)\s*mV`)
	reRange  = regexp.MustCompile(`(?m)^VDDGFX_OFFSET:\s*(-?\d+)\s*mV\s+(-?\d+)\s*mV`)
)

// parseOD extracts the current GFX voltage offset and its allowed range (mV) from the contents
// of pp_od_clk_voltage. ok is false when the table has no VDDGFX offset entry.
func parseOD(table string) (cur, lo, hi int, ok bool) {
	m := reOffset.FindStringSubmatch(table)
	if m == nil {
		return 0, 0, 0, false
	}
	cur, _ = strconv.Atoi(m[1])
	if r := reRange.FindStringSubmatch(table); r != nil {
		lo, _ = strconv.Atoi(r[1])
		hi, _ = strconv.Atoi(r[2])
	} else {
		lo, hi = -200, 0 // range line missing: allow undervolt only, conservative
	}
	return cur, lo, hi, true
}

func readOD(c card) (cur, lo, hi int, ok bool) {
	b, err := os.ReadFile(c.dev + odFile)
	if err != nil {
		return 0, 0, 0, false
	}
	return parseOD(string(b))
}

func applyOffset(cards []card, mv int) error {
	var failed int
	for _, c := range cards {
		_, lo, hi, ok := readOD(c)
		if !ok {
			if mv == 0 {
				continue // nothing to clear
			}
			fmt.Fprintf(os.Stderr, "%s: voltage offset unavailable (is amdgpu.ppfeaturemask OverDrive bit 0x4000 set?)\n", c.name)
			failed++
			continue
		}
		if mv < lo || mv > hi {
			fmt.Fprintf(os.Stderr, "%s: %dmV outside allowed %d..%dmV\n", c.name, mv, lo, hi)
			failed++
			continue
		}
		// "vo" stages the offset, "c" commits it
		var err error
		for _, cmd := range []string{fmt.Sprintf("vo %d", mv), "c"} {
			if err = os.WriteFile(c.dev+odFile, []byte(cmd+"\n"), 0); err != nil {
				break
			}
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: %v\n", c.name, err)
			failed++
			continue
		}
		if got, _, _, _ := readOD(c); got != mv {
			fmt.Fprintf(os.Stderr, "%s: wrote %dmV but read back %dmV\n", c.name, mv, got)
			failed++
			continue
		}
		fmt.Printf("%s offset=%dmV\n", c.name, mv)
	}
	if failed > 0 {
		return fmt.Errorf("%d card(s) failed", failed)
	}
	return nil
}

func apply(cards []card, watts int) error {
	var failed int
	for _, c := range cards {
		minU, _ := readInt(c.hwmon + "/power1_cap_min")
		maxU, _ := readInt(c.hwmon + "/power1_cap_max")
		w := int64(watts) * 1_000_000
		if (maxU > 0 && w > maxU) || w < minU {
			fmt.Fprintf(os.Stderr, "%s: %dW outside allowed %d-%dW\n", c.name, watts, minU/1e6, maxU/1e6)
			failed++
			continue
		}
		_ = os.WriteFile(c.dev+"/power/control", []byte("on"), 0)
		var err error
		for try := 0; try < 5; try++ {
			if err = os.WriteFile(c.hwmon+"/power1_cap", []byte(strconv.FormatInt(w, 10)), 0); err == nil {
				break
			}
			time.Sleep(time.Second)
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: %v\n", c.name, err)
			failed++
			continue
		}
		got, _ := readInt(c.hwmon + "/power1_cap")
		fmt.Printf("%s cap=%dW\n", c.name, got/1_000_000)
	}
	if failed > 0 {
		return fmt.Errorf("%d card(s) failed", failed)
	}
	return nil
}

func status(cards []card) {
	cf := loadConf()
	fmt.Printf("configured: %dW, %dmV (%s)\n", cf.capW, cf.uvMV, confPath)
	for _, c := range cards {
		cap, _ := readInt(c.hwmon + "/power1_cap")
		minU, _ := readInt(c.hwmon + "/power1_cap_min")
		maxU, _ := readInt(c.hwmon + "/power1_cap_max")
		avg, _ := readInt(c.hwmon + "/power1_average")
		uv := "offset=n/a"
		if cur, lo, hi, ok := readOD(c); ok {
			uv = fmt.Sprintf("offset=%dmV (range %d..%dmV)", cur, lo, hi)
		}
		fmt.Printf("%s cap=%dW (range %d-%dW) draw=%dW %s\n", c.name, cap/1e6, minU/1e6, maxU/1e6, avg/1e6, uv)
	}
}

func parseWatts(s string) int {
	w, err := strconv.Atoi(strings.TrimSuffix(strings.ToLower(s), "w"))
	if err != nil || w <= 0 {
		fmt.Fprintf(os.Stderr, "invalid watts %q\n", s)
		os.Exit(2)
	}
	return w
}

func die(err error) {
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}

func main() {
	cmd := "status"
	if len(os.Args) > 1 {
		cmd = os.Args[1]
	}
	switch cmd {
	case "status":
		status(findCards())
	case "set":
		if len(os.Args) < 3 {
			fmt.Fprintln(os.Stderr, "usage: gpucap set <watts>")
			os.Exit(2)
		}
		w := parseWatts(os.Args[2])
		if os.Geteuid() != 0 {
			die(fmt.Errorf("must be root (sudo gpucap set %d)", w))
		}
		cards := findCards()
		if len(cards) == 0 {
			die(fmt.Errorf("no amdgpu cards found"))
		}
		// validate/apply first so a bad value is never persisted
		if err := apply(cards, w); err != nil {
			die(err)
		}
		cf := loadConf()
		cf.capW = w
		if err := saveConf(cf); err != nil {
			die(err)
		}
		fmt.Printf("saved %dW to %s\n", w, confPath)
	case "undervolt":
		if len(os.Args) < 3 {
			fmt.Fprintln(os.Stderr, "usage: gpucap undervolt <mV>  (e.g. -50; 0 clears)")
			os.Exit(2)
		}
		mv, err := strconv.Atoi(strings.TrimSuffix(strings.ToLower(os.Args[2]), "mv"))
		if err != nil || mv > 0 {
			fmt.Fprintf(os.Stderr, "invalid offset %q (must be 0 or negative mV)\n", os.Args[2])
			os.Exit(2)
		}
		if os.Geteuid() != 0 {
			die(fmt.Errorf("must be root (sudo gpucap undervolt %d)", mv))
		}
		cards := findCards()
		if len(cards) == 0 {
			die(fmt.Errorf("no amdgpu cards found"))
		}
		if err := applyOffset(cards, mv); err != nil {
			die(err)
		}
		cf := loadConf()
		cf.uvMV = mv
		if err := saveConf(cf); err != nil {
			die(err)
		}
		fmt.Printf("saved %dmV to %s\n", mv, confPath)
	case "apply":
		cf := loadConf()
		w := cf.capW
		if len(os.Args) > 2 {
			w = parseWatts(os.Args[2])
		}
		cards := waitCards(60 * time.Second)
		if len(cards) == 0 {
			die(fmt.Errorf("no amdgpu cards found"))
		}
		if err := apply(cards, w); err != nil {
			die(err)
		}
		// a failed offset must not fail the unit and hide that the cap was applied
		if err := applyOffset(cards, cf.uvMV); err != nil {
			fmt.Fprintln(os.Stderr, "warning:", err)
		}
	default:
		fmt.Fprintln(os.Stderr, "usage: gpucap status | set <watts> | undervolt <mV> | apply [watts]")
		os.Exit(2)
	}
}
