#!/usr/bin/env python3
"""
Unit tests for the commented-out profile templates at the bottom of
config/models.yaml.

Why this file exists: the templates are entirely commented out, so every check we
already had passed regardless of what was inside them. `yaml.safe_load` on the real
file never sees them, and a reviewer checking that a diff "only touches comments"
sees nothing to object to. A template can therefore be missing a flag that the root
CLAUDE.md calls mandatory, or contain prose that becomes argv once uncommented, and
nothing notices until someone copies it and loses an afternoon.

That is not hypothetical. The template shipped for a while naming a stale local image
rather than the pinned one, and without --entrypoint="", --cudagraph-capture-sizes,
the two compile-cache mounts, or GPU_MAX_HW_QUEUES=1 -- by the root doc's own account,
a profile that fails with "unrecognized arguments", or takes 18+ minutes to start, or
serves at half speed with nothing in the logs. A later pass added explanatory "#"
lines *inside* the `cmd: |` block scalar, which llama-swap v223+ runs without a shell:
uncommenting that yielded 243 argv tokens including 21 bare "#" instead of 60 clean
ones.

So these tests adopt each template the way a person would -- strip one leading comment
marker per line, parse the result -- and assert it is actually usable.

Run:  python3 tests/test_models_template.py        (also pytest-compatible)
"""
import shlex
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
MODELS = REPO / "config" / "models.yaml"


def uncomment(block):
    """Strip exactly one leading '# ' (or a bare '#') per line, as a user would."""
    out = []
    for ln in block.split("\n"):
        if ln.startswith("# "):
            out.append(ln[2:])
        elif ln == "#":
            out.append("")
        else:
            out.append(ln)
    return "\n".join(out)


def extract(first_line, last_line):
    src = MODELS.read_text()
    i = src.index(first_line)
    j = src.index(last_line, i) + len(last_line)
    return uncomment(src[i:j])


def argv(cmd):
    """Tokenise a cmd block the way a shell-less launcher's splitter would."""
    return shlex.split(cmd.replace("\n", " "))


class TemplateParses(unittest.TestCase):
    """Each template must still be valid YAML once the comment markers come off."""

    def test_vllm_template_parses(self):
        doc = yaml.safe_load(
            extract(
                "# my-new-model:\n",
                "#   cmdStop: podman stop llmstack-vllm-${MODEL_ID}\n",
            )
        )
        self.assertIn("my-new-model", doc)
        prof = doc["my-new-model"]
        for key in ("name", "ttl", "metadata", "checkEndpoint", "cmd", "cmdStop"):
            self.assertIn(key, prof, f"vLLM template lost the {key!r} key")

    def test_gguf_template_parses(self):
        doc = yaml.safe_load(
            extract(
                "# my-gguf-model:\n",
                "#   cmdStop: podman stop llmstack-llama-${MODEL_ID}\n",
            )
        )
        self.assertIn("my-gguf-model", doc)


class CmdBodyIsArgumentsOnly(unittest.TestCase):
    """
    The cmd body is a YAML block scalar executed without a shell, so a '#' line
    inside it is an argument, not a comment. All commentary must sit above `cmd:`.
    """

    def _assert_no_comments(self, cmd, label):
        stray = [t for t in argv(cmd) if t.startswith("#")]
        self.assertEqual(
            stray,
            [],
            f"{label}: {len(stray)} comment token(s) would be passed to podman as "
            f"arguments. Move the commentary above `cmd:`.",
        )

    def test_vllm_cmd_has_no_comment_tokens(self):
        doc = yaml.safe_load(
            extract(
                "# my-new-model:\n",
                "#   cmdStop: podman stop llmstack-vllm-${MODEL_ID}\n",
            )
        )
        self._assert_no_comments(doc["my-new-model"]["cmd"], "vLLM template")

    def test_gguf_cmd_has_no_comment_tokens(self):
        doc = yaml.safe_load(
            extract(
                "# my-gguf-model:\n",
                "#   cmdStop: podman stop llmstack-llama-${MODEL_ID}\n",
            )
        )
        self._assert_no_comments(doc["my-gguf-model"]["cmd"], "GGUF template")


