"""Tests for model provenance sidecars.

These exist because the sidecars were, for a while, all wrong in the same way.
`build_meta` hardcoded a single `trained_on` entry, so every exported model --
including a stock COCO detector and a model trained on an entirely different
dataset -- claimed to come from `weed-crop-aerial`.

That is not cosmetic. Two of the three datasets are CC BY 4.0, whose attribution
is a **licence obligation that must follow the product**. Crediting the wrong
source is a compliance failure, and it also destroys the one record that tells a
future reader what a detection was actually produced by.

The rule these tests pin down: provenance is derived from the experiment's
dataset, and an unknown dataset is a hard error rather than a default.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

from export_onnx import DATASET_PROVENANCE, build_meta  # noqa: E402


class TestBuildMeta:
    def test_each_dataset_gets_its_own_attribution(self):
        """The bug was that they all got the same one."""
        credits = {
            name: build_meta("m", ["a"], Path("c"), (640, 640), name)["trained_on"][0]
            for name in DATASET_PROVENANCE
        }
        assert len(set(credits.values())) == len(credits), credits

    def test_imageweeds_credits_the_paper_not_roboflow(self):
        meta = build_meta("m", ["a"], Path("c"), (640, 640), "imageweeds")
        credit = meta["trained_on"][0]
        assert "Rai" in credit and "Data in Brief" in credit
        assert "Roboflow 100" not in credit

    def test_unknown_dataset_raises_rather_than_defaulting(self):
        """A confidently wrong attribution is worse than a missing one."""
        with pytest.raises(SystemExit, match="No provenance entry"):
            build_meta("m", ["a"], Path("c"), (640, 640), "a-dataset-nobody-registered")

    def test_validated_locally_is_always_false_on_export(self):
        """Flipping the safety gate is a deliberate act, never a build step."""
        for name in DATASET_PROVENANCE:
            meta = build_meta("m", ["a"], Path("c"), (640, 640), name)
            assert meta["validated_locally"] is False
            assert "Decision support only." in meta["validation_notes"]

    def test_cc_by_datasets_name_a_creditee(self):
        """CC BY is only satisfied if someone is actually named."""
        for name, prov in DATASET_PROVENANCE.items():
            credit = prov["trained_on"][0]
            if "CC BY" in credit:
                assert "credit" in credit.lower(), f"{name} says CC BY but credits nobody"


class TestShippedSidecars:
    """The .meta.json files committed to the repo, checked as data."""

    SIDECARS = sorted((ROOT / "models").glob("*.meta.json"))

    def test_there_are_sidecars_to_check(self):
        assert self.SIDECARS, "no model sidecars found"

    @pytest.mark.parametrize("path", SIDECARS, ids=lambda p: p.name)
    def test_sidecar_is_not_validated_locally(self, path):
        assert json.loads(path.read_text(encoding="utf-8"))["validated_locally"] is False

    @pytest.mark.parametrize("path", SIDECARS, ids=lambda p: p.name)
    def test_sidecar_names_a_real_source(self, path):
        meta = json.loads(path.read_text(encoding="utf-8"))
        assert meta["trained_on"], f"{path.name} names no training data"
        assert all(t.strip() for t in meta["trained_on"])

    def test_the_coco_model_does_not_claim_agricultural_data(self):
        """It detects none of this project's targets; saying otherwise invites deployment."""
        p = ROOT / "models" / "yolox_s_coco.onnx.meta.json"
        if not p.exists():
            pytest.skip("COCO smoke-test model not present")
        meta = json.loads(p.read_text(encoding="utf-8"))
        assert "COCO" in meta["trained_on"][0]
        assert "weed-crop-aerial" not in meta["trained_on"][0]

    def test_class_names_match_the_model_name(self):
        """A permuted or borrowed class list produces plausible metrics and nonsense labels."""
        expected = {
            "imageweeds_yolox_s": ["ragweed", "waterhemp", "horseweed",
                                   "redrootpigweed", "kochia"],
            "weed_crop_yolox_s": ["crop", "weed"],
        }
        for stem, names in expected.items():
            p = ROOT / "models" / f"{stem}.onnx.meta.json"
            if not p.exists():
                continue
            assert json.loads(p.read_text(encoding="utf-8"))["class_names"] == names
