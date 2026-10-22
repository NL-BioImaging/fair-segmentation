"""Write a napari image layer and its label layers to one OME-Zarr store.

The intensity image becomes the multiscale image at the root of the store and
every label layer becomes an OME-Zarr labelled image under ``labels/``, so a
single ``*.ome.zarr`` holds the input pixels and the segmentation derived from
them:

    <name>.ome.zarr/            multiscales
      acquisition-metadata.yaml the acquisition metadata, on the imaging model
      ro-crate-metadata.json    describes the store and links that file
      labels/
        <label name>/           multiscales + image-label

ome-zarr-py writes both, pyramids and metadata, always from the layers, so the
store holds what the viewer showed; the axes, pixel sizes and units are those
of the layer, as the reader set them. The acquisition metadata, converted onto
the common model by imaging-metadata-converter, is kept next to the pixels as
biomero-converter does: in a file of its own, described by an RO-Crate in the
store.

Layers are taken by duck typing (``data``, ``name``, ``axis_labels``,
``scale``, ``units``) rather than by importing napari, so this module can be
used, and tested, without a viewer.
"""

from __future__ import annotations

from io import StringIO
import logging
import os.path
import re

import numpy as np
import yaml
import zarr
from imaging_metadata_converter import SOURCE_MAP_KEY
from imaging_metadata_converter.ModelPaths import DEFAULT_MODEL_FILE
from ome_zarr.writer import write_image, write_labels
from rocrate.model import ContextEntity
from rocrate.rocrate import ROCrate

from fair_segmentation import parameters
from fair_segmentation.util import validate_filename


logger = logging.getLogger(__name__)

ACQUISITION_METADATA_FILENAME = 'acquisition-metadata.yaml'
MODEL_SCHEMA_URL = ('https://github.com/NL-BioImaging/imaging-metadata-converter/blob/{release}/src/'
                    'imaging_metadata_converter/models/' + os.path.basename(DEFAULT_MODEL_FILE))
# OME-Zarr requires the axes in this order
DIM_ORDER = ('t', 'c', 'z', 'y', 'x')
# tifffile calls the colour samples of a pixel S
AXIS_NAMES = {'s': 'c'}
# empanada names some of its layers after the segmentation, not after the class
GENERIC_LAYER_NAMES = ('empanada_seg', 'panoptic-stack', 'batch_segs')
LAYER_NAME_SUFFIXES = ('-prediction', '_batch_segs', '-upsampled')


def write_ome_zarr(store_path, image_layer, label_layers=(), acquisition_metadata=None,
                   class_names=None, label_divisor=None):
    """Write `image_layer` and `label_layers` to the OME-Zarr store `store_path`.

    `acquisition_metadata` is the image's metadata on the common model, as
    imaging-metadata-converter returns it. `class_names` maps an empanada class
    id onto its name and `label_divisor` is the number of instances reserved
    per class, which together turn a label value into a class. Returns the
    store path.
    """
    store_path = str(store_path)
    root = zarr.open_group(store_path, mode='w')
    data, axes = layer_array(image_layer)
    write_image(data, root, axes=list(axes), **physical_args(image_layer, axes))

    for label_layer in label_layers:
        # a label layer without axis labels has the trailing axes of the image
        default_axes = axes[-np.ndim(full_resolution(label_layer)):]
        label_data, label_axes = layer_array(label_layer, default_axes)
        properties = label_properties(label_data, class_names, label_divisor,
                                      label_layer.name)
        # scaler=None: its default is the deprecated way of building the pyramid
        write_labels(label_data, root, name=validate_filename(label_layer.name),
                     scaler=None, axes=list(label_axes),
                     label_metadata={'properties': properties},
                     **physical_args(label_layer, label_axes))
    if label_layers:
        # ome-zarr-py leaves out the version 0.5 asks of the labels group
        labels = root['labels']
        labels.attrs['ome'] = {**labels.attrs['ome'], 'version': root.attrs['ome']['version']}

    write_acquisition_crate(store_path, image_layer.name, acquisition_metadata)
    return store_path


def write_acquisition_crate(store_path, name, acquisition_metadata=None):
    """Describe the store with an RO-Crate in it, linking its acquisition metadata.

    The metadata goes to a yaml file of its own, as biomero-converter writes it:
    on the imaging model of imaging-metadata-converter, which the file conforms
    to, without the converter's source map.
    """
    crate = ROCrate()
    crate.root_dataset['name'] = name
    crate.root_dataset['description'] = 'OME-Zarr image and its segmentation, written by fair-segmentation'
    if acquisition_metadata:
        metadata = {key: value for key, value in acquisition_metadata.items() if key != SOURCE_MAP_KEY}
        yaml_text = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
        metadata_file = crate.add_file(source=StringIO(yaml_text), dest_path=ACQUISITION_METADATA_FILENAME,
                                       properties={
            'name': 'Acquisition metadata',
            'description': 'Image acquisition metadata converted to the imaging metadata model '
                           '(https://github.com/NL-BioImaging/imaging-metadata-converter)',
            'encodingFormat': 'application/yaml',
        })
        metadata_file['about'] = crate.root_dataset
        metadata_file['conformsTo'] = model_schema_entity(crate)
    crate.write(store_path)


def model_schema_entity(crate):
    """The imaging model's LinkML schema, at the release of the installed converter's model."""
    version = model_schema_version()
    properties = {'@type': ['CreativeWork', 'Profile'],
                  'name': 'Imaging metadata model (LinkML schema)',
                  'encodingFormat': 'application/yaml'}
    if version:
        properties['version'] = version
    url = MODEL_SCHEMA_URL.format(release=f'v{version}' if version else 'main')
    return crate.add(ContextEntity(crate, identifier=url, properties=properties))


