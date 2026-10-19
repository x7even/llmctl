#!/bin/bash
# Run with sudo from this directory. Replaces the old shell-script service.
#
# This installs the tool and its units and changes no power, voltage or clock setting. gpucap has
# no built-in defaults: with no /etc/gpucap.conf it applies nothing, so a fresh install leaves your
# GPUs exactly as they are. Ask for something first:
#
#   sudo gpucap set <watts>        a power cap, applied at boot and after resume
#   sudo gpucap undervolt -<mV>    a GFX voltage offset (needs --enable-overdrive below, once)
#
# An existing /etc/gpucap.conf is always preserved, never rewritten, and is what the units apply.
#
#   sudo ./install.sh --enable-overdrive   also set amdgpu's OverDrive bit (needs one reboot)
set -e
# resolve this script before the cd, so --help works when invoked by a relative path
self=$(readlink -f "$0")
cd "$(dirname "$self")"

enable_od=0
for a in "$@"; do
  case "$a" in
    --enable-overdrive) enable_od=1 ;;
    -h|--help) sed -n '2,13p' "$self"; exit 0 ;;
    *) echo "unknown option: $a (try --help)" >&2; exit 2 ;;
  esac
done

install -m 755 gpucap /usr/local/bin/gpucap
install -m 644 gpu-power-cap.service gpu-power-cap-resume.service /etc/systemd/system/
rm -f /usr/local/sbin/gpu-power-cap.sh
systemctl daemon-reload
# enabled, not started: with nothing configured there is nothing to apply, and an install must not
# change a setting on its own. The units run at the next boot and after each resume.
systemctl enable gpu-power-cap-resume.service
systemctl enable gpu-power-cap.service

if [ -e /etc/gpucap.conf ]; then
  # a config already exists, so it is the operator's: re-apply whatever it asks for and nothing
  # else. The binary decides -- it ignores anything it cannot parse and applies no defaults, so a
  # malformed or empty file results in no change rather than a guess made here.
  echo "found existing /etc/gpucap.conf: preserving it and applying what it asks for"
  systemctl restart gpu-power-cap.service
else
  echo "no /etc/gpucap.conf: nothing applied, your power limit, voltage and clocks are untouched"
  echo "to set a cap:   sudo gpucap set <watts>      (see sudo gpucap --help)"
fi
# absolute path: sudo's secure_path may not include /usr/local/bin. `configured: cap none` here
# means nothing will be applied at boot -- that is the expected state after a plain install.
/usr/local/bin/gpucap status

if [ "$enable_od" = 1 ]; then
  # Voltage and clock tuning needs amdgpu's OverDrive feature bit (0x4000), which the default
  # ppfeaturemask leaves off. Add it to whatever mask is running now, via modprobe.d (amdgpu loads
  # from the initramfs, so that is rebuilt too). A reboot is needed once; changing an offset later
  # never needs one. Nothing is tuned by enabling the bit -- it only makes tuning possible.
  PARAM=/sys/module/amdgpu/parameters/ppfeaturemask
  if [ ! -r "$PARAM" ]; then
    echo "cannot read $PARAM: is the amdgpu driver loaded?" >&2
    exit 1
  fi
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
    echo "*** After the reboot: sudo gpucap undervolt -XX | sclk +XX | mclk XXXX -- nothing is tuned until you do. ***"
    echo "*** Run gpucap --help first: tuning can damage hardware, start small and stress-test.                   ***"
    echo "*** To undo: sudo rm /etc/modprobe.d/gpucap-overdrive.conf, rebuild the initramfs, reboot. ***"
  fi
fi
