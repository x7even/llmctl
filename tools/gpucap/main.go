// gpucap: view and set the power cap on every amdgpu card, persistently.
//
//	gpucap                 summary: settings, clocks, temperatures per card (also `gpucap status`)
//	gpucap --settings      just the current settings and their allowed ranges
//	gpucap --all           every value we can read, per card
//	gpucap --help          usage, guidance and risk warning
//	gpucap set <watts>     write config and apply now (needs root)
//	gpucap undervolt <mV>  apply and save a GFX voltage offset (e.g. -50; 0 clears; needs root)
//	gpucap sclk <MHz>      apply and save a core clock offset (e.g. +50; 0 clears; needs root)
//	gpucap mclk <MHz>      apply and save a memory max clock (e.g. 1310; 0 = stock; needs root)
//	gpucap apply [watts]   apply configured (or given) cap and voltage offset; used by systemd
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"text/tabwriter"
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

	// defaultUVLimit is the deepest undervolt (mV, magnitude) gpucap accepts unless UV_LIMIT_MV in
	// /etc/gpucap.conf raises it. The driver range is usually wider (about -200 mV) but offsets that
	// deep are rarely stable; typical stable values are -30 to -80 mV and this varies per chip.
	defaultUVLimit = 100

	// defaultSclkLimit is the largest core clock offset (MHz) and defaultMclkLimit the highest memory max
	// clock (MHz) gpucap accepts unless SCLK_LIMIT_MHZ / MCLK_LIMIT_MHZ in /etc/gpucap.conf raise them.
	// The driver ranges are far wider (+1000 MHz, 1500 MHz). These defaults suit a Radeon AI PRO R9700
	// (stock memory max 1259 MHz); set your own limits for other cards.
	defaultSclkLimit = 150
	defaultMclkLimit = 1350
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
	capW    int // power cap in watts
	uvMV    int // GFX voltage offset in mV; 0 = stock, negative = undervolt
	uvLimit int // deepest undervolt allowed, mV magnitude

	sclkMHz   int // core clock offset in MHz; 0 = stock
	mclkMHz   int // memory max clock in MHz; 0 = stock
	sclkLimit int // largest core clock offset allowed, MHz
	mclkLimit int // highest memory max clock allowed, MHz
}

func loadConf() conf {
	c := conf{capW: defaultCap, uvLimit: defaultUVLimit, sclkLimit: defaultSclkLimit, mclkLimit: defaultMclkLimit}
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
		case "UV_LIMIT_MV":
			if n > 0 {
				c.uvLimit = n
			}
		case "SCLK_MHZ":
			c.sclkMHz = n
		case "MCLK_MHZ":
			c.mclkMHz = n
		case "SCLK_LIMIT_MHZ":
			if n > 0 {
				c.sclkLimit = n
			}
		case "MCLK_LIMIT_MHZ":
			if n > 0 {
				c.mclkLimit = n
			}
		}
	}
	return c
}

func saveConf(c conf) error {
	return os.WriteFile(confPath, []byte(fmt.Sprintf(
		"CAP_W=%d\nUV_MV=%d\nSCLK_MHZ=%d\nMCLK_MHZ=%d\nUV_LIMIT_MV=%d\nSCLK_LIMIT_MHZ=%d\nMCLK_LIMIT_MHZ=%d\n",
		c.capW, c.uvMV, c.sclkMHz, c.mclkMHz, c.uvLimit, c.sclkLimit, c.mclkLimit)), 0o644)
}

// odEnabled reports whether amdgpu's OverDrive feature bit is set in the running kernel.
func odEnabled() bool {
	b, err := os.ReadFile("/sys/module/amdgpu/parameters/ppfeaturemask")
	if err != nil {
		return false
	}
	m, err := strconv.ParseUint(strings.TrimSpace(string(b)), 0, 32)
	return err == nil && m&0x4000 != 0
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

// stat reads a numeric sysfs file, divides by div and formats it with f; "-" if unreadable.
func stat(path string, div float64, f string) string {
	v, err := readInt(path)
	if err != nil {
		return "-"
	}
	return fmt.Sprintf(f, float64(v)/div)
}

func readStr(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return "-"
	}
	return strings.TrimSpace(strings.ReplaceAll(string(b), "\x00", ""))
}

