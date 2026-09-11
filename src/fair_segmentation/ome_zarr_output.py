"""Write a napari image layer and its label layers to one OME-Zarr store.

The intensity image becomes the multiscale image at the root of the store and
every label layer becomes an OME-Zarr labelled image under ``labels/``, so a
single ``*.ome.zarr`` holds the input pixels and the segmentation derived from
them:

    <name>.ome.zarr/            multiscales + converted acquisition metadata
      labels/
        <label name>/           multiscales + image-label

ngff-zarr builds and writes the pyramids; it has no notion of labelled images,
so the ``labels`` listing and the ``image-label`` metadata are merged into the
group attributes here and validated against the schemas ngff-zarr bundles.

Layers are taken by duck typing (``data``, ``name``, ``scale``, ``translate``)
rather than by importing napari, so this module can be used, and tested,
without a viewer.
"""

from __future__ import annotations

import datetime
import logging
import os.path

import ngff_zarr as nz
import numpy as np
import zarr

from fair_segmentation import parameters
from fair_segmentation.util import convert_to_um, validate_filename


logger = logging.getLogger(__name__)

# OME-Zarr requires the axes in this order; 'c'/'t' are dropped when absent
DIM_ORDER = ('t', 'c', 'z', 'y', 'x')
SPATIAL_DIMS = ('z', 'y', 'x')
LABELS_GROUP = 'labels'
# empanada names some of its layers after the segmentation, not after the class
GENERIC_LAYER_NAMES = ('empanada_seg', 'panoptic-stack', 'batch_segs')
LAYER_NAME_SUFFIXES = ('-prediction', '_batch_segs', '-upsampled')


def write_ome_zarr(store_path, image_layer, label_layers=(), common_metadata=None,
                   workflow_metadata=None, class_names=None, label_divisor=None,
                   version=parameters.NGFF_VERSION, overwrite=True,
                   labels_visible=parameters.LABELS_VISIBLE):
    """Write `image_layer` and `label_layers` to the OME-Zarr store `store_path`.

    `common_metadata` is acquisition metadata on the common model (as returned
    by imaging_metadata_converter); its pixel sizes set the coordinate
    transformations and the whole tree is kept in the root attributes.
    `class_names` maps an empanada class id onto its name and `label_divisor`
    is the number of instances reserved per class, which together turn a label
    value into a class. `labels_visible` asks a viewer to open the label layers
    switched on rather than hidden. Returns the store path.
    """
    store_path = str(store_path)
    image = ngff_image_from_layer(image_layer, common_metadata, name='image')
    _write_multiscales(store_path, image, version=version, overwrite=overwrite)

    label_names = []
    for label_layer in label_layers:
        label_names.append(_write_label(
            store_path, label_layer, image_dims=image.dims, version=version,
            common_metadata=common_metadata, class_names=class_names,
            label_divisor=label_divisor, visible=labels_visible))
    if label_names:
        _write_labels_group(store_path, label_names, version=version)

    root_metadata = {'version': parameters.VERSION}
    if common_metadata:
        root_metadata['acquisition_metadata'] = common_metadata
    if workflow_metadata:
        root_metadata['workflow'] = workflow_metadata
    nz.update_root_attributes(
        store_path, {parameters.CUSTOM_METADATA_KEY: jsonable(root_metadata)})
    _consolidate(store_path)
    return store_path


def _write_multiscales(store_path, image, version, overwrite=True, method=None):
    """Build the pyramid for `image` and write it as an OME-Zarr image."""
    multiscales = nz.to_multiscales(
        image,
        scale_factors=parameters.ZARR_MULTISCALE_MIN_LENGTH,
        chunks={dim: parameters.ZARR_CHUNKS[dim] for dim in image.dims},
        method=method,
    )
    # ngff-zarr paths its levels 'scale<n>/<image name>', which the spec allows
    # but ome-zarr-models, which looks a dataset up as a direct child of the
    # group, cannot resolve; the flat '<n>' every other writer uses is read by
    # all of them
    for index, dataset in enumerate(multiscales.metadata.datasets):
        dataset.path = str(index)

    to_zarr_kwargs = {}
    if version != '0.4':
        # sharding needs zarr v3, which only the 0.5+ layouts use
        to_zarr_kwargs['chunks_per_shard'] = parameters.ZARR_SHARD_MULTIPLIER
    nz.to_ngff_zarr(store_path, multiscales, version=version, overwrite=overwrite,
                    **to_zarr_kwargs)
    return multiscales


