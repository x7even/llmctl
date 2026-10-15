#!/bin/bash
# Run with sudo from this directory. Replaces the old shell-script service.
set -e
cd "$(dirname "$0")"
# CAP_W is the power cap in watts applied at boot and after resume. 230 is just the value for the
# machine this was written for: change it here for a new install, or later with `sudo gpucap set <watts>`
# (or by editing CAP_W in /etc/gpucap.conf). An existing /etc/gpucap.conf is never overwritten.
[ -f /etc/gpucap.conf ] || printf 'CAP_W=230\nUV_MV=0\nSCLK_MHZ=0\nMCLK_MHZ=0\nUV_LIMIT_MV=100\nSCLK_LIMIT_MHZ=150\nMCLK_LIMIT_MHZ=1350\n' > /etc/gpucap.conf
install -m 755 gpucap /usr/local/bin/gpucap
install -m 644 gpu-power-cap.service gpu-power-cap-resume.service /etc/systemd/system/
rm -f /usr/local/sbin/gpu-power-cap.sh
systemctl daemon-reload
systemctl enable gpu-power-cap-resume.service
systemctl enable --now gpu-power-cap.service
systemctl restart gpu-power-cap.service
gpucap status

# Voltage offset (gpucap undervolt) needs amdgpu's OverDrive feature bit (0x4000), which the default
# ppfeaturemask leaves off. Add it to whatever mask is running now, via modprobe.d (amdgpu loads from
# the initramfs, so that is rebuilt too). A reboot is needed once; changing the offset never needs one.
PARAM=/sys/module/amdgpu/parameters/ppfeaturemask
if [ -r "$PARAM" ]; then
  cur=$(( $(cat "$PARAM") ))
  if (( cur & 0x4000 )); then
    echo "OverDrive already enabled (ppfeaturemask=$(printf '0x%x' "$cur")): voltage offset is ready, no reboot needed."
  else
    new=$(printf '0x%x' $(( cur | 0x4000 )))
    echo "options amdgpu ppfeaturemask=$new" > /etc/modprobe.d/gpucap-overdrive.conf
    if command -v update-initramfs >/dev/null; then update-initramfs -u
    elif command -v dracut >/dev/null; then dracut -f
    else echo "WARNING: rebuild your initramfs manually so the amdgpu option applies at boot"; fi
    echo
    echo "*** REBOOT REQUIRED once to enable voltage offset (ppfeaturemask $(printf '0x%x' "$cur") -> $new). ***"
    echo "*** After the reboot, voltage and clock tuning is enabled: sudo gpucap undervolt -XX | sclk +XX | mclk XXXX ***"
    echo "*** Run gpucap --help first: tuning can damage hardware, start small and stress-test.                  ***"
    echo "*** Changing the offset later never needs another reboot. ***"
  fi
fi
