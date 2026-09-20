"""Tests for the YOLO -> COCO conversion.

Worth more than they look. A coordinate error here does not raise: it produces a
training run whose loss descends convincingly and a final model that detects
nothing. Every expected value below is computed by hand in the test name or
comment, so the test fails if the arithmetic drifts rather than agreeing with
whatever the code currently does.
"""

import json
import sys
from pathlib import Path

import importlib.util

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))

from yolo_to_coco import load_class_names, yolo_box_to_coco  # noqa: E402


class TestLoadClassNames:
    """Class names come from the dataset's own data.yaml, never hardcoded.

    The order matters as much as the contents: label files store integer ids, so
    a names list that has drifted from the data produces a model whose classes
    are permuted -- metrics look plausible, predictions are nonsense.
    """

    def _write(self, tmp_path, text):
        (tmp_path / "data.yaml").write_text(text, encoding="utf-8")
        return tmp_path

    def test_reads_names_in_order(self, tmp_path):
        root = self._write(tmp_path, "names:\n- crop\n- weed\nnc: 2\npath: .\n")
        assert load_class_names(root) == ["crop", "weed"]

    def test_reads_five_classes(self, tmp_path):
        root = self._write(
            tmp_path,
            "names:\n- ragweed\n- waterhemp\n- horseweed\n- redrootpigweed\n- kochia\n"
            "nc: 5\npath: .\n",
        )
        assert load_class_names(root) == [
            "ragweed", "waterhemp", "horseweed", "redrootpigweed", "kochia"
        ]

    def test_stops_at_next_top_level_key(self, tmp_path):
        """`nc:` and `train:` must not be swallowed into the names list."""
        root = self._write(
            tmp_path,
            "names:\n- crop\n- weed\nnc: 2\ntrain: train/images\nval: valid/images\n",
        )
        assert load_class_names(root) == ["crop", "weed"]

    def test_missing_data_yaml_falls_back(self, tmp_path):
        assert load_class_names(tmp_path) == ["crop", "weed"]

    def test_unparseable_names_falls_back(self, tmp_path):
        root = self._write(tmp_path, "nc: 2\npath: .\n")
        assert load_class_names(root) == ["crop", "weed"]

    def test_fallback_is_a_copy_not_the_module_list(self, tmp_path):
        """Mutating the result must not corrupt the module-level default."""
        import yolo_to_coco

        got = load_class_names(tmp_path)
        got.append("mutated")
        assert yolo_to_coco.FALLBACK_CLASS_NAMES == ["crop", "weed"]


class TestYoloBoxToCoco:
    def test_centred_box_hand_computed(self):
        """A box centred in a 100x200 image, half its width and a quarter its height.

        cx=0.5 cy=0.5 w=0.5 h=0.25  on  100x200
          abs_w = 0.5  * 100 = 50
          abs_h = 0.25 * 200 = 50
          x_min = (0.5 - 0.25) * 100 = 25
          y_min = (0.5 - 0.125) * 200 = 75
        """
        assert yolo_box_to_coco(0.5, 0.5, 0.5, 0.25, 100, 200) == (25.0, 75.0, 50.0, 50.0)

    def test_full_frame_box(self):
        """A box covering the whole image maps to the whole image."""
        assert yolo_box_to_coco(0.5, 0.5, 1.0, 1.0, 640, 480) == (0.0, 0.0, 640.0, 480.0)

    def test_top_left_corner_box(self):
        """cx=0.1 cy=0.1 w=0.2 h=0.2 on 500x500 -> origin, 100x100."""
        assert yolo_box_to_coco(0.1, 0.1, 0.2, 0.2, 500, 500) == (0.0, 0.0, 100.0, 100.0)

    def test_non_square_image_does_not_mix_axes(self):
        """Width must scale by image width and height by image height.

        Swapping the two is the classic failure. With a deliberately non-square
        image and a non-square box, a swap gives a different answer.
        """
        x, y, w, h = yolo_box_to_coco(0.5, 0.5, 0.4, 0.2, 1000, 100)
        assert (w, h) == (400.0, 20.0)   # not (40.0, 200.0)
        assert (x, y) == (300.0, 40.0)

    def test_box_is_not_xyxy(self):
        """COCO wants [x, y, width, height], never [x1, y1, x2, y2].

        For this box x2 would be 75, so a width of 75 means someone emitted xyxy.
        """
        x, y, w, h = yolo_box_to_coco(0.5, 0.5, 0.5, 0.5, 100, 100)
        assert (x, y, w, h) == (25.0, 25.0, 50.0, 50.0)
        assert w != 75.0

    @pytest.mark.parametrize(
        "cx,cy,bw,bh",
        [(0.5, 0.5, 0.3, 0.3), (0.25, 0.75, 0.1, 0.4), (0.9, 0.1, 0.15, 0.05)],
    )
    def test_round_trip_back_to_yolo(self, cx, cy, bw, bh):
        """Converting back recovers the original normalised box."""
        W, H = 800, 600
        x, y, w, h = yolo_box_to_coco(cx, cy, bw, bh, W, H)
        assert (w / W, h / H) == pytest.approx((bw, bh))
        assert ((x + w / 2) / W, (y + h / 2) / H) == pytest.approx((cx, cy))

    def test_overhanging_box_is_clamped_into_frame(self):
        """Annotations that run past the edge are clamped, not left negative.

        pycocotools computes areas from negative coordinates without complaining,
        which quietly corrupts AP.
        """
        x, y, w, h = yolo_box_to_coco(0.02, 0.02, 0.2, 0.2, 100, 100)
        assert x >= 0 and y >= 0
        assert x + w <= 100 and y + h <= 100

    def test_box_overhanging_far_edge_is_clamped(self):
        x, y, w, h = yolo_box_to_coco(0.98, 0.98, 0.2, 0.2, 100, 100)
        assert x + w <= 100 and y + h <= 100
        assert w > 0 and h > 0


