# gpucap

A small Linux command-line tool to view and set the power cap on every AMD GPU, and keep it across reboots and suspend/resume.

> **This is just a standalone tool that happens to live in this repo.** It is in no way required to run llmctl / llmstack
> or any model on it. The stack works the same without it, and nothing in the stack depends on or references it.
> It exists only because one machine had an external power limit.

## Usage

```
gpucap status          show configured cap, then cap / allowed range / current draw per card
gpucap set <watts>     write /etc/gpucap.conf and apply now (needs root)
gpucap apply [watts]   apply the configured (or given) cap; this is what the systemd units run
```

`<watts>` can be written `230` or `230w`. A value outside a card's allowed range is rejected for that card
(the range is shown by `gpucap status`).

Example:

```
$ gpucap status
configured: 230W (/etc/gpucap.conf)
card0 cap=230W (range 147-300W) draw=18W
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

**Prerequisite:** the file only exists when amdgpu's OverDrive bit is enabled, which the default
`amdgpu.ppfeaturemask=0xfff7bfff` does not do. Add `amdgpu.ppfeaturemask=0xfff7ffff` (or `0xffffffff`) to the kernel
command line and reboot. Older kernels may not expose the offset for newer GPUs (Navi 48 support landed around 6.13+).
Start with a small offset (-30 to -50 mV) and stress-test each card: a too-aggressive undervolt shows up as hangs or
crashes under load, not as an error.

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
sudo rm /etc/systemd/system/gpu-power-cap*.service /usr/local/bin/gpucap /etc/gpucap.conf
sudo systemctl daemon-reload
```

The cap itself is not undone until the next reboot (or until you set a new value, e.g. the card's maximum).