type column struct {
	head string
	get  func(c card) string
}

// columns holds every value status can show; the views below pick from it by header.
var columns = []column{
	{"CARD", func(c card) string { return c.name }},
	{"CAP W", func(c card) string { return stat(c.hwmon+"/power1_cap", 1e6, "%.0f") }},
	{"CAP RANGE W", func(c card) string {
		lo, _ := readInt(c.hwmon + "/power1_cap_min")
		hi, _ := readInt(c.hwmon + "/power1_cap_max")
		return fmt.Sprintf("%d-%d", lo/1e6, hi/1e6)
	}},
	{"DRAW W", func(c card) string { return stat(c.hwmon+"/power1_average", 1e6, "%.0f") }},
	{"V OFFSET mV", func(c card) string {
		if t, ok := readOD(c); ok && t.hasV {
			return strconv.Itoa(t.vo)
		}
		return "n/a"
	}},
	{"V RANGE mV", func(c card) string {
		if t, ok := readOD(c); ok && t.hasV {
			return fmt.Sprintf("%d..%d", t.voLo, t.voHi)
		}
		return "n/a"
	}},
	{"SCLK OFFSET MHz", func(c card) string {
		if t, ok := readOD(c); ok && t.hasS {
			return fmt.Sprintf("%+d", t.sclk)
		}
		return "n/a"
	}},
	{"SCLK RANGE MHz", func(c card) string {
		if t, ok := readOD(c); ok && t.hasS {
			return fmt.Sprintf("%d..%d", t.sLo, t.sHi)
		}
		return "n/a"
	}},
	{"MCLK MAX MHz", func(c card) string {
		if t, ok := readOD(c); ok && t.hasM {
			return strconv.Itoa(t.mMax)
		}
		return "n/a"
	}},
	{"MCLK RANGE MHz", func(c card) string {
		if t, ok := readOD(c); ok && t.hasM {
			return fmt.Sprintf("%d..%d", t.mLo, t.mHi)
		}
		return "n/a"
	}},
	{"VGFX mV", func(c card) string { return stat(c.hwmon+"/in0_input", 1, "%.0f") }},
	{"SCLK MHz", func(c card) string { return stat(c.hwmon+"/freq1_input", 1e6, "%.0f") }},
	{"MCLK MHz", func(c card) string { return stat(c.hwmon+"/freq2_input", 1e6, "%.0f") }},
	{"EDGE C", func(c card) string { return stat(c.hwmon+"/temp1_input", 1e3, "%.0f") }},
	{"JUNC C", func(c card) string { return stat(c.hwmon+"/temp2_input", 1e3, "%.0f") }},
	{"MEM C", func(c card) string { return stat(c.hwmon+"/temp3_input", 1e3, "%.0f") }},
	{"FAN RPM", func(c card) string { return stat(c.hwmon+"/fan1_input", 1, "%.0f") }},
	{"FAN %", func(c card) string {
		if v, err := readInt(c.hwmon + "/pwm1"); err == nil {
			return fmt.Sprintf("%.0f", float64(v)*100/255)
		}
		return "-"
	}},
	{"BUSY %", func(c card) string { return stat(c.dev+"/gpu_busy_percent", 1, "%.0f") }},
	{"VRAM GB", func(c card) string {
		u, err := readInt(c.dev + "/mem_info_vram_used")
		if err != nil {
			return "-"
		}
		t, _ := readInt(c.dev + "/mem_info_vram_total")
		return fmt.Sprintf("%.1f/%.0f", float64(u)/1e9, float64(t)/1e9)
	}},
	{"PCIE", func(c card) string {
		w := readStr(c.dev + "/current_link_width")
		sp := strings.Fields(readStr(c.dev + "/current_link_speed"))
		if w == "-" || len(sp) == 0 {
			return "-"
		}
		return fmt.Sprintf("x%s@%s", w, sp[0])
	}},
}

