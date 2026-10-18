#!/usr/bin/env python3
"""
Unit tests for scripts/pcie-link-check (PCIe link-speed downtrain detector):
speed string parsing, GPU discovery by vendor, chain ordering from the sysfs ancestry,
grouping a chain into physical links, and the verdict logic - a downtrained link is reported
with exit 1, an idle GPU is reported as inconclusive with exit 2 rather than as a false
downtrain, and a fully healthy rig exits 0.

Two of those are the point of the test:

* Reading link speed at idle gives 2.5 GT/s on a perfectly healthy card, so the tool must
  refuse to call that a fault; getting this wrong would tell an operator to reseat working
  hardware.
* Both ends of a PCIe link report that link, so one fault must be counted once. A card with
  its own PCIe switch has four devices in its chain but only two links; counting per device
  reports the fault twice and invents a second failing link inside the card.

No GPU is needed: the sysfs tree is a temp directory of real files and symlinks, and the
sampling step is replaced with a supplied peak table. Bus numbers below are arbitrary.

Run:  python3 tests/test_pcie_link_check.py        (also pytest-compatible)
"""
import importlib.machinery
import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "pcie-link-check"

_loader = importlib.machinery.SourceFileLoader("pcie_link_check", str(SCRIPT))
_spec = importlib.util.spec_from_loader("pcie_link_check", _loader)
plc = importlib.util.module_from_spec(_spec)
_loader.exec_module(plc)

# Two GPUs, each on its own root complex and each carrying its own PCIe switch:
# root port -> switch upstream port -> switch downstream port -> GPU. Four devices, two links.
GPU_A = "0000:13:00.0"
GPU_B = "0000:53:00.0"
CHAINS = {
    GPU_A: ["0000:10:01.1", "0000:11:00.0", "0000:12:00.0", GPU_A],
    GPU_B: ["0000:50:01.1", "0000:51:00.0", "0000:52:00.0", GPU_B],
}


def _build(root, rated="32.0 GT/s PCIe", width="16"):
    """A fake /sys with PCI devices, a drm card per GPU, and the ancestry encoded as symlinks."""
    root = Path(root)
    devices = root / "bus" / "pci" / "devices"
    devices.mkdir(parents=True)
    drm = root / "class" / "drm"
    drm.mkdir(parents=True)

    for i, (endpoint, chain) in enumerate(sorted(CHAINS.items())):
        # Real nested directories so os.path.realpath recovers the chain order.
        tree = root / "devices" / ("pci%s" % chain[0][:7])
        for dev in chain:
            tree = tree / dev
            tree.mkdir(parents=True, exist_ok=True)
            (tree / "current_link_speed").write_text("2.5 GT/s PCIe\n")
            (tree / "max_link_speed").write_text(rated + "\n")
            (tree / "max_link_width").write_text(width + "\n")
            (tree / "current_link_width").write_text(width + "\n")
            (tree / "vendor").write_text("0x1002\n")
            (devices / dev).symlink_to(tree)
        card = drm / ("card%d" % i)
        card.mkdir()
        (card / "device").symlink_to(tree)

    # A non-AMD display device must be ignored.
    other = root / "devices" / "pci0000:90" / "0000:90:00.0"
    other.mkdir(parents=True)
    (other / "vendor").write_text("0x10de\n")
    (other / "current_link_speed").write_text("2.5 GT/s PCIe\n")
    (devices / "0000:90:00.0").symlink_to(other)
    (drm / "card9").mkdir()
    (drm / "card9" / "device").symlink_to(other)
    return str(devices), str(drm)


class Harness(unittest.TestCase):
    def run_tool(self, peak, rated="32.0 GT/s PCIe", width="16"):
        """Run main() against a fake sysfs with `peak` substituted for live sampling."""
        with tempfile.TemporaryDirectory() as tmp:
            sys_dev, drm_root = _build(tmp, rated, width)
            old = (plc.SYS_DEV, plc.DRM_ROOT, plc.sample, sys.argv)
            plc.SYS_DEV, plc.DRM_ROOT = sys_dev, drm_root
            plc.sample = lambda chains, seconds, interval: peak
            sys.argv = ["pcie-link-check", "--seconds", "0"]
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    code = plc.main()
            finally:
                plc.SYS_DEV, plc.DRM_ROOT, plc.sample, sys.argv = old
            return code, buf.getvalue()

    @staticmethod
    def peaks(speeds):
        """{bdf: speed} -> the peak table main() expects, applying each speed to its whole chain."""
        out = {}
        for endpoint, chain in CHAINS.items():
            for dev in chain:
                out[dev] = (speeds[endpoint], 16)
        return out


class TestParsing(unittest.TestCase):
    def test_speed_gts(self):
        self.assertEqual(plc.speed_gts("32.0 GT/s PCIe"), 32.0)
        self.assertEqual(plc.speed_gts("16 GT/s"), 16.0)
        self.assertEqual(plc.speed_gts("2.5 GT/s PCIe"), 2.5)

    def test_speed_gts_unparseable(self):
        for bad in (None, "", "Unknown", "garbage"):
            self.assertIsNone(plc.speed_gts(bad))