def _write_label(store_path, label_layer, image_dims, version, common_metadata=None,
                 class_names=None, label_divisor=None, visible=True):
    """Write one label layer under ``labels/`` and return the name used."""
    layer_name = get_attr(label_layer, 'name', None) or LABELS_GROUP
    name = validate_filename(layer_name)
    label_path = os.path.join(store_path, LABELS_GROUP, name)

    drop_dims = dropped_dims(layer_data(label_layer).ndim, image_dims)
    image = ngff_image_from_layer(label_layer, common_metadata, name=name,
                                  drop_dims=drop_dims)
    # label values must survive downsampling, so no interpolating method here
    _write_multiscales(label_path, image, version=version, overwrite=True,
                       method=nz.Methods.ITKWASM_LABEL_IMAGE)

    image_label, summary = image_label_metadata(
        image.data, class_names=class_names, label_divisor=label_divisor,
        layer_name=layer_name)
    updates = {'image-label': image_label}
    if visible and 'colors' in image_label:
        updates['omero'] = omero_metadata(
            ', '.join(summary['classes'].values()) or layer_name,
            image_label['colors'])
    _merge_ome_attrs(label_path, updates, version=version, model='label')
    _merge_custom_attrs(label_path, summary, version=version)
    return name


def omero_metadata(channel_name, colors):
    """Return the rendering metadata that opens this label layer switched on.

    Both ome-zarr-py and napari-ome-zarr load a labelled image hidden, so that
    the labels do not cover the image they belong to. There is no visibility
    field in ``image-label``, but a labelled image is a multiscale image as
    well, so the ``omero`` rendering metadata of an image applies to it: napari
    takes the layer's visibility from `channels[0].active`. It reads the
    channel colour as a greyscale-to-colour map, which a label layer cannot
    use, so this goes in only alongside ``image-label.colors``, which napari
    prefers over it -- without those the layer fails to build. The channel name
    is appended to the layer name by napari, so it names the classes rather
    than repeating the name of the layer.
    """
    rgba = colors[0].get('rgba', [255, 255, 255, 255])
    return {
        'channels': [{
            'label': channel_name,
            'color': '{:02X}{:02X}{:02X}'.format(*rgba[:3]),
            'active': True,
        }],
    }


def _write_labels_group(store_path, label_names, version):
    """Write the ``labels`` group listing the labelled images below it."""
    labels_path = os.path.join(store_path, LABELS_GROUP)
    _merge_ome_attrs(labels_path, {LABELS_GROUP: list(label_names)}, version=version)


def ngff_image_from_layer(layer, common_metadata=None, name='image', drop_dims=()):
    """Return the NgffImage for `layer`, with its axes in OME-Zarr order.

    Pixel sizes come from the common acquisition metadata where it has them and
    from the layer's own scale otherwise, so an image read without acquisition
    metadata still gets whatever napari knows.
    """
    data = as_dask(layer_data(layer))
    dims = infer_dims(data.shape, common_metadata, drop_dims=drop_dims)
    # the layer's scale and translate have one entry per axis of the layer, so
    # they are read while the axes are still the layer's own
    physical_scale = metadata_scale(common_metadata, dims)
    scale = layer_vector(layer, dims, 'scale', 1.0)
    scale.update(physical_scale)
    translation = layer_vector(layer, dims, 'translate', 0.0)

    data, dims = reorder_dims(data, dims)
    data, dims = drop_singleton_dims(data, dims)
    return nz.to_ngff_image(
        data, dims=list(dims), name=name,
        scale={dim: scale[dim] for dim in dims},
        translation={dim: translation[dim] for dim in dims},
        # only the axes whose physical size is known get a physical unit: a
        # layer scale is in units napari does not state, and an axis left at
        # the fallback scale of 1 has no physical size to declare at all
        axes_units=axes_units(dim for dim in dims if dim in physical_scale))


def layer_data(layer):
    """Return the full resolution data of a layer.

    A multiscale layer hands us its levels; the pyramid is rebuilt from the
    full resolution level rather than re-used, as the levels of the source need
    not be the factors OME-Zarr asks for.
    """
    data = get_attr(layer, 'data', layer)
    if isinstance(data, (list, tuple)):
        data = data[0]
    if not hasattr(data, 'ndim'):
        data = np.asarray(data)
    return data


def infer_dims(shape, common_metadata=None, drop_dims=()):
    """Return the dimension name of every axis of an array of shape `shape`."""
    dims = metadata_dims(shape, common_metadata, drop_dims)
    if dims is not None:
        return dims
    return default_dims(shape)


