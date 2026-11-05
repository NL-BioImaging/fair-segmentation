"""Describe a segmentation run as a Bilayers workflow specification.

The RO-Crate packaging a run names a Bilayers ``config.yaml`` as its workflow.
There is no hand written one for empanada-napari, so it is generated from the
values of the inference widget, with fair-metadata-integration: every value
becomes a parameter whose default is the value the run used, so the config
records how the segmentation was produced as well as what can be set.

Widget values that are layers are the data the run consumed and produced, not
parameters; they are described by the single image input and the segmentation
output instead.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import os

from fair_metadata_integration import bilayers_config as generic_bilayers_config, image_entry

from fair_segmentation import parameters
from fair_segmentation.util import validate_filename


ZARR_FORMAT = 'omezarr'


def bilayers_config(widget_name, widget_params, choices=None, input_format='tiff',
                    depth=True):
    """Return the Bilayers config for the inference widget `widget_name`.

    `widget_params` maps argument names to the values the run used; `choices`
    maps the names of the drop-down arguments to the values they offered.
    """
    values = {name: value for name, value in widget_params.items() if not is_layer(value)}
    return generic_bilayers_config(
        validate_filename(str(widget_name)), values,
        inputs=[image_entry('input_image', 'Input image', 'Image to segment',
                            subtype=['grayscale'], formats=[input_format],
                            unique_string=['*'], section='inputs',
                            depth=depth, pyramidal=False)],
        outputs=[image_entry('segmentation', 'Segmentation',
                             'Input image with the segmentation as OME-Zarr labels',
                             subtype=['label'], formats=[ZARR_FORMAT],
                             unique_string=['.ome.zarr'], section='outputs',
                             depth=depth, pyramidal=True)],
        citations=parameters.BILAYERS_CITATIONS,
        docker_image={**parameters.BILAYERS_DOCKER_IMAGE, 'tag': image_tag()},
        cli_command=parameters.BILAYERS_CLI_COMMAND,
        choices=choices,
    )


def image_tag():
    """Return the tag of the container image this run is in.

    The Dockerfile records the tag the image was built with in the environment;
    outside a container, or in an image built without one, the installed
    version of fair-segmentation stands in for it.
    """
    tag = os.environ.get(parameters.IMAGE_TAG_ENV)
    if tag:
        return tag
    try:
        return version('fair-segmentation')
    except PackageNotFoundError:
        return 'unknown'


def is_layer(value):
    """Return whether a widget value is a layer rather than a setting."""
    return hasattr(value, 'data') and hasattr(value, 'name')
