# gpucap

A small Linux command-line tool to view and set the power cap, and (on RDNA3/RDNA4) the voltage offset and clocks, of every AMD GPU, and keep them across reboots and suspend/resume.

> **This is just a standalone tool that happens to live in this repo.** It is in no way required to run llmctl / llmstack
> or any model on it. The stack works the same without it, and nothing in the stack depends on or references it.
> It exists only because one machine had an external power limit.

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
gpucap apply [watts]   apply the configured (or given) cap plus saved voltage/clock settings; this is what the systemd units run
```

`<watts>` can be written `230` or `230w`. A value outside a card's allowed range is rejected for that card
(the range is shown by `gpucap status`).

Example:

```
$ gpucap
configured: cap 230W, voltage -30mV, core +0MHz, memory max stock (/etc/gpucap.conf)
limits:     voltage -100mV, core +150MHz, memory max 1350MHz
   CARD  CAP W  DRAW W  V OFFSET mV  VGFX mV  SCLK OFFSET MHz  SCLK MHz  MCLK MAX MHz  MCLK MHz  EDGE C  JUNC C  MEM C
  card0    230     180          -30      950               +0      2900          1259      1258      62      71     66
...
$ sudo gpucap set 250
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

**Limits:** the driver ranges are wide (about -200 mV, +1000 MHz core, 1500 MHz memory) but settings that far are rarely stable.
gpucap refuses anything past `UV_LIMIT_MV` (default 100), `SCLK_LIMIT_MHZ` (default 150) and `MCLK_LIMIT_MHZ` (default 1350,
chosen for a Radeon AI PRO R9700 with 1259 MHz stock) unless you raise them in `/etc/gpucap.conf`; set limits that suit your cards.
Typical stable undervolts are -30 to -80 mV and vary per chip: start small, change one thing at a time, stress-test each card,
and compare real results. Too aggressive a setting shows up as hangs, crashes or (for memory) corrupt output, not as an error.

**Prerequisite (handled by `install.sh`):** the file only exists when amdgpu's OverDrive bit (`0x4000`) is set in
`amdgpu.ppfeaturemask`, which the default does not do. `install.sh` ORs that bit into the running mask, writes
`/etc/modprobe.d/gpucap-overdrive.conf`, rebuilds the initramfs, and tells you to **reboot once**. After that, changing a
setting is a live write and never needs a reboot. It needs a driver that supports OverDrive on your GPU (verified here with
AMD's amdgpu-dkms 6.16.6 on a Navi 48; the stock 6.8 kernel driver does not support that card at all).

## Build and install

Requires Go 1.22+ to build (the binary is not committed).

```
cd tools/gpucap
go build -o gpucap .
sudo ./install.sh
```

`install.sh` installs the binary to `/usr/local/bin/gpucap`, creates `/etc/gpucap.conf` if it does not exist,
and enables two systemd units:

- `gpu-power-cap.service` applies the cap at boot.
- `gpu-power-cap-resume.service` re-applies it after suspend/hibernate.

Note the built-in default and the value `install.sh` writes into a new `/etc/gpucap.conf` are both `230` W,
which was just the value for the machine this was written for. Set your own with `sudo gpucap set <watts>`
(or edit `CAP_W=` in `/etc/gpucap.conf`) before relying on it.

## Uninstall

```
sudo systemctl disable --now gpu-power-cap.service gpu-power-cap-resume.service
sudo rm /etc/systemd/system/gpu-power-cap*.service /usr/local/bin/gpucap /etc/gpucap.conf /etc/modprobe.d/gpucap-overdrive.conf
sudo update-initramfs -u   # only if you removed the modprobe file
sudo systemctl daemon-reload
```

The cap itself is not undone until the next reboot (or until you set a new value, e.g. the card's maximum).
