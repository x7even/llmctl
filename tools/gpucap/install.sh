#!/bin/bash
# Run with sudo from this directory. Replaces the old shell-script service.
# This installer never creates /etc/gpucap.conf and never picks a cap of its own: an existing
# config is left untouched and only its own CAP_W is re-applied. With no config nothing about
# power or clocks is changed - set a cap when you want one with `sudo gpucap set <watts>`.
set -e
cd "$(dirname "$0")"
install -m 755 gpucap /usr/local/bin/gpucap
install -m 644 gpu-power-cap.service gpu-power-cap-resume.service /etc/systemd/system/
rm -f /usr/local/sbin/gpu-power-cap.sh
systemctl daemon-reload
systemctl enable gpu-power-cap-resume.service
systemctl enable gpu-power-cap.service
# first parseable CAP_W, matching what `gpucap apply` would read (empty if none)
cap=""
if [ -f /etc/gpucap.conf ]; then
	cap=$(sed -n 's/^[[:space:]]*CAP_W[[:space:]]*=[[:space:]]*+\{0,1\}0*\([1-9][0-9]\{0,17\}\)[[:space:]]*$/\1/p' /etc/gpucap.conf | head -n1)
fi
if [ ! -f /etc/gpucap.conf ]; then
	echo "note: no /etc/gpucap.conf, so no cap is configured and no power setting was changed."
	echo "to set one: sudo gpucap set <watts>"
elif [ -n "$cap" ]; then
	echo "/etc/gpucap.conf has CAP_W=$cap: re-applying that existing value, config left untouched."
	systemctl restart gpu-power-cap.service ||
		echo "warning: applying CAP_W=$cap failed, see journalctl -u gpu-power-cap.service"
else
	echo "warning: /etc/gpucap.conf has no parseable CAP_W: left untouched, nothing applied."
	echo "to set a cap: sudo gpucap set <watts>"
fi
/usr/local/bin/gpucap status
