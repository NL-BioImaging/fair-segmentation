# empanada-napari

fair-segmentation runs segmentation with the [empanada-napari](https://github.com/volume-em/empanada-napari)
plugin. These notes track what the pipeline needs from empanada-napari, and which version is used.

## Version in use

empanada-napari is installed from the `main` branch of the ccp-volume-em fork, as defined in `pyproject.toml`:

```
empanada-napari @ git+https://github.com/ccp-volume-em/empanada-napari.git
```

The fork's `main` is upstream `main` with the open [PR #56](https://github.com/volume-em/empanada-napari/pull/56)
*Fix export assertion and add label measurements* merged in:

- Fixes the export sanity check, which compared the image stack size to itself rather than to the mask
- Adds a *Measure Labels* widget: per-label morphometrics (area, perimeter, eccentricity, axis lengths,
  Feret diameter, circularity, aspect ratio) for the current slice or the whole stack, with optional CSV export
- Removes duplicate dependencies

New commits on upstream `main` or on the PR are not picked up automatically; merge them into the fork's `main`.
Once the PR is merged and released, switch to the released version.

## Fork

[ccp-volume-em/empanada-napari](https://github.com/ccp-volume-em/empanada-napari) is the fork used here, and the
base for changes intended upstream. Branch those changes from upstream `main`, so their pull requests do not
include the PR #56 commits.

## Requirements

| Requirement                                    | Status                                                         |
|------------------------------------------------|----------------------------------------------------------------|
| Support for 16-bit images                      | Open                                                           |
| Integrate Measure labels                       | In PR #56                                                      |
| Export segmentation to OME-Zarr + labels mask  | Implemented in fair-segmentation (`fair_segmentation.ome_zarr_output`) |
| Integration (or hook) to FAIR packaging output | Implemented in fair-segmentation (`run_fair.py`)               |

### Support for 16-bit images

empanada-napari and its models are built around 8-bit images: the models are trained on 8-bit data, and
training requires 8-bit input (`train.py` asserts `img.dtype == np.uint8`). Electron microscopy data is often
acquired as 16-bit, so empanada-napari, including its models, should support the 16-bit input range natively,
without the image first being converted to 8-bit.

Inference already accepts 16-bit input, but only scales it by the data type: `Preprocessor`
(`empanada_napari/utils.py`) divides by `np.iinfo(image.dtype).max`, so by 65535 for 16-bit, and then applies the
model's normalisation (MitoNet_v1 and DropNet_base_v1: mean 0.57571, std 0.12765, as a fraction of the full
range). This only matches the training data when the image spans the full 16-bit range. Data stored at a lower
bit depth in a 16-bit container (for example 12 or 14-bit detectors) ends up too dark relative to the model's
expected intensities. Normalising by the actual intensity range (percentiles, or the detector bit depth from the
acquisition metadata) would address inference; training and fine-tuning would also need to accept 16-bit input.

### Integrate Measure labels

Added in PR #56 as the *Measure Labels* widget. fair-segmentation reads its output folder setting to decide where
to write the FAIR output.

### Export segmentation to OME-Zarr + labels mask

empanada-napari exports segmentations as image files. fair-segmentation writes the input image and its label
layers to a single OME-Zarr store, with the labels as OME-Zarr labelled images. Native support in empanada-napari
would make this available without the fair-segmentation wrapper.

### Integration (or hook) to FAIR packaging output

fair-segmentation currently collects the widget parameters from the napari dock widgets after the segmentation
has run. A hook in empanada-napari, for example a callback or signal when inference or export finishes with its
parameters and output, would allow FAIR packaging to be triggered directly.