def metadata_dims(shape, common_metadata, drop_dims=()):
    """Return dims from the acquisition metadata sizes, or None if they disagree.

    The sizes are only trusted when they reproduce the shape of the array
    exactly: readers and plugins squeeze, crop and split dimensions, so
    metadata that no longer describes the array must not name its axes.
    """
    pixels = nested_get(common_metadata, 'Image', 'Pixels')
    if not isinstance(pixels, dict):
        return None
    sizes = {}
    for dim in DIM_ORDER:
        size = pixels.get(f'Size{dim.upper()}')
        if size is None:
            continue
        try:
            sizes[dim] = int(size)
        except (TypeError, ValueError):
            return None
    dims = tuple(dim for dim in DIM_ORDER
                 if sizes.get(dim, 1) > 1 and dim not in drop_dims)
    if tuple(sizes[dim] for dim in dims) != tuple(shape):
        return None
    return dims


def default_dims(shape):
    """Name the axes of `shape` from its dimensionality alone."""
    ndim = len(shape)
    if ndim == 2:
        return ('y', 'x')
    if ndim == 3:
        # a trailing axis of a few samples is rgb(a), anything else is a stack
        return ('y', 'x', 'c') if shape[-1] in (2, 3, 4) else ('z', 'y', 'x')
    if ndim == 4:
        return ('c', 'z', 'y', 'x') if shape[0] <= 4 else ('t', 'z', 'y', 'x')
    if ndim == 5:
        return DIM_ORDER
    raise ValueError(f'Cannot name the axes of a {ndim}-dimensional image')


def dropped_dims(label_ndim, image_dims):
    """Return the image dims a label image of `label_ndim` axes cannot have.

    A segmentation of a multi-channel or time image is a single volume, so the
    channel, and then the time, axis of the image is not one of its axes.
    """
    dropped = []
    for dim in ('c', 't'):
        if len(image_dims) - len(dropped) > label_ndim and dim in image_dims:
            dropped.append(dim)
    return tuple(dropped)


def reorder_dims(data, dims):
    """Move the axes of `data` into the order OME-Zarr requires."""
    target = tuple(dim for dim in DIM_ORDER if dim in dims)
    if target == tuple(dims):
        return data, target
    order = [dims.index(dim) for dim in target]
    return np.moveaxis(data, order, range(len(target))), target


def drop_singleton_dims(data, dims):
    """Drop the axes of length one, apart from y and x.

    A single plane, channel or timepoint says nothing that the axes it is
    written without do not already say, and the downsampling of a label image
    cannot take an axis it has no room to filter along.
    """
    keep = tuple(dim for dim, size in zip(dims, data.shape)
                 if size > 1 or dim in ('y', 'x'))
    if keep == tuple(dims):
        return data, dims
    index = tuple(slice(None) if dim in keep else 0 for dim in dims)
    return data[index], keep


def layer_vector(layer, dims, attr, default):
    """Return the layer's `scale` or `translate` as a value per dimension."""
    values = get_attr(layer, attr, None)
    vector = {dim: default for dim in dims}
    if values is None:
        return vector
    values = list(np.atleast_1d(values))
    if len(values) != len(dims):
        # napari keeps one entry per layer axis; a mismatch means the vector
        # does not describe these axes, and guessing an alignment would
        # silently scale the wrong one
        logger.warning('ignoring layer %s %s: %d values for %d dimensions',
                       get_attr(layer, 'name', ''), attr, len(values), len(dims))
        return vector
    for dim, value in zip(dims, values):
        vector[dim] = float(value)
    return vector


def metadata_scale(common_metadata, dims):
    """Return the pixel size per dim from the common acquisition metadata.

    Spatial sizes are normalised to micrometer and the time increment to
    seconds, matching the units declared on the axes.
    """
    pixels = nested_get(common_metadata, 'Image', 'Pixels')
    scale = {}
    if not isinstance(pixels, dict):
        return scale
    for dim in dims:
        if dim in SPATIAL_DIMS:
            value = pixels.get(f'PhysicalSize{dim.upper()}')
            if isinstance(value, (int, float)) and value > 0:
                unit = pixels.get(f'PhysicalSize{dim.upper()}Unit', 'um')
                scale[dim] = convert_to_um(float(value), unit)
        elif dim == 't':
            value = pixels.get('TimeIncrement')
            if isinstance(value, (int, float)) and value > 0:
                scale[dim] = convert_to_seconds(
                    float(value), pixels.get('TimeIncrementUnit', 's'))
    return scale


def convert_to_seconds(value, unit):
    conversions = {
        'ns': 1e-9, 'nanosecond': 1e-9,
        'us': 1e-6, 'µs': 1e-6, 'microsecond': 1e-6,
        'ms': 1e-3, 'millisecond': 1e-3,
        's': 1, 'sec': 1, 'second': 1,
        'min': 60, 'minute': 60,
        'h': 3600, 'hour': 3600,
    }
    return value * conversions.get(unit, 1)


def axes_units(dims):
    """Return the unit of every dim of known physical size; a channel has none."""
    units = {}
    for dim in dims:
        if dim in SPATIAL_DIMS:
            units[dim] = 'micrometer'
        elif dim == 't':
            units[dim] = 'second'
    return units


