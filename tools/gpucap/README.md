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
