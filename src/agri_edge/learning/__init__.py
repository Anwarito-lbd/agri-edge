"""The loop that turns this farm's imagery into a model validated on it.

    walk / fly -> spool -> select_for_labeling -> Label Studio -> COCO
               -> retrain (training/) -> validate_local -> signed report
               -> the engine trusts the model only with that report

* `selection`    which frames are worth a person's labelling time
* `labelstudio`  export tasks with pre-annotations; import labels as COCO
* `metrics`      AP50 / precision / recall, pure numpy
* `validate`     local validation against stated criteria -> report tied to
                 the model file's sha256
* `png`          a dependency-free PNG writer for spool frames
"""