class TestLinkGrouping(unittest.TestCase):
    def test_chain_groups_into_two_links(self):
        """Four devices, two links: the fault must not be counted once per device."""
        self.assertEqual(
            plc.links_in(CHAINS[GPU_A]),
            [("0000:10:01.1", "0000:11:00.0"), ("0000:12:00.0", GPU_A)],
        )

    def test_odd_chain_leaves_the_tail_alone(self):
        """An unexpected topology must not silently merge a device into the wrong link."""
        self.assertEqual(plc.links_in(["a", "b", "c"]), [("a", "b"), ("c",)])


class TestDiscovery(Harness):
    def test_finds_only_amd_gpus_and_orders_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            sys_dev, drm_root = _build(tmp)
            plc.SYS_DEV, plc.DRM_ROOT = sys_dev, drm_root
            try:
                found = plc.gpu_endpoints()
                bdfs = [b for b, _ in found]
                self.assertEqual(sorted(bdfs), sorted(CHAINS))
                self.assertNotIn("0000:90:00.0", bdfs)  # the non-AMD device
                for bdf in bdfs:
                    # Root port first, endpoint last - the link labels depend on this order.
                    self.assertEqual(plc.chain_for(bdf), CHAINS[bdf])
            finally:
                plc.SYS_DEV, plc.DRM_ROOT = "/sys/bus/pci/devices", "/sys/class/drm"


class TestVerdicts(Harness):
    def test_all_healthy_under_load_exits_zero(self):
        code, out = self.run_tool(self.peaks({GPU_A: 32.0, GPU_B: 32.0}))
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertNotIn("DOWNTRAINED", out)

    def test_one_gen4_link_is_reported_with_exit_one(self):
        code, out = self.run_tool(self.peaks({GPU_A: 32.0, GPU_B: 16.0}))
        self.assertEqual(code, 1)
        self.assertIn("DOWNTRAINED", out)
        self.assertIn(GPU_B, out)
        # The healthy chain must not be implicated.
        self.assertNotIn("%s: link" % GPU_A, out)

    def test_gen4_slot_link_counts_as_exactly_one_link(self):
        """One bad slot link is one fault. Both its ends report it; reporting per device would
        say two links failed and point at a healthy on-card link as well."""
        peak = self.peaks({GPU_A: 32.0, GPU_B: 32.0})
        for dev in CHAINS[GPU_B][:2]:   # the two ends of the slot link
            peak[dev] = (16.0, 16)
        code, out = self.run_tool(peak)
        self.assertEqual(code, 1)
        self.assertIn("DOWNTRAINED: 1 link(s)", out)
        self.assertEqual(out.count("DOWNTRAINED"), 2)  # the link's row, and the summary header
        self.assertIn("slot/riser", out)
        # The card's internal link ran at full speed and must be reported healthy.
        self.assertNotIn("%s: link 0000:52:00.0" % GPU_B, out)

    def test_idle_gpu_is_inconclusive_not_downtrained(self):
        """An untouched card reads 2.5 GT/s; calling that a fault would be a false alarm."""
        code, out = self.run_tool(self.peaks({GPU_A: 2.5, GPU_B: 2.5}))
        self.assertEqual(code, 2)
        self.assertIn("INCONCLUSIVE", out)
        self.assertNotIn("DOWNTRAINED", out)

    def test_idle_gpu_alongside_a_real_fault_still_reports_the_fault(self):
        code, out = self.run_tool(self.peaks({GPU_A: 2.5, GPU_B: 16.0}))
        self.assertEqual(code, 1)
        self.assertIn("INCONCLUSIVE", out)
        self.assertIn("DOWNTRAINED", out)
        self.assertIn("%s: link" % GPU_B, out)
        self.assertNotIn("%s: link" % GPU_A, out)

    def test_narrowed_width_is_a_downtrain(self):
        peak = self.peaks({GPU_A: 32.0, GPU_B: 32.0})
        for dev in CHAINS[GPU_B]:
            peak[dev] = (32.0, 8)  # full speed, half the lanes
        code, out = self.run_tool(peak)
        self.assertEqual(code, 1)
        self.assertIn(GPU_B, out)

    def test_slot_link_is_labelled_distinctly_from_the_on_card_link(self):
        """Which link failed decides whether the operator touches the slot or the card."""
        code, out = self.run_tool(self.peaks({GPU_A: 32.0, GPU_B: 16.0}))
        self.assertIn("slot/riser", out)
        self.assertIn("on-card", out)

    def test_gen4_rated_host_passes_at_gen4(self):
        """Rated speed comes from each link's own ends, so a Gen4 host is healthy at 16 GT/s."""
        code, out = self.run_tool(
            self.peaks({GPU_A: 16.0, GPU_B: 16.0}),
            rated="16.0 GT/s PCIe",
        )
        self.assertEqual(code, 0)
        self.assertIn("OK", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
