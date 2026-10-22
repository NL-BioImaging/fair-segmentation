"""Describe a segmentation run as a Bilayers workflow specification.

The RO-Crate packaging a run names a Bilayers ``config.yaml`` as its workflow.
There is no hand written one for empanada-napari, so it is generated from the
values of the inference widget: every value becomes a parameter whose default
is the value the run used, so the config records how the segmentation was
produced as well as what can be set.

Widget values that are layers are the data the run consumed and produced, not
parameters; they are described by the single image input and the segmentation
output instead.

When biomero-schema is installed, the config is checked by converting it with
its Bilayers adapter before it is written.
"""

from __future__ import annotations

import logging
import os.path

import yaml

from fair_segmentation import parameters
from fair_segmentation.ome_zarr_output import jsonable
from fair_segmentation.util import validate_filename


logger = logging.getLogger(__name__)

PARAMETER_SECTION = 'input-args'
ZARR_FORMAT = 'omezarr'


def bilayers_config(widget_name, widget_params, choices=None, input_format='tiff',
                    depth=True):
    """Return the Bilayers config for the inference widget `widget_name`.

    `widget_params` maps argument names to the values the run used; `choices`
    maps the names of the drop-down arguments to the values they offered.
    """
    choices = choices or {}
    params = [parameter_entry(name, value, choices.get(name))
              for name, value in widget_params.items()
              if value is not None and not is_layer(value)]
    return {
        'citations': parameters.BILAYERS_CITATIONS,
        'docker_image': parameters.BILAYERS_DOCKER_IMAGE,
        'algorithm_folder_name': validate_filename(str(widget_name)),
        'exec_function': {
            'name': 'generate_cli_command',
            'cli_command': parameters.BILAYERS_CLI_COMMAND,
            'hidden_args': [],
        },
        'inputs': [image_entry('input_image', 'Input image', 'Image to segment',
                               subtype=['grayscale'], formats=[input_format],
                               unique_string=['*'], section='inputs',
                               depth=depth, pyramidal=False)],
        'outputs': [image_entry('segmentation', 'Segmentation',
                                'Input image with the segmentation as OME-Zarr labels',
                                subtype=['label'], formats=[ZARR_FORMAT],
                                unique_string=['.ome.zarr'], section='outputs',
                                depth=depth, pyramidal=True)],
        'parameters': params,
        'display_only': [],
    }


def image_entry(name, label, description, subtype, formats, unique_string, section,
                depth, pyramidal):
    """Return an input or output entry describing an image."""
    return {
        'name': name,
        'type': 'image',
        'label': label,
        'description': description,
        'subtype': subtype,
        'format': formats,
        'cli_tag': f'--{name}',
        'cli_order': 0,
        'default': '',
        'optional': False,
        'file_count': 'single',
        'unique_string': unique_string,
        'section_id': section,
        'mode': 'beginner',
        'depth': depth,
        'timepoints': False,
        'tiled': False,
        'pyramidal': pyramidal,
    }


def parameter_entry(name, value, choices=None):
    """Return the parameter entry for one widget value."""
    value = jsonable(value)
    entry = {
        'name': name,
        'label': name.replace('_', ' ').capitalize(),
        'description': '',
    }
    if choices:
        entry['type'] = 'dropdown'
        entry['options'] = [{'label': str(choice), 'value': jsonable(choice)}
                            for choice in choices]
        entry['multiselect'] = False
    elif isinstance(value, bool):
        entry['type'] = 'checkbox'
        entry['append_value'] = False
    elif isinstance(value, int):
        entry['type'] = 'integer'
    elif isinstance(value, float):
        entry['type'] = 'float'
    else:
        entry['type'] = 'textbox'
        value = str(value)
    entry.update({
        'default': value,
        'cli_tag': f'--{name}',
        'optional': False,
        'section_id': PARAMETER_SECTION,
        'mode': 'beginner',
    })
    return entry


def is_layer(value):
    """Return whether a widget value is a layer rather than a setting."""
    return hasattr(value, 'data') and hasattr(value, 'name')


def write_bilayers_config(path, config):
    """Validate `config` where possible and write it to `path` as yaml."""
    validate_bilayers_config(config)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        yaml.safe_dump(config, file, sort_keys=False, allow_unicode=True)
    return path


def validate_bilayers_config(config):
    """Convert `config` with biomero-schema's Bilayers adapter, if it is installed.

    The conversion validates the result as a BIOMERO workflow schema and raises
    if the config does not describe a valid workflow. biomero-schema is imported
    here rather than at module level: validation is a check, not a requirement
    for packaging a run.
    """
    try:
        from biomero_schema.adapters import parse_descriptor
    except ImportError:
        logger.info('biomero-schema is not installed; the workflow config is '
                    'written without validation')
        return None
    return parse_descriptor(config, name=config.get('algorithm_folder_name'))
