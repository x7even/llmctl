# gpucap

A small Linux command-line tool to view and set the power cap, and (on RDNA3/RDNA4) the voltage offset and clocks, of every AMD GPU, and keep them across reboots and suspend/resume.

> **This is just a standalone tool that happens to live in this repo.** It is in no way required to run llmctl / llmstack
> or any model on it. The stack works the same without it, and nothing in the stack depends on or references it.
> It exists only because one machine had an external power limit.

**It has no defaults and applies nothing until you ask it to.** Installing gpucap does not change your
power limit, voltage or clocks: with no `/etc/gpucap.conf` the boot and resume units run, find nothing
configured, change nothing and exit successfully. An existing `/etc/gpucap.conf` is always preserved and
is the only thing they apply.

## Usage

```
gpucap                 summary table per card: cap, draw, voltage offset, live voltage, clocks, temperatures
gpucap --settings      just the current settings (cap, voltage offset, clocks) and their allowed ranges
gpucap --all           everything readable per card: adds fan, busy %, VRAM, PCIe link and the ranges
                       (`gpucap status` is the same as plain `gpucap`)
gpucap --help          usage, tuning guidance and the risk warning
gpucap set <watts>     write /etc/gpucap.conf and apply now (needs root)
gpucap undervolt <mV>  GFX voltage offset, 0 or negative (e.g. -30); 0 clears (needs root)
gpucap sclk <MHz>      core clock offset (e.g. +50); 0 clears (needs root)
gpucap mclk <MHz>      memory max clock (e.g. 1310); 0 restores stock (needs root)
gpucap apply [watts]   apply the configured (or given) cap plus saved voltage/clock settings; this is what the systemd units run.
                       With nothing configured it changes nothing and exits 0
```

`<watts>` can be written `300` or `300w`. A value outside a card's allowed range is rejected for that card
(the range is shown by `gpucap status`). Until you run `gpucap set`, `status` reports `cap none` and the units
leave the cards alone.

Example:

```
$ gpucap
configured: cap none, voltage 0mV, core +0MHz, memory max stock (/etc/gpucap.conf)
limits:     voltage -100mV, core +150MHz, memory max 1350MHz
   CARD  CAP W  DRAW W  V OFFSET mV  VGFX mV  SCLK OFFSET MHz  SCLK MHz  MCLK MAX MHz  MCLK MHz  EDGE C  JUNC C  MEM C
  card0    300     180           +0      950               +0      2900          1259      1258      62      71     66
...
$ sudo gpucap set 280
```

It works through the amdgpu hwmon files (`/sys/class/drm/card*/device/hwmon/*/power1_cap`), so it only sees
AMD cards with a power-cap sysfs entry.

## Voltage and clock tuning (optional, RDNA3/RDNA4)

> **Warning:** changing power limits, voltages and clocks can damage your hardware, cause instability or data loss, and may
> void your warranty. You use this at your own risk. Run `gpucap --help` for guidance.

Three settings are written to `/sys/class/drm/card*/device/pp_od_clk_voltage`, the commands the SMU13/SMU14 driver code parses:

| Command | Writes | Meaning |
|---|---|---|
| `gpucap undervolt <mV>` | `vo <mV>` | voltage offset applied to the whole V/F curve |
| `gpucap sclk <MHz>` | `s <MHz>` | core clock offset |
| `gpucap mclk <MHz>` | `m 1 <MHz>` | memory max clock (`0` restores the boot table with `r`) |

Each is followed by `c` to commit. gpucap checks every value against the card's reported range and its own limits on all cards
before writing anything, reads the table back to verify, and only then saves the value to `/etc/gpucap.conf`. `apply`
(boot/resume) re-applies the saved settings after the cap; a failed voltage/clock setting only warns, so the cap still applies.

A zero in the config means *not requested*, not *reset to zero*: `apply` writes nothing to
`pp_od_clk_voltage` unless `UV_MV`, `SCLK_MHZ` or `MCLK_MHZ` is non-zero, so it never clobbers an offset
set by another tool. To reset one deliberately, ask for it: `sudo gpucap undervolt 0` does write `vo 0`.