def image_label_metadata(label_data, class_names=None, label_divisor=None,
                         layer_name=None):
    """Return the ``image-label`` metadata and class summary of a label image.

    The properties give every label value its class, which for an empanada
    panoptic segmentation is `value // label_divisor`. Instance segmentations
    run to many thousands of labels, so past MAX_LABEL_PROPERTIES the
    per-instance properties are left out; the class summary, written to our own
    attributes either way, is then the record of the classes.
    """
    values = unique_labels(label_data)
    classes = class_map(values, class_names=class_names,
                        label_divisor=label_divisor, layer_name=layer_name)

    image_label = {'source': {'image': '../../'}}
    if len(values) > parameters.MAX_LABEL_PROPERTIES:
        logger.info('%d labels exceeds the %d property limit; writing the class '
                    'summary only', len(values), parameters.MAX_LABEL_PROPERTIES)
    elif values:
        image_label['properties'] = [
            {'label-value': int(value),
             'class-id': classes[value][0],
             'class-name': classes[value][1]}
            for value in values
        ]
        # one colour per class, so every instance of a class is drawn the same
        # in any viewer rather than in a colour of the viewer's choosing
        colors = class_colors(classes)
        image_label['colors'] = [
            {'label-value': int(value), 'rgba': colors[classes[value][0]]}
            for value in values
        ]

    summary = {
        'label_count': len(values),
        'label_divisor': int(label_divisor) if label_divisor else None,
        'classes': {str(class_id): class_name
                    for class_id, class_name in sorted(set(classes.values()))},
    }
    return image_label, summary


def class_colors(classes):
    """Return an rgba per class id, taken from ngff-zarr's glasbey palette."""
    class_ids = sorted({class_id for class_id, _ in classes.values()})
    colors = {}
    for index, class_id in enumerate(class_ids):
        hex_color = nz.GLASBEY_COLORS[index % len(nz.GLASBEY_COLORS)]
        colors[class_id] = [int(hex_color[channel:channel + 2], 16)
                            for channel in (0, 2, 4)] + [255]
    return colors


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


def _merge_ome_attrs(group_path, updates, version, model=None):
    """Merge `updates` into the OME metadata of the group at `group_path`.

    From 0.5 on the OME metadata lives behind an ``ome`` key; 0.4 keeps it at
    the top level of the attributes.
    """
    group = _open_group(group_path, version)
    attrs = dict(group.attrs)
    if version == '0.4':
        attrs.update(updates)
        attrs.setdefault('version', version)
        to_validate = attrs
    else:
        ome = dict(attrs.get('ome', {}))
        ome.update(updates)
        ome.setdefault('version', version)
        attrs['ome'] = ome
        to_validate = {'ome': ome}
    if model:
        nz.validate(to_validate, version=version, model=model)
    group.attrs.put(attrs)


def _merge_custom_attrs(group_path, metadata, version):
    """Merge `metadata` into our own key in the group's attributes."""
    group = _open_group(group_path, version)
    attrs = dict(group.attrs)
    custom = dict(attrs.get(parameters.CUSTOM_METADATA_KEY, {}))
    custom.update(jsonable(metadata))
    attrs[parameters.CUSTOM_METADATA_KEY] = custom
    group.attrs.put(attrs)


def _open_group(group_path, version):
    """Open, or create, the zarr group of the layout `version` asks for."""
    return zarr.open_group(group_path, mode='a',
                           zarr_format=2 if version == '0.4' else 3)


def _consolidate(store_path):
    """Refresh the consolidated metadata so the label groups are listed in it."""
    try:
        zarr.consolidate_metadata(store_path)
    except Exception:
        # consolidated metadata is an optimisation: a store without it is still
        # a valid store, so a failure here must not discard what was written
        logger.warning('could not consolidate metadata for %s', store_path,
                       exc_info=True)


def as_dask(data):
    """Return `data` as a lazy dask array, keeping a lazy source lazy."""
    import dask.array as da

    if isinstance(data, da.Array):
        return data
    if isinstance(data, zarr.Array):
        return da.from_zarr(data)
    return da.from_array(np.asarray(data))


def get_attr(obj, name, default):
    """Return an attribute of a layer, or `default` when it has none."""
    value = getattr(obj, name, None)
    return default if value is None else value


def nested_get(mapping, *keys):
    """Return the value at a path of nested dicts, or None if it is not there."""
    for key in keys:
        if not isinstance(mapping, dict):
            return None
        mapping = mapping.get(key)
    return mapping


def jsonable(value):
    """Convert `value` into something the zarr attributes can hold.

    Acquisition metadata arrives with numpy scalars, tuples, bytes and
    datetimes in it, none of which are json.
    """
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
