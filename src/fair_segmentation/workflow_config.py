"""Describe a segmentation run as a Bilayers workflow specification.

The RO-Crate packaging a run names a Bilayers ``config.yaml`` as its workflow.
There is no hand written one for empanada-napari, so it is generated from the
values of the inference widget, with fair-metadata-integration: every value
becomes a parameter whose default is the value the run used, so the config
records how the segmentation was produced as well as what can be set.

Widget values that are layers are the data the run consumed and produced, not
parameters; they are described by the single image input and the segmentation
output instead.

Every widget is a section of the config, named after it: the inference
widget's values are its parameters, those of the other widgets (e.g. the
measure widget's output folder) are display-only entries. The run's parameters
file holds the values by the same sections, so each value is at its entry.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import os

from fair_metadata_integration import bilayers_config as generic_bilayers_config, display_entry, image_entry

from fair_segmentation import parameters
from fair_segmentation.util import validate_filename


ZARR_FORMAT = 'omezarr'


def bilayers_config(widget_name, widget_params, choices=None, input_format='tiff',
                    depth=True, other_widgets=None):
    """Return the Bilayers config for the inference widget `widget_name`.

    `widget_params` maps argument names to the values the run used; `choices`
    maps the names of the drop-down arguments to the values they offered.
    `other_widgets` maps the names of the other widgets to their values, which
    become display-only entries.
    """
    display_only = [display_entry(key, value, section=widget_section(name))
                    for name, values in (other_widgets or {}).items() if name != widget_name
                    for key, value in settings(values).items()]
    return generic_bilayers_config(
        widget_section(widget_name), settings(widget_params),
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
        section=widget_section(widget_name),
        display_only=display_only,
    )


def run_values(widget_params):
    """Return the values of every widget by its section, as the parameters file holds them."""
    return {widget_section(name): settings(values) for name, values in widget_params.items()}


def widget_section(widget_name):
    """Return the section_id of a widget: its name, as a file name."""
    return validate_filename(str(widget_name))


def settings(values):
    """Return the values of a widget that are settings: not layers, and set."""
    return {key: value for key, value in values.items()
            if value is not None and not is_layer(value)}


def software():
    """Return fair-segmentation, which packages the run, as software of the crate."""
    return {**parameters.SOFTWARE, 'version': image_tag()}


def segmentation_software():
    """Return empanada-napari, which segments the image, with its installed version."""
    try:
        return {**parameters.SEGMENTATION_SOFTWARE, 'version': version('empanada-napari')}
    except PackageNotFoundError:
        return dict(parameters.SEGMENTATION_SOFTWARE)


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
