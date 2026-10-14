# gpucap

A small Linux command-line tool to view and set the power cap on every AMD GPU, and keep it across reboots and suspend/resume.

> **This is just a standalone tool that happens to live in this repo.** It is in no way required to run llmctl / llmstack
> or any model on it. The stack works the same without it, and nothing in the stack depends on or references it.
> It exists only because one machine had an external power limit.

## Usage

```
gpucap                 summary table per card: cap, draw, voltage offset, live voltage, clocks, temperatures
gpucap --settings      just the current settings (cap, voltage offset) and their allowed ranges
gpucap --all           everything readable per card: adds fan, busy %, VRAM, PCIe link and the ranges
                       (`gpucap status` is the same as plain `gpucap`)
gpucap set <watts>     write /etc/gpucap.conf and apply now (needs root)
gpucap apply [watts]   apply the configured (or given) cap; this is what the systemd units run
```

`<watts>` can be written `230` or `230w`. A value outside a card's allowed range is rejected for that card
(the range is shown by `gpucap status`).

Example:

```
$ gpucap
configured: 230W, -30mV, undervolt limit -100mV (/etc/gpucap.conf)
   CARD  CAP W  DRAW W  OFFSET mV  VGFX mV  SCLK MHz  MCLK MHz  EDGE C  JUNC C  MEM C
  card0    230     180        -30      950      2900      1258      62      71     66
...
$ sudo gpucap set 250
```

It works through the amdgpu hwmon files (`/sys/class/drm/card*/device/hwmon/*/power1_cap`), so it only sees
AMD cards with a power-cap sysfs entry.

## Undervolting (optional, RDNA3/RDNA4)

```
gpucap undervolt <mV>  write UV_MV to /etc/gpucap.conf and apply a GFX voltage offset now (e.g. -50; 0 clears; needs root)
```

This writes `vo <mV>` then `c` to `/sys/class/drm/card*/device/pp_od_clk_voltage` and reads the value back.
`apply` (boot/resume) re-applies the saved offset after the cap; a failed offset only warns, so the cap still applies.
`gpucap status` shows the current offset and allowed range, or `offset=n/a` when unsupported.

**Allowed range:** gpucap accepts 0 down to `-UV_LIMIT_MV` (default `-100` mV), further bounded by the range the driver
reports. The driver usually allows about -200 mV, but offsets that deep are rarely stable. To go deeper, set
`UV_LIMIT_MV=150` (for example) in `/etc/gpucap.conf`. Typical stable values are -30 to -80 mV and vary per chip: start at
-30, stress-test each card, and step down. A too-aggressive undervolt shows up as hangs or crashes under load, not as an error.

**Prerequisite (handled by `install.sh`):** the offset file only exists when amdgpu's OverDrive bit (`0x4000`) is set in
`amdgpu.ppfeaturemask`, which the default does not do. `install.sh` ORs that bit into the running mask, writes
`/etc/modprobe.d/gpucap-overdrive.conf`, rebuilds the initramfs, and tells you to **reboot once**. After that, changing the
offset is a live write and never needs a reboot. Older kernels may not expose the offset for newer GPUs (Navi 48 landed around 6.13+).

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