// Views of the column set, selected by the first argument to `gpucap`.
var views = map[string][]string{
	"summary":  {"CARD", "CAP W", "DRAW W", "V OFFSET mV", "VGFX mV", "SCLK OFFSET MHz", "SCLK MHz", "MCLK MAX MHz", "MCLK MHz", "EDGE C", "JUNC C", "MEM C"},
	"settings": {"CARD", "CAP W", "CAP RANGE W", "V OFFSET mV", "V RANGE mV", "SCLK OFFSET MHz", "SCLK RANGE MHz", "MCLK MAX MHz", "MCLK RANGE MHz"},
}

func mclkStr(mhz int) string {
	if mhz == 0 {
		return "stock"
	}
	return fmt.Sprintf("%dMHz", mhz)
}

func status(cards []card, view string) {
	cf := loadConf()
	fmt.Printf("configured: cap %dW, voltage %dmV, core %+dMHz, memory max %s (%s)\n", cf.capW, cf.uvMV, cf.sclkMHz, mclkStr(cf.mclkMHz), confPath)
	fmt.Printf("limits:     voltage -%dmV, core +%dMHz, memory max %dMHz\n", cf.uvLimit, cf.sclkLimit, cf.mclkLimit)
	if !odEnabled() {
		fmt.Println("voltage offset: OverDrive not enabled (run install.sh and reboot)")
	}
	var cols []column
	for _, c := range columns {
		if want, ok := views[view]; !ok || slices.Contains(want, c.head) { // "all": no entry, every column
			cols = append(cols, c)
		}
	}
	tw := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', tabwriter.AlignRight)
	for _, c := range cols {
		fmt.Fprint(tw, c.head, "\t")
	}
	fmt.Fprintln(tw)
	for _, cd := range cards {
		for _, c := range cols {
			fmt.Fprint(tw, c.get(cd), "\t")
		}
		fmt.Fprintln(tw)
	}
	tw.Flush()
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

const helpText = `gpucap - view and tune power cap, voltage and clocks on AMD GPUs

USAGE
  gpucap                  summary per card: settings, clocks, temperatures
  gpucap --settings       current settings and their allowed ranges
  gpucap --all            everything readable per card (fan, busy %, VRAM, PCIe...)
  sudo gpucap set <W>     power cap in watts
  sudo gpucap undervolt <mV>
                          GFX voltage offset, 0 or negative (e.g. -30); 0 clears
  sudo gpucap sclk <MHz>  core clock offset (e.g. +50); 0 clears
  sudo gpucap mclk <MHz>  memory max clock (e.g. 1310); 0 restores stock
  sudo gpucap apply [W]   re-apply all saved settings (what the boot/resume services run)
  gpucap --help           this text

  Each set command validates the value on every card, applies it, reads it back, and only
  then saves it to /etc/gpucap.conf so it is re-applied at boot and after suspend.

WARNING
  Changing power limits, voltages and clocks can damage your hardware, cause instability
  or data loss, and may void your warranty. Settings are applied at your own risk.
  A too-low voltage or too-high clock usually crashes the GPU rather than damaging it, but
  a crash can take down running jobs and may need a reboot. Memory overclocks can pass
  short tests and still corrupt results later. Raising the power cap above the card's stock
  limit adds heat and stress on the card and its power connectors: check PSU and cooling.
  Nothing here is guaranteed stable on your particular GPUs.

GUIDANCE
  Change one thing at a time, test it under sustained load for several minutes (watch
  gpucap for temperatures and clocks, and check the output of your workload), then move on.
  Every chip is different: test each card.
  Power cap   Lower caps cut heat and power at a modest speed cost. Allowed range per card:
              gpucap --settings.
  Undervolt   Start at -30 mV, step down 10-20 mV at a time, back off a step or two from the
              last stable value. Lets the card hold higher clocks at the same power.
              Refused beyond -100 mV unless UV_LIMIT_MV is raised in /etc/gpucap.conf.
  Core clock  Start at +25..+50 MHz and step up. Needs a stable undervolt/power headroom to
              help; under a tight power cap it often changes little.
              Refused beyond +150 MHz unless SCLK_LIMIT_MHZ is raised.
  Memory      Start about 2-3% above stock and step up slowly, comparing real results
              (not just "no crash"). Refused above MCLK_LIMIT_MHZ (default 1350, set for a
              Radeon AI PRO R9700 with 1259 MHz stock; set your own for other cards).
  Undo        sudo gpucap undervolt 0 / sclk 0 / mclk 0, or sudo gpucap set <max W>.
              Settings are saved and re-applied at boot: remove them from /etc/gpucap.conf
              (UV_MV, SCLK_MHZ, MCLK_MHZ) to stop that. A reboot resets the hardware to stock.
  Requires    root for set/undervolt/sclk/mclk/apply. Voltage and clock tuning also need amdgpu's
              OverDrive bit; install.sh enables it and needs one reboot.

FILES
  /etc/gpucap.conf        CAP_W, UV_MV, SCLK_MHZ, MCLK_MHZ and the *_LIMIT settings
`

// setOD handles `gpucap undervolt|sclk|mclk <value>`: validate and apply the new value on every
// card, and only then save it to the config so a bad value is never persisted.
func setOD(cmd string) {
	usage := map[string]string{
		"undervolt": "gpucap undervolt <mV>   (0 or negative, e.g. -30; 0 clears)",
		"sclk":      "gpucap sclk <MHz>       (core clock offset, e.g. +50; 0 clears)",
		"mclk":      "gpucap mclk <MHz>       (memory max clock, e.g. 1310; 0 restores stock)",
	}[cmd]
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "usage: "+usage)
		os.Exit(2)
	}
	arg := strings.ToLower(os.Args[2])
	arg = strings.TrimSuffix(strings.TrimSuffix(arg, "mhz"), "mv")
	v, err := strconv.Atoi(strings.TrimPrefix(arg, "+"))
	if err != nil || (cmd == "undervolt" && v > 0) || (cmd == "mclk" && v < 0) {
		fmt.Fprintf(os.Stderr, "invalid value %q\nusage: %s\n", os.Args[2], usage)
		os.Exit(2)
	}
	if os.Geteuid() != 0 {
		die(fmt.Errorf("must be root (sudo gpucap %s %s)", cmd, os.Args[2]))
	}
	cards := findCards()
	if len(cards) == 0 {
		die(fmt.Errorf("no amdgpu cards found"))
	}
	cf := loadConf()
	switch cmd {
	case "undervolt":
		cf.uvMV = v
	case "sclk":
		cf.sclkMHz = v
	case "mclk":
		cf.mclkMHz = v
	}
	// going back to the stock memory clock is only possible by restoring the boot table
	if err := applyOD(cards, cf.od(), cmd == "mclk" && v == 0); err != nil {
		die(err)
	}
	if err := saveConf(cf); err != nil {
		die(err)
	}
	fmt.Printf("saved to %s\n", confPath)
	if v != 0 {
		fmt.Println("note: stress-test before relying on this; an unstable setting can crash a GPU (see gpucap --help)")
	}
}

func main() {
	cmd := "status"
	if len(os.Args) > 1 {
		cmd = os.Args[1]
	}
	switch cmd {
	case "help", "--help", "-h":
		fmt.Print(helpText)
	case "status", "--summary":
		status(findCards(), "summary")
	case "--settings":
		status(findCards(), "settings")
	case "--all":
		status(findCards(), "all")
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
	case "undervolt", "sclk", "mclk":
		setOD(cmd)
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
		// failed voltage/clock settings must not fail the unit and hide that the cap was applied
		if err := applyOD(cards, cf.od(), false); err != nil {
			fmt.Fprintln(os.Stderr, "warning:", err)
		}
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q; run gpucap --help\n", cmd)
		os.Exit(2)
	}
}
