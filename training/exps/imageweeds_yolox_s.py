"""YOLOX-s experiment: five prairie weed species from nadir aerial imagery.

Classes: ragweed, waterhemp, horseweed, redroot pigweed, kochia -- the
herbicide-resistant weeds that actually matter on the Canadian Prairies.

WHY THIS DATASET AND NOT THE FIRST ONE
--------------------------------------
`weed-crop-aerial` turned out not to be aerial: close-range ground shots plus
indoor propagation trays, with 98% of its `crop` labels coming from seed trays.
This one was verified by inspecting imagery before training -- genuine nadir
views of a real tilled field, crop rows and tractor tracks visible.

KNOWN CAVEAT, AND IT MATTERS
----------------------------
Only the **transplanted research specimens** are annotated -- weeds placed in
black pots within the plot. Each frame also contains dozens of naturally
occurring weeds that are *not* labelled, so they train as background. Two
consequences to expect and not misdiagnose:

  * Recall is capped by the annotation, not by the model. Detections of real
    unlabelled weeds are scored as false positives, so measured precision
    understates true performance.
  * The model can pick up container cues alongside plant morphology.

Neither is fixable by tuning. Both are fixed by annotating local field imagery,
which is the phase-8 work regardless.

SIZING
------
Source frames are 5472x3648 with boxes averaging ~350 px, about 6.4% of frame
width -- roughly 41 px once letterboxed to the 640 network input. That is
comfortably detectable, so whole-frame training is correct here and tiling is
unnecessary. Tiling exists for seedling-scale targets, a different problem
(`training/gsd_calculator.py`).

Run:
    python vendor/YOLOX/tools/train.py -f training/exps/imageweeds_yolox_s.py \
        -d 1 -b 8 --fp16 -c weights/yolox_s.pth
"""

import os
import sys

# See the long note in weed_crop_yolox_s.py: YOLOX's JIT-compiled C++ COCOeval
# extension raises RuntimeError past an ImportError-only guard when ninja (or a
# C++ compiler) is missing, killing the run at the first evaluation. Setting the
# module to None makes the import raise ImportError, which YOLOX does catch,
# taking its own intended pycocotools fallback.
sys.modules.setdefault("yolox.layers.fast_coco_eval_api", None)

# --------------------------------------------------------------------------
# Make YOLOX's `--resume` work on PyTorch 2.6+.
#
# `trainer.resume_train` calls `torch.load(ckpt)` without `weights_only=False`.
# PyTorch 2.6 flipped that default to True, and these checkpoints contain a
# numpy scalar (`best_ap`), which is not an allowed global under the safe
# unpickler. Resume therefore dies with `_pickle.UnpicklingError` -- and because
# YOLOX wraps main() in loguru's `@logger.catch`, the process still **exits 0**,
# so it looks like a successful no-op run.
#
# Allowlisting the one numpy global here fixes resume without touching vendored
# code. The exp module is imported into the training process before the trainer
# runs, which is why this works from here.
try:
    import numpy as _np
    import torch.serialization as _ts

    # The scalar factory, the dtype base, and every concrete dtype class --
    # allowlisting them one error at a time is a losing game, and the set is
    # small and entirely numpy's own.
    _allow = [_np._core.multiarray.scalar, _np.dtype]
    _allow += [
        getattr(_np.dtypes, _n)
        for _n in dir(_np.dtypes)
        if _n.endswith("DType") and isinstance(getattr(_np.dtypes, _n), type)
    ]
    _ts.add_safe_globals(_allow)
except Exception:  # pragma: no cover - older torch has no add_safe_globals
    pass


from yolox.exp import Exp as MyExp  # noqa: E402


class Exp(MyExp):
    def __init__(self):
        super().__init__()

        self.depth = 0.33
        self.width = 0.50
        self.exp_name = os.path.split(os.path.realpath(__file__))[1].split(".")[0]

        self.num_classes = 5
        self.data_dir = "data/imageweeds"
        self.train_ann = "instances_train.json"
        self.val_ann = "instances_valid.json"
        self.test_ann = "instances_test.json"

        self.input_size = (640, 640)
        self.test_size = (640, 640)
        self.data_num_workers = 2

        # ~385 training images and ~1,670 boxes: smaller than the first dataset,
        # so lean harder on augmentation and run longer. Still fine-tuning from
        # COCO weights -- from scratch at this scale would not converge.
        self.max_epoch = 150
        self.warmup_epochs = 5
        self.no_aug_epochs = 20
        self.eval_interval = 5
        self.print_interval = 20

        # Nadir aerial imagery has no canonical "up": a frame is equally valid at
        # any heading, so full rotation is a free and legitimate multiplier.
        self.degrees = 180.0
        self.mosaic_prob = 1.0
        self.mixup_prob = 1.0
        self.hsv_prob = 1.0
        self.flip_prob = 0.5
        self.enable_mixup = True
        # Weeds are roughly uniform in size at fixed altitude, so wild scale
        # jitter would synthesise sizes the deployed camera never produces.
        self.mosaic_scale = (0.5, 1.5)

        self.basic_lr_per_img = 0.01 / 64.0
        self.min_lr_ratio = 0.05
        self.weight_decay = 5e-4
        self.momentum = 0.9

        self.save_history_ckpt = True

    def get_dataset(self, cache: bool = False, cache_type: str = "ram"):
        from yolox.data import COCODataset, TrainTransform

        return COCODataset(
            data_dir=self.data_dir,
            json_file=self.train_ann,
            name=os.path.join("train", "images"),
            img_size=self.input_size,
            preproc=TrainTransform(
                max_labels=50, flip_prob=self.flip_prob, hsv_prob=self.hsv_prob
            ),
            cache=cache,
            cache_type=cache_type,
        )

    def get_eval_dataset(self, **kwargs):
        from yolox.data import COCODataset, ValTransform

        testdev = kwargs.get("testdev", False)
        legacy = kwargs.get("legacy", False)

        return COCODataset(
            data_dir=self.data_dir,
            json_file=self.test_ann if testdev else self.val_ann,
            name=os.path.join("test" if testdev else "valid", "images"),
            img_size=self.test_size,
            preproc=ValTransform(legacy=legacy),
        )

    def get_evaluator(self, batch_size, is_distributed, testdev=False, legacy=False):
        """Per-class AP is the number that matters with five uneven classes."""
        from yolox.evaluators import COCOEvaluator

        return COCOEvaluator(
            dataloader=self.get_eval_loader(
                batch_size, is_distributed, testdev=testdev, legacy=legacy
            ),
            img_size=self.test_size,
            confthre=self.test_conf,
            nmsthre=self.nmsthre,
            num_classes=self.num_classes,
            testdev=testdev,
            per_class_AP=True,
            per_class_AR=True,
        )