def model_schema_version():
    """The version in the model's header, read up to it rather than loading the whole schema."""
    with open(DEFAULT_MODEL_FILE, encoding='utf-8') as file:
        for line in file:
            match = re.match(r'version:\s*(\S+)', line)
            if match:
                return match.group(1).strip('\'"')
    return None


def full_resolution(layer):
    """Return the full resolution level of a layer: ome-zarr-py builds the pyramid."""
    return layer.data[0] if isinstance(layer.data, (list, tuple)) else layer.data


def layer_array(layer, default_axes=None):
    """Return the full resolution data of `layer` and its axes, in OME-Zarr order.

    The axes are the layer's own axis labels where the reader gave them, and
    `default_axes` otherwise.
    """
    data = full_resolution(layer)
    axes = layer_axes(layer) or default_axes or ('z', 'y', 'x')[-np.ndim(data):]
    order = sorted(range(len(axes)), key=lambda index: DIM_ORDER.index(axes[index]))
    if order != list(range(len(axes))):
        data = np.transpose(data, order)
    return data, tuple(axes[index] for index in order)


def layer_axes(layer):
    """Return the layer's axis labels as OME-Zarr axis names, or None."""
    labels = getattr(layer, 'axis_labels', None) or ()
    axes = tuple(AXIS_NAMES.get(str(label).lower(), str(label).lower()) for label in labels)
    valid = set(axes) <= set(DIM_ORDER) and len(set(axes)) == len(axes)
    return axes if valid and len(axes) == np.ndim(full_resolution(layer)) else None


def physical_args(layer, axes):
    """Return the scale and units of the layer's spatial axes for ome-zarr-py.

    napari keeps a scale and unit per axis of the layer, in the layer's own
    order; an axis left in pixels, such as the colour samples, gets neither.
    """
    own_axes = layer_axes(layer) or axes
    scale, units = {}, {}
    layer_units = getattr(layer, 'units', None) or [None] * len(own_axes)
    for axis, value, unit in zip(own_axes, getattr(layer, 'scale', ()), layer_units):
        unit = str(unit) if unit is not None else None
        if axis == 'c' or unit in (None, 'pixel'):
            continue
        scale[axis] = float(value)
        units[axis] = unit
    return {'scale': scale or None, 'axes_units': units or None}


def label_properties(label_data, class_names=None, label_divisor=None, layer_name=None):
    """Return the ``image-label`` properties giving every label value its class.

    For an empanada panoptic segmentation the class is `value // label_divisor`.
    Instance segmentations run to many thousands of labels, so past
    MAX_LABEL_PROPERTIES none are listed.
    """
    values = unique_labels(label_data)
    if len(values) > parameters.MAX_LABEL_PROPERTIES:
        logger.info('%d labels exceeds the %d property limit; no properties written',
                    len(values), parameters.MAX_LABEL_PROPERTIES)
        return []
    classes = class_map(values, class_names, label_divisor, layer_name)
    return [{'label-value': int(value), 'class-id': classes[value][0],
             'class-name': classes[value][1]} for value in values]


def unique_labels(label_data):
    """Return the sorted label values present, excluding the background."""
    values = np.unique(np.asarray(label_data))
    return [value for value in values.tolist() if value != 0]


def class_map(values, class_names=None, label_divisor=None, layer_name=None):
    """Map every label value onto its (class id, class name)."""
    if class_names and label_divisor:
        divisor = int(label_divisor)
        return {value: class_of(int(value) // divisor, class_names)
                for value in values}
    # without a panoptic encoding the whole label image is one class, which the
    # layer was named after
    return {value: (1, class_name_from_layer_name(layer_name)) for value in values}


def class_of(class_id, class_names):
    """Return the (id, name) of a class id, naming it after the id if unknown."""
    name = class_names.get(class_id, class_names.get(str(class_id)))
    if name is None:
        logger.warning('no class name for class id %s', class_id)
        name = f'class-{class_id}'
    return class_id, str(name)


def class_name_from_layer_name(layer_name):
    """Return the class a layer name states, or a generic name if it states none."""
    name = str(layer_name or '').strip()
    for suffix in LAYER_NAME_SUFFIXES:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    if not name or any(generic in name for generic in GENERIC_LAYER_NAMES):
        return 'segmentation'
    return name


def class_info_from_params(params):
    """Return (class names, label divisor) for the empanada widget parameters.

    The inference widgets hold the model in `model_config` and the instances
    reserved per class in `maximum_objects_per_class`; together they decode the
    class of a label value.
    """
    params = params or {}
    class_names = empanada_class_names(params.get('model_config'))
    divisor = params.get('maximum_objects_per_class')
    try:
        divisor = int(divisor)
    except (TypeError, ValueError):
        divisor = None
    if not class_names or not divisor:
        return None, None
    return class_names, divisor


def empanada_class_names(model_config_name):
    """Return {class id: class name} for an empanada model, or None.

    empanada is imported here rather than at module level: the class names are
    a convenience for the segmentations it produces, not a requirement for
    writing a store.
    """
    if not model_config_name:
        return None
    try:
        from empanada.config_loaders import read_yaml
        from empanada_napari.utils import get_configs
    except ImportError:
        logger.info('empanada is not installed; label classes come from the '
                    'layer name')
        return None
    config_file = get_configs().get(str(model_config_name))
    if config_file is None:
        logger.warning('unknown empanada model config %s', model_config_name)
        return None
    class_names = read_yaml(config_file).get('class_names')
    if not class_names:
        return None
    return {int(class_id): name for class_id, name in class_names.items()}

