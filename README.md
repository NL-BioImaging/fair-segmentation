# fair-segmentation
FAIR organelle segmentation pipeline

Based on [empanada-napari](https://github.com/volume-em/empanada-napari) napari plugin, export with FAIR RO-Crate packaging

## Installation

Requires Python 3.12 or later. All dependencies are defined in `pyproject.toml`; the `napari` extra adds napari,
empanada-napari and the [napari-meta-tiff](https://pypi.org/project/napari-meta-tiff/) reader.

empanada-napari is currently installed from the
[ccp-volume-em fork](https://github.com/ccp-volume-em/empanada-napari), which includes the open pull request
[volume-em/empanada-napari#56](https://github.com/volume-em/empanada-napari/pull/56), rather than a release,
see [empanada-napari notes](notes/empanada-napari.md).

### Conda

```
conda env create -f environment.yml
conda activate fair-segmentation-env
```

This installs the package in editable mode with the `napari` and `dev` extras. Conda only provides Python;
everything else is installed with pip. On Windows, conda's matplotlib pulls in an ICU library that breaks the
PyQt6 wheels napari uses, so avoid installing napari-related packages with conda into this environment.

### pip

```
pip install -e ".[napari]"
```

### pixi

```
pixi run -e napari python run_fair.py
```

### Docker

```
docker build --build-arg IMAGE_TAG=<tag> -t ghcr.io/nl-bioimaging/empanada-napari-xpra:<tag> .
docker run -p 9876:9876 ghcr.io/nl-bioimaging/empanada-napari-xpra:<tag>
```

The tag given as `IMAGE_TAG` is recorded as the container of every packaged run.

Then open napari in the browser at http://localhost:9876.

## Usage

```
python run_fair.py
```

Segment the image with the empanada-napari inference widget, then choose *Plugins > Package output*. The output is
written to the folder set as `save_dir` on the *Measure Labels* widget, or to `output/` otherwise.

### Output

The output folder is an RO-Crate describing the run, written with
[fair-metadata-integration](https://github.com/NL-BioImaging/fair-metadata-integration) (FMI):

```
output/
├── <image>.ome.zarr/              the image and its segmentation (OME-Zarr 0.5)
│   ├── acquisition-metadata.yaml  the acquisition metadata, on the imaging metadata model
│   ├── ro-crate-metadata.json     the store's own RO-Crate
│   └── labels/<label name>/       a label image per segmentation, with the class of every label value
├── config.yaml                    the run as a Bilayers workflow
├── parameters.yaml                the values the run gave each widget
├── ro-crate-metadata.json         the run's Workflow Run Crate
└── ro-crate-preview.html          a human-readable view of the crate
```

- **The store's crate** (`create_zarr_ro_crate`) describes the store: its Zarr format, the OME-NGFF version it
  conforms to, and its acquisition metadata, converted by
  [imaging-metadata-converter](https://github.com/NL-BioImaging/imaging-metadata-converter), which conforms to
  that converter's LinkML imaging model. It also states where the store came from: it is based on the input
  image, which was acquired on the instrument named in the metadata and segmented by empanada-napari (with its
  version), and it gives the number of objects of each class segmented (e.g. `mito objects`).
- **`config.yaml`** is generated from the widgets with FMI's Bilayers helpers (`bilayers_config`). Every widget is
  a section, named after it (e.g. `3D_Inference_(empanada-napari)`): the inference widget's values are parameters,
  with the value the run used as the default, and the other widgets' values (e.g. the output folder of Measure
  Labels) are display-only entries. The citation, container image and command are fair-segmentation's own; the
  container tag is the one the Docker image was built with.
- **`parameters.yaml`** (`write_parameters`) holds the values of every widget, under the same sections, so every
  value is at its entry of `config.yaml`.
- **The run's crate** (`create_ro_crate`) names `config.yaml` as the workflow, part of fair-segmentation (with its
  version), the input image (referenced where it is, not copied) as its input, the label images in the store as its
  outputs, and `parameters.yaml` as the run's parameter values.

When an output `.ome.zarr` is opened in napari afterwards (with
[napari-ome-zarr](https://github.com/ome/napari-ome-zarr)), the label layers are added hidden, as napari-ome-zarr
does for all label images; switch them on with the eye icon in the layer list.

## Use of AI

Generative AI coding assistants were used in developing this software, including tests and documentation.
All changes are directed and approved by a maintainer, and checked by automated tests where applicable.

## License

[BSD-3-Clause]


[BSD-3-Clause]: https://opensource.org/license/bsd-3-clause
