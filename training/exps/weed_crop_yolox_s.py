"""YOLOX-s experiment: weed vs crop on aerial imagery.

YOLOX is Apache-2.0, which is why it is here rather than a YOLOv8/v11 (AGPL-3.0)
or YOLOv6 (GPL-3.0). It is also already in the Hailo model zoo as
`yolox_s_leaky`, so there is a documented path from this checkpoint to a `.hef`
running on the AI HAT.

Two dataset facts drive the settings below:

1. **The class balance is 95% weed / 5% crop** (278 crop boxes in training).
   Aggregate mAP will be dominated by the weed class; a model that ignores crop
   entirely still scores well. Judge this run on *per-class* AP.

2. **Every image is already 640x640**, matching `input_size` exactly. No
   letterboxing happens during training, so any aspect-ratio bug will not show up
   until inference on a real camera frame. That is why the letterbox round-trip
   is unit-tested separately rather than trusted because training looked fine.

Run:
    python vendor/YOLOX/tools/train.py \
        -f training/exps/weed_crop_yolox_s.py \
        -d 1 -b 8 --fp16 -c weights/yolox_s.pth
"""

import os
import sys

# --------------------------------------------------------------------------
# Disable YOLOX's optional C++ COCOeval extension before anything imports it.
#
# YOLOX ships a JIT-compiled C++ accelerator for COCO evaluation. Its loader
# (`yolox/layers/jit_ops.py`) raises **RuntimeError** when ninja is absent, but
# `yolox/layers/__init__.py` only guards the import with `except ImportError`.
# The RuntimeError therefore escapes and kills the training run at the first
# evaluation -- after several epochs of work, with a message about ninja that
# does not mention evaluation.
#
# Installing ninja does not fix it on this machine: compiling the extension also
# needs MSVC (`cl.exe`), which is a multi-gigabyte Visual Studio Build Tools
# install. The extension is purely a speed optimisation, and at 235 validation
# images standard pycocotools takes about a second.
#
# Setting the module to None in sys.modules makes `from .fast_coco_eval_api
# import COCOeval_opt` raise ImportError -- which YOLOX *does* catch, taking its
# own intended fallback path ("Use standard COCOeval"). This avoids patching
# vendored code that gets re-cloned.
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

        # --- model: yolox_s depth/width ---
        self.depth = 0.33
        self.width = 0.50
        self.exp_name = os.path.split(os.path.realpath(__file__))[1].split(".")[0]

        # --- data ---
        self.num_classes = 2               # crop, weed
        self.data_dir = "data/weed-crop-aerial"
        self.train_ann = "instances_train.json"
        self.val_ann = "instances_valid.json"
        self.test_ann = "instances_test.json"

        self.input_size = (640, 640)
        self.test_size = (640, 640)

        # Windows + CUDA: worker processes re-import and can deadlock or blow up
        # host RAM. 2 is a safe default here; raise it only if you measure a win.
        self.data_num_workers = 2

        # --- schedule ---
        # 823 training images is small. 100 epochs from COCO-pretrained weights is
        # enough to converge; training from scratch at this size will not work.
        self.max_epoch = 100
        self.warmup_epochs = 5
        self.no_aug_epochs = 15            # last N epochs without mosaic/mixup
        self.eval_interval = 5
        self.print_interval = 20

        # --- augmentation ---
        # Mosaic and mixup are strong regularisers and matter more, not less, on a
        # small dataset. Rotation is kept generous because aerial imagery has no
        # canonical "up" -- a nadir frame is equally valid at any heading, which is
        # not true of the ground-level photography these defaults were tuned on.
        self.degrees = 180.0
        self.mosaic_prob = 1.0
        self.mixup_prob = 1.0
        self.hsv_prob = 1.0
        self.flip_prob = 0.5
        self.enable_mixup = True

        # --- optimiser ---
        # basic_lr_per_img * batch_size = actual LR. At batch 8 this gives 1.25e-4,
        # appropriate for fine-tuning rather than the from-scratch default.
        self.basic_lr_per_img = 0.01 / 64.0
        self.min_lr_ratio = 0.05
        self.weight_decay = 5e-4
        self.momentum = 0.9

        # Keep every evaluated checkpoint. A laptop GPU throttles and Windows
        # installs updates; losing a 2-hour run to a single overwritten file is
        # avoidable.
        self.save_history_ckpt = True

    # YOLOX's defaults assume the COCO layout (train2017/, val2017/). Our images
    # live in train/images, valid/images, test/images, so `name` has to be
    # overridden -- the base class hardcodes it and there is no config hook.

    def get_dataset(self, cache: bool = False, cache_type: str = "ram"):
        from yolox.data import COCODataset, TrainTransform

        return COCODataset(
            data_dir=self.data_dir,
            json_file=self.train_ann,
            name=os.path.join("train", "images"),
            img_size=self.input_size,
            preproc=TrainTransform(
                max_labels=50,
                flip_prob=self.flip_prob,
                hsv_prob=self.hsv_prob,
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
        """Standard evaluator, but reporting per-class AP.

        The aggregate mAP is close to meaningless on this dataset: at 95% weed /
        5% crop, a model that never predicts crop still scores respectably. The
        per-class table is what tells you whether the run is actually working.
        """
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
