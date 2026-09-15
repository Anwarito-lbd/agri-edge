"""YOLOX-s experiment: livestock counting from nadir aerial imagery.

WHY THIS IS THE EASY WIN
------------------------
Every other target in this project is capped by optics. Livestock is not:

    target             whole-frame ceiling    tiling needed?
    3 cm seedling            0.6 m            yes -- still capped at 3.9 m
    30 cm mature weed        6.1 m            yes, for survey altitude
    120 cm sheep            24.6 m            no
    200 cm cow              41.0 m            no

Cattle are detectable at 41 m AGL with plain whole-frame inference, so **this is
the one model that runs usefully on a bare Raspberry Pi with no accelerator.**

Dataset is Public Domain -- no attribution obligation, unlike the CC BY 4.0 weed
sets whose credit must follow the product.

max_labels, AND WHY IT IS NOT A DETAIL
--------------------------------------
These are dense scenes: mean 31 sheep per image, **max 105**, and 24.4% of
training images carry more than 50 objects.

YOLOX's defaults are `TrainTransform(max_labels=50)` for the base dataset and
`max_labels=120` after mosaic. At 50, a quarter of the training images would have
their labels **silently truncated** -- and a truncated label is worse than a
missing image, because it actively teaches the model that a real, visible sheep
is background. Nothing errors; the model just quietly learns to under-count.

Both are raised below. Mosaic combines four images, so the post-mosaic cap has to
clear 4 x 105 in the worst case.

Run:
    python vendor/YOLOX/tools/train.py -f training/exps/aerial_sheep_yolox_s.py \
        -d 1 -b 8 --fp16 -c weights/yolox_s.pth
"""

import os
import sys

# See weed_crop_yolox_s.py: YOLOX's JIT C++ COCOeval extension raises
# RuntimeError past an ImportError-only guard when ninja/cl.exe are absent,
# killing the run at the first evaluation.
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

# Comfortably above the observed maximum of 105 objects in one image.
MAX_LABELS = 150
# Mosaic merges four images before cropping; 4 x 105 = 420 worst case.
MAX_LABELS_MOSAIC = 450


class Exp(MyExp):
    def __init__(self):
        super().__init__()

        self.depth = 0.33
        self.width = 0.50
        self.exp_name = os.path.split(os.path.realpath(__file__))[1].split(".")[0]

        self.num_classes = 1                # sheep
        self.data_dir = "data/aerial-sheep"
        self.train_ann = "instances_train.json"
        self.val_ann = "instances_valid.json"
        self.test_ann = "instances_test.json"

        self.input_size = (640, 640)
        self.test_size = (640, 640)
        self.data_num_workers = 2

        # 130k boxes across 3,609 images -- roughly 55x the training signal of the
        # weed species set, so this converges in far fewer epochs. More epochs
        # here would buy overfitting, not accuracy.
        self.max_epoch = 60
        self.warmup_epochs = 3
        self.no_aug_epochs = 10
        self.eval_interval = 5
        self.print_interval = 50

        # Nadir imagery has no canonical "up", so full rotation is free signal.
        self.degrees = 180.0
        self.mosaic_prob = 1.0
        self.flip_prob = 0.5
        self.hsv_prob = 1.0
        # Mixup blends two images and roughly doubles object density. On scenes
        # that already carry 100 animals that mostly manufactures occlusion the
        # camera never sees, so it is off here (it is on for the sparse weed sets).
        self.enable_mixup = False
        # Sheep are a near-constant size at fixed altitude; wild scale jitter
        # would synthesise sizes the deployed camera cannot produce.
        self.mosaic_scale = (0.7, 1.3)

        self.basic_lr_per_img = 0.01 / 64.0
        self.min_lr_ratio = 0.05
        self.weight_decay = 5e-4
        self.momentum = 0.9

        # Dense scenes: many true objects legitimately sit close together, so a
        # tight NMS would delete real animals standing shoulder to shoulder.
        self.nmsthre = 0.65

        self.save_history_ckpt = True

    def get_dataset(self, cache: bool = False, cache_type: str = "ram"):
        from yolox.data import COCODataset, TrainTransform

        return COCODataset(
            data_dir=self.data_dir,
            json_file=self.train_ann,
            name=os.path.join("train", "images"),
            img_size=self.input_size,
            preproc=TrainTransform(
                max_labels=MAX_LABELS,      # NOT the default 50 -- see module docstring
                flip_prob=self.flip_prob,
                hsv_prob=self.hsv_prob,
            ),
            cache=cache,
            cache_type=cache_type,
        )

    def get_data_loader(self, batch_size, is_distributed, no_aug=False, cache_img: str = None):
        """Copy of the base implementation with the post-mosaic label cap raised.

        The base class hardcodes `max_labels=120` inside `MosaicDetection` with no
        config hook, and 120 truncates these scenes after four images are merged.
        """
        from yolox.data import (
            DataLoader,
            InfiniteSampler,
            MosaicDetection,
            TrainTransform,
            YoloBatchSampler,
            worker_init_reset_seed,
        )
        from yolox.utils import wait_for_the_master

        if self.dataset is None:
            with wait_for_the_master():
                assert cache_img is None, \
                    "cache_img must be None if you didn't create self.dataset before launch"
                self.dataset = self.get_dataset(cache=False, cache_type=cache_img)

        self.dataset = MosaicDetection(
            dataset=self.dataset,
            mosaic=not no_aug,
            img_size=self.input_size,
            preproc=TrainTransform(
                max_labels=MAX_LABELS_MOSAIC,   # NOT the default 120
                flip_prob=self.flip_prob,
                hsv_prob=self.hsv_prob,
            ),
            degrees=self.degrees,
            translate=self.translate,
            mosaic_scale=self.mosaic_scale,
            mixup_scale=self.mixup_scale,
            shear=self.shear,
            enable_mixup=self.enable_mixup,
            mosaic_prob=self.mosaic_prob,
            mixup_prob=self.mixup_prob,
        )

        self.dataset.enable_mosaic = not no_aug
        sampler = InfiniteSampler(len(self.dataset), seed=self.seed if self.seed else 0)
        batch_sampler = YoloBatchSampler(
            sampler=sampler,
            batch_size=batch_size,
            drop_last=False,
            mosaic=not no_aug,
        )
        dataloader_kwargs = {
            "num_workers": self.data_num_workers,
            "pin_memory": True,
            "batch_sampler": batch_sampler,
            "worker_init_fn": worker_init_reset_seed,
        }
        return DataLoader(self.dataset, **dataloader_kwargs)

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