class MandatoryFlags(unittest.TestCase):
    """
    The five items the root CLAUDE.md marks mandatory for every vLLM profile, plus
    the pinned-image and never-use rules. Each assertion names the failure mode,
    because the point of the template is that the next person does not have to know.
    """

    @classmethod
    def setUpClass(cls):
        doc = yaml.safe_load(
            extract(
                "# my-new-model:\n",
                "#   cmdStop: podman stop llmstack-vllm-${MODEL_ID}\n",
            )
        )
        cls.prof = doc["my-new-model"]
        cls.cmd = cls.prof["cmd"]

    def test_item1_entrypoint_nullified_and_vllm_invoked(self):
        self.assertIn(
            '--entrypoint=""',
            self.cmd,
            "item 1: without --entrypoint=\"\" the image's broken ENTRYPOINT runs",
        )
        self.assertIn(
            "vllm serve",
            self.cmd,
            "item 1: vllm must be invoked explicitly once the entrypoint is nullified",
        )

    def test_item2_explicit_cudagraph_capture_sizes(self):
        self.assertIn(
            "--cudagraph-capture-sizes",
            self.cmd,
            "item 2: without this vLLM enumerates ~2000+ shapes and start takes 18+ min",
        )

    def test_item3_both_compile_cache_mounts(self):
        self.assertIn(
            ".vllm-cache:/root/.cache/vllm",
            self.cmd,
            "item 3: without the vllm cache mount torch.compile re-runs every start",
        )
        self.assertIn(
            ".triton-cache:/root/.triton/cache",
            self.cmd,
            "item 3: without the triton cache mount kernels recompile every start",
        )

    def test_item4_usemodelname_matches_served_model_name(self):
        self.assertEqual(
            self.prof.get("useModelName"),
            "my-new-model",
            "item 4: useModelName must equal --served-model-name or every alias 404s",
        )
        self.assertIn(
            "--served-model-name my-new-model",
            self.cmd,
            "item 4: --served-model-name must match useModelName",
        )

    def test_item5_gpu_max_hw_queues(self):
        self.assertIn(
            "-e GPU_MAX_HW_QUEUES=1",
            self.cmd,
            "item 5: without it a gfx1201 container can draw the slow decode band and "
            "serve at ~half speed for its whole life with nothing in the logs",
        )

    def test_uses_the_pinned_image(self):
        self.assertIn(
            "docker.io/vllm/vllm-openai-rocm:v0.26.0",
            self.cmd,
            "the template must name the pinned image, not a local or stale one",
        )

    def test_no_moving_latest_tag(self):
        self.assertNotIn(
            ":latest",
            self.cmd,
            "pinned-tag policy: never reference a moving :latest tag",
        )

    def test_no_enforce_eager(self):
        self.assertNotIn(
            "--enforce-eager",
            self.cmd,
            "--enforce-eager permanently costs 10-20% throughput; use capture sizes",
        )

    def test_max_num_seqs_keeps_the_3d_path_open(self):
        toks = argv(self.cmd)
        self.assertIn("--max-num-seqs", toks)
        seqs = int(toks[toks.index("--max-num-seqs") + 1])
        self.assertLessEqual(
            seqs,
            32,
            "--max-num-seqs above 32 silently closes TRITON_ATTN's 3D split-KV path "
            "(docs/rdna4-long-context.md)",
        )

    def test_awq_and_expert_parallel_not_both_enabled(self):
        self.assertFalse(
            "--quantization awq" in self.cmd and "--enable-expert-parallel" in self.cmd,
            "AWQ + expert-parallel crashes mid-startup with an IndexError",
        )


class CommittedFormKeepsThePlaceholder(unittest.TestCase):
    """
    The template's cache mounts must use the placeholder, like the rest of the file.
    tests/test_configure.py already guards the committed file as a whole; this pins
    the reason for the template specifically, so nobody "helpfully" writes a real
    path into the example.
    """

    def test_template_mounts_use_the_placeholder(self):
        src = MODELS.read_text()
        i = src.index("# my-new-model:\n")
        j = src.index("#   cmdStop: podman stop llmstack-vllm-${MODEL_ID}\n", i)
        block = src[i:j]
        if "__LLMSTACK_DIR__" not in block:
            # A configured working copy has had the placeholder substituted; that is
            # expected and is not what this test is for.
            self.skipTest("working copy is configured, not in committed form")
        self.assertNotIn(
            "/home/",
            block,
            "the template must carry __LLMSTACK_DIR__, never a real home path",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
