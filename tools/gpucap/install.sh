#!/bin/bash
# Run with sudo from this directory. Replaces the old shell-script service.
set -e
cd "$(dirname "$0")"
[ -f /etc/gpucap.conf ] || echo "CAP_W=230" > /etc/gpucap.conf
install -m 755 gpucap /usr/local/bin/gpucap
install -m 644 gpu-power-cap.service gpu-power-cap-resume.service /etc/systemd/system/
rm -f /usr/local/sbin/gpu-power-cap.sh
systemctl daemon-reload
systemctl enable gpu-power-cap-resume.service
systemctl enable --now gpu-power-cap.service
systemctl restart gpu-power-cap.service
gpucap status