# Pillow is a laptop-side dep: it writes the synthetic images this class
# converts. Importing it inside the fixture meant collection SUCCEEDED and every
# test then errored at setup -- which is why a --collect-only check missed it
# and CI did not. The guard belongs where it can be seen.
HAVE_PIL = importlib.util.find_spec("PIL") is not None


@pytest.mark.skipif(not HAVE_PIL, reason="Pillow not installed (laptop-only dev dep)")
class TestConvertSplit:
    """End-to-end conversion on a tiny synthetic dataset."""

    @pytest.fixture
    def tiny_dataset(self, tmp_path):
        from PIL import Image

        root = tmp_path / "ds"
        for split in ("train",):
            (root / split / "images").mkdir(parents=True)
            (root / split / "labels").mkdir(parents=True)
            Image.new("RGB", (200, 100), "green").save(root / split / "images" / "a.jpg")
            Image.new("RGB", (200, 100), "green").save(root / split / "images" / "b.jpg")
            # a.jpg: one crop (class 0) and one weed (class 1)
            (root / split / "labels" / "a.txt").write_text(
                "0 0.5 0.5 0.5 0.5\n1 0.25 0.25 0.1 0.1\n", encoding="utf-8"
            )
            # b.jpg: a degenerate zero-width box that must be dropped
            (root / split / "labels" / "b.txt").write_text("1 0.5 0.5 0.0 0.3\n", encoding="utf-8")
        return root

    def test_structure_and_counts(self, tiny_dataset, tmp_path):
        from yolo_to_coco import convert_split

        coco = convert_split(tiny_dataset, "train", tmp_path / "ann")
        assert len(coco["images"]) == 2
        assert len(coco["annotations"]) == 2       # the degenerate box was dropped
        assert [c["name"] for c in coco["categories"]] == ["crop", "weed"]

    def test_category_ids_are_one_indexed(self, tiny_dataset, tmp_path):
        """YOLOX sorts getCatIds() and uses position as the class index."""
        from yolo_to_coco import convert_split

        coco = convert_split(tiny_dataset, "train", tmp_path / "ann")
        assert {c["id"] for c in coco["categories"]} == {1, 2}
        # YOLO class 0 (crop) became category_id 1.
        assert sorted(a["category_id"] for a in coco["annotations"]) == [1, 2]

    def test_area_matches_bbox(self, tiny_dataset, tmp_path):
        from yolo_to_coco import convert_split

        coco = convert_split(tiny_dataset, "train", tmp_path / "ann")
        for a in coco["annotations"]:
            _, _, w, h = a["bbox"]
            assert a["area"] == pytest.approx(w * h, abs=0.01)

    def test_annotation_ids_unique(self, tiny_dataset, tmp_path):
        from yolo_to_coco import convert_split

        coco = convert_split(tiny_dataset, "train", tmp_path / "ann")
        ids = [a["id"] for a in coco["annotations"]]
        assert len(ids) == len(set(ids))

    def test_writes_readable_json(self, tiny_dataset, tmp_path):
        from yolo_to_coco import convert_split

        convert_split(tiny_dataset, "train", tmp_path / "ann")
        loaded = json.loads((tmp_path / "ann" / "instances_train.json").read_text(encoding="utf-8"))
        assert loaded["images"][0]["width"] == 200
        assert loaded["images"][0]["height"] == 100

    def test_image_without_label_file_still_listed(self, tiny_dataset, tmp_path):
        """An unlabelled image is a valid negative example, not an error."""
        from yolo_to_coco import convert_split

        (tiny_dataset / "train" / "labels" / "b.txt").unlink()
        coco = convert_split(tiny_dataset, "train", tmp_path / "ann")
        assert len(coco["images"]) == 2
        assert len(coco["annotations"]) == 2

    def test_malformed_label_raises(self, tiny_dataset, tmp_path):
        from yolo_to_coco import convert_split

        (tiny_dataset / "train" / "labels" / "a.txt").write_text("0 0.5 0.5\n", encoding="utf-8")
        with pytest.raises(ValueError, match="expected 5 fields"):
            convert_split(tiny_dataset, "train", tmp_path / "ann")
