// gpucap: view and set the power cap on every amdgpu card, persistently.
//
//	gpucap status          show cap/min/max/draw per card
//	gpucap set <watts>     write config and apply now (needs root)
//	gpucap apply [watts]   apply configured (or given) cap; used by systemd
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const (
	confPath   = "/etc/gpucap.conf"
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

func loadConf() int {
	b, err := os.ReadFile(confPath)
	if err != nil {
		return defaultCap
	}
	for _, l := range strings.Split(string(b), "\n") {
		k, v, ok := strings.Cut(strings.TrimSpace(l), "=")
		if ok && strings.TrimSpace(k) == "CAP_W" {
			if w, err := strconv.Atoi(strings.TrimSpace(v)); err == nil {
				return w
			}
		}
	}
	return defaultCap
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
	fmt.Printf("configured: %dW (%s)\n", loadConf(), confPath)
	for _, c := range cards {
		cap, _ := readInt(c.hwmon + "/power1_cap")
		minU, _ := readInt(c.hwmon + "/power1_cap_min")
		maxU, _ := readInt(c.hwmon + "/power1_cap_max")
		avg, _ := readInt(c.hwmon + "/power1_average")
		fmt.Printf("%s cap=%dW (range %d-%dW) draw=%dW\n", c.name, cap/1e6, minU/1e6, maxU/1e6, avg/1e6)
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
		if err := os.WriteFile(confPath, []byte(fmt.Sprintf("CAP_W=%d\n", w)), 0o644); err != nil {
			die(err)
		}
		fmt.Printf("saved %dW to %s\n", w, confPath)
	case "apply":
		w := loadConf()
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
	default:
		fmt.Fprintln(os.Stderr, "usage: gpucap status | set <watts> | apply [watts]")
		os.Exit(2)
	}
}
