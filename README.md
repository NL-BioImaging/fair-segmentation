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
