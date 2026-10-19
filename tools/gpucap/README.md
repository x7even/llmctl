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

`<watts>` can be written `200` or `200w`. A value outside a card's allowed range is rejected for that card
(the range is shown by `gpucap status`).

Example:

```
$ gpucap status
configured: 200W (/etc/gpucap.conf)
card0 cap=200W (range 100-300W) draw=20W
...
$ sudo gpucap set 250
```

There is no built-in default cap. With none configured, `status` says so and still only reads the cards, and
`apply` changes nothing — no power limit, no clocks — says so, points at `sudo gpucap set <watts>`, and exits 0
(a non-zero exit would mark the oneshot units failed on every boot).

It works through the amdgpu hwmon files (`/sys/class/drm/card*/device/hwmon/*/power1_cap`), so it only sees
AMD cards with a power-cap sysfs entry.

## Build and install

Requires Go 1.22+ to build (the binary is not committed).

```
cd tools/gpucap
go build -o gpucap .
sudo ./install.sh
```

`install.sh` installs the binary to `/usr/local/bin/gpucap` and enables two systemd units:

- `gpu-power-cap.service` re-applies a configured cap at boot, and does nothing if none is set.
- `gpu-power-cap-resume.service` re-applies it after suspend/hibernate.

It never creates `/etc/gpucap.conf` and never picks a cap for you. An existing config is left untouched: if it
has a valid `CAP_W` the installer starts the unit so that value is re-applied, and says which value it is;
with an unusable `CAP_W` or no config at all it warns and changes no power setting. So on a machine with
no usable config, installing caps nothing — run `sudo gpucap set <watts>` once and the units keep that value
across reboot and resume.

If you installed an earlier version of this tool, it wrote a `CAP_W` of its own choosing into
`/etc/gpucap.conf`. That file now counts as yours, so that value is what gets re-applied. To be rid of a cap
you did not pick, install this version first (`go build -o gpucap .`, then `sudo ./install.sh`) and only then
`sudo rm /etc/gpucap.conf` — or `sudo gpucap set <watts>` to replace it with a value of your own. The order
matters: the older binary falls back to its built-in default whenever the config is unreadable, so deleting
the file before replacing the binary brings the same cap back on the next boot. A cap is a run-time driver
setting, so one already in force survives until the next reboot or resume, after which nothing re-applies it.

## Uninstall

```
sudo systemctl disable --now gpu-power-cap.service gpu-power-cap-resume.service
sudo rm -f /etc/systemd/system/gpu-power-cap*.service /usr/local/bin/gpucap /etc/gpucap.conf
sudo systemctl daemon-reload
```

The cap itself is not undone until the next reboot (or until you set a new value, e.g. the card's maximum).