**Limits:** the driver ranges are wide (about -200 mV, +1000 MHz core, 1500 MHz memory) but settings that far are rarely stable.
gpucap refuses anything past `UV_LIMIT_MV` (default 100), `SCLK_LIMIT_MHZ` (default 150) and `MCLK_LIMIT_MHZ` (default 1350,
chosen for a Radeon AI PRO R9700 with 1259 MHz stock) unless you raise them in `/etc/gpucap.conf`; set limits that suit your cards.
Typical stable undervolts are -30 to -80 mV and vary per chip: start small, change one thing at a time, stress-test each card,
and compare real results. Too aggressive a setting shows up as hangs, crashes or (for memory) corrupt output, not as an error.

**Prerequisite, and it is opt-in:** the file only exists when amdgpu's OverDrive bit (`0x4000`) is set in
`amdgpu.ppfeaturemask`, which the default does not do. A plain `sudo ./install.sh` does not touch it. Ask for it with
`sudo ./install.sh --enable-overdrive`, which ORs that bit into the running mask, writes
`/etc/modprobe.d/gpucap-overdrive.conf`, rebuilds the initramfs, and tells you to **reboot once**. Enabling the bit tunes
nothing by itself; after the reboot, changing a setting is a live write and never needs another one. To undo it: remove
`/etc/modprobe.d/gpucap-overdrive.conf`, rebuild the initramfs, reboot. It needs a driver that supports OverDrive on your
GPU (verified with AMD's amdgpu-dkms 6.16.x on a Navi 48; the 6.8 in-kernel driver does not support that card at all).

## Build and install

Requires Go 1.22+ to build (the binary is not committed).

```
cd tools/gpucap
go build -o gpucap .
sudo ./install.sh
```

`install.sh` installs the binary to `/usr/local/bin/gpucap`, installs and enables two systemd units, and
changes no power, voltage or clock setting:

- `gpu-power-cap.service` applies your settings at boot.
- `gpu-power-cap-resume.service` re-applies them after suspend/hibernate.

It writes no config of its own and it starts and restarts nothing, so a fresh install leaves your GPUs
exactly as they were: installing is not applying. The units run at the next boot and after each resume,
and `sudo gpucap apply` applies the config on demand. Ask for something when you want it:

```
sudo gpucap set 300          # a power cap, from then on applied at boot and after resume
sudo gpucap undervolt -30    # needs sudo ./install.sh --enable-overdrive once, see above
```

An existing `/etc/gpucap.conf` is left exactly as it is — not rewritten, and not re-applied by the
installer either; it is what the units apply from the next boot or resume, or what `sudo gpucap apply`
applies now. A line gpucap cannot parse is ignored rather than replaced with a guess.

### Upgrading from an earlier version

Earlier versions wrote a `CAP_W` of their own choosing into `/etc/gpucap.conf` at install time, and fell back
to a compiled-in default whenever that file was unreadable. This version has neither. If you are on an older
build and want to be rid of a cap you did not pick, **install this version first** (`go build -o gpucap .`,
then `sudo ./install.sh`) and only then `sudo rm /etc/gpucap.conf` — or `sudo gpucap set <watts>` to replace
it with a value of your own. The order matters: the older binary applies its built-in default whenever the
config is missing, so deleting the file before replacing the binary brings the same cap back on the next boot.

Hosts that ran an older installer also had `vo 0` and `s 0` written to `pp_od_clk_voltage` at every boot and
resume, which resets an offset set by any other tool. Once this binary is in place that stops: zeros now mean
*not requested*. A cap and an offset are both run-time driver settings, so ones already in force survive until
the next reboot or resume, after which nothing re-applies them.

## Uninstall

```
sudo systemctl disable --now gpu-power-cap.service gpu-power-cap-resume.service
sudo rm /etc/systemd/system/gpu-power-cap*.service /usr/local/bin/gpucap /etc/gpucap.conf /etc/modprobe.d/gpucap-overdrive.conf
sudo update-initramfs -u   # only if you removed the modprobe file
sudo systemctl daemon-reload
```

Removing `/etc/modprobe.d/gpucap-overdrive.conf` is only needed if you ran `install.sh --enable-overdrive`;
rebuild the initramfs afterwards as shown. Settings already in force are not undone by uninstalling — they are
run-time driver state and last until the next reboot, or until you set a new value (e.g. the card's maximum).
Nothing re-applies them once the units are gone.
