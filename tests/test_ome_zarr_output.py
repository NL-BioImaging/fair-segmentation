"""Tests for writing an image layer and its labels to one OME-Zarr store."""

import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml
import zarr
from imaging_metadata_converter import SOURCE_MAP_KEY

from fair_segmentation import parameters
from fair_segmentation.ome_zarr_output import (
    ACQUISITION_METADATA_FILENAME,
    class_name_from_layer_name,
    label_properties,
    layer_array,
    write_ome_zarr,
)


LABEL_DIVISOR = 10000
CLASS_NAMES = {1: 'mito', 2: 'lipid'}
PIXEL_SIZE = 0.005
# as imaging-metadata-converter returns it: on the model, with its source map
ACQUISITION_METADATA = {
    'Instrument': {'Manufacturer': 'Acme', 'Model': 7},
    SOURCE_MAP_KEY: {'Instrument.Model': {'Source': 'Model'}},
}


def layer(data, name, axis_labels=None, scale=None, units=None):
    """A stand-in for a napari layer, as napari-meta-tiff sets it up."""
    ndim = data[0].ndim if isinstance(data, list) else data.ndim
    return SimpleNamespace(
        data=data,
        name=name,
        axis_labels=axis_labels if axis_labels is not None else tuple(str(-i) for i in range(ndim, 0, -1)),
        scale=scale if scale is not None else (1.0,) * ndim,
        units=units if units is not None else ('pixel',) * ndim,
    )


def image_layer(data, axis_labels=('Z', 'Y', 'X')):
    ndim = data.ndim
    return layer(data, 'input', axis_labels=axis_labels,
                 scale=(0.05,) + (PIXEL_SIZE,) * (ndim - 1) if ndim == 3 else (PIXEL_SIZE,) * ndim,
                 units=('micrometer',) * ndim)


def label_volume(shape=(4, 256, 300)):
    """A two class, three instance panoptic segmentation as empanada encodes it."""
    labels = np.zeros(shape, dtype=np.uint32)
    labels[1:3, 10:120, 10:120] = LABEL_DIVISOR + 1        # class 1, instance 1
    labels[1:3, 130:250, 10:120] = LABEL_DIVISOR + 2       # class 1, instance 2
    labels[1:3, 10:120, 150:290] = 2 * LABEL_DIVISOR + 3   # class 2, instance 3
    return labels


def label_plane(shape=(256, 256)):
    """The same, for a single plane: one instance of each of the two classes."""
    labels = np.zeros(shape, dtype=np.uint32)
    labels[10:120, 10:120] = LABEL_DIVISOR + 1
    labels[130:250, 10:120] = 2 * LABEL_DIVISOR + 3
    return labels


def ome_attrs(store_path, *group):
    return dict(zarr.open_group(Path(store_path).joinpath(*group), mode='r').attrs)['ome']


@pytest.fixture()
def image():
    return np.random.default_rng(0).integers(0, 255, (4, 256, 300), dtype=np.uint8)


@pytest.fixture()
def store(tmp_path, image):
    """A written store holding a small volume and its segmentation."""
    seg = label_volume()
    return write_ome_zarr(
        tmp_path / 'segmented.ome.zarr',
        image_layer(image),
        # empanada copies the image's scale and units, not its axis labels
        [layer(seg, 'mito-prediction', scale=(0.05, PIXEL_SIZE, PIXEL_SIZE),
               units=('micrometer',) * 3)],
        acquisition_metadata=ACQUISITION_METADATA,
        class_names=CLASS_NAMES, label_divisor=LABEL_DIVISOR)


class TestWriteOmeZarr:
    def test_image_multiscales(self, store):
        multiscales = ome_attrs(store)['multiscales'][0]
        assert [axis['name'] for axis in multiscales['axes']] == ['z', 'y', 'x']
        assert {axis.get('unit') for axis in multiscales['axes']} == {'micrometer'}
        scale = multiscales['datasets'][0]['coordinateTransformations'][0]['scale']
        assert scale == pytest.approx([0.05, PIXEL_SIZE, PIXEL_SIZE])

    def test_store_validates(self, store):
        from ome_zarr_models.v05.image import Image

        Image.from_zarr(zarr.open_group(store, mode='r'))

    def test_labels_group_lists_the_label(self, store):
        labels = ome_attrs(store, 'labels')
        assert labels['labels'] == ['mito-prediction']
        assert labels['version'] == '0.5'

    def test_label_has_the_image_axes_and_scale(self, store):
        multiscales = ome_attrs(store, 'labels', 'mito-prediction')['multiscales'][0]
        assert [axis['name'] for axis in multiscales['axes']] == ['z', 'y', 'x']
        scale = multiscales['datasets'][0]['coordinateTransformations'][0]['scale']
        assert scale == pytest.approx([0.05, PIXEL_SIZE, PIXEL_SIZE])

    def test_image_label_properties_carry_the_classes(self, store):
        properties = ome_attrs(store, 'labels', 'mito-prediction')['image-label']['properties']
        assert {(p['label-value'], p['class-id'], p['class-name']) for p in properties} == {
            (LABEL_DIVISOR + 1, 1, 'mito'),
            (LABEL_DIVISOR + 2, 1, 'mito'),
            (2 * LABEL_DIVISOR + 3, 2, 'lipid'),
        }

    def test_labels_are_read_without_image_rendering_settings(self, store):
        """A reader turns no image rendering (contrast limits) into label layer settings."""
        from ome_zarr.io import parse_url
        from ome_zarr.reader import Reader

        nodes = {node.metadata.get('name'): node.metadata for node in Reader(parse_url(store))()}
        assert 'contrast_limits' not in nodes['mito-prediction']

    def test_zarr_json_holds_ome_metadata_only(self, store):
        assert list(zarr.open_group(store, mode='r').attrs) == ['ome']

    def test_acquisition_metadata_is_a_yaml_file_without_the_source_map(self, store):
        metadata = yaml.safe_load((Path(store) / ACQUISITION_METADATA_FILENAME).read_text(encoding='utf-8'))
        assert metadata == {'Instrument': {'Manufacturer': 'Acme', 'Model': 7}}

    def test_crate_in_the_store_links_the_acquisition_metadata(self, store):
        graph = json.loads((Path(store) / 'ro-crate-metadata.json').read_text())['@graph']
        entities = {entity['@id']: entity for entity in graph}
        metadata_file = entities[ACQUISITION_METADATA_FILENAME]
        assert metadata_file['about'] == {'@id': './'}
        assert {'@id': ACQUISITION_METADATA_FILENAME} in entities['./']['hasPart']
        schema = entities[metadata_file['conformsTo']['@id']]
        assert 'imaging-metadata-converter' in schema['@id']
        assert 'Profile' in schema['@type']

    def test_store_without_acquisition_metadata_still_has_a_crate(self, tmp_path):
        store = write_ome_zarr(tmp_path / 'bare.ome.zarr',
                               image_layer(np.zeros((256, 256), dtype=np.uint8), ('Y', 'X')))
        assert (Path(store) / 'ro-crate-metadata.json').exists()
        assert not (Path(store) / ACQUISITION_METADATA_FILENAME).exists()

    def test_pixels_round_trip(self, store, image):
        written = zarr.open_group(store, mode='r')
        level0 = ome_attrs(store)['multiscales'][0]['datasets'][0]['path']
        np.testing.assert_array_equal(written[level0][:], image)
        label = written['labels/mito-prediction']
        np.testing.assert_array_equal(label[level0][:], label_volume())

    def test_label_pyramid_does_not_invent_label_values(self, store):
        label = zarr.open_group(Path(store) / 'labels' / 'mito-prediction', mode='r')
        allowed = set(np.unique(label_volume()).tolist())
        for dataset in ome_attrs(store, 'labels', 'mito-prediction')['multiscales'][0]['datasets']:
            assert set(np.unique(label[dataset['path']][:]).tolist()) <= allowed

    def test_multiscale_layer_uses_its_full_resolution_level(self, tmp_path):
        full = np.zeros((256, 256), dtype=np.uint8)
        levels = [full, full[::2, ::2]]
        store = write_ome_zarr(tmp_path / 'multiscale.ome.zarr',
                               layer(levels, 'input', axis_labels=('Y', 'X')))
        level0 = ome_attrs(store)['multiscales'][0]['datasets'][0]['path']
        assert zarr.open_group(store, mode='r')[level0].shape == (256, 256)

    def test_store_without_labels(self, tmp_path):
        store = write_ome_zarr(tmp_path / 'image_only.ome.zarr',
                               image_layer(np.zeros((256, 256), dtype=np.uint8), ('Y', 'X')))
        assert 'multiscales' in ome_attrs(store)
        assert not (Path(store) / 'labels').exists()

    def test_written_without_warnings_or_consolidated_metadata(self, tmp_path):
        with warnings.catch_warnings():
            warnings.simplefilter('error', UserWarning)
            warnings.simplefilter('error', DeprecationWarning)
            store = write_ome_zarr(tmp_path / 'quiet.ome.zarr',
                                   image_layer(np.zeros((256, 256), dtype=np.uint8), ('Y', 'X')),
                                   [layer(label_plane(), 'empanada_seg_2d')])
        root = json.loads((Path(store) / 'zarr.json').read_text())
        assert root.get('consolidated_metadata') is None


class TestRewrite:
    def test_store_is_replaced_by_the_current_layers(self, tmp_path, image):
        """A rerun writes what the viewer shows now, not what an earlier run left."""
        store_path = tmp_path / 'cells.ome.zarr'
        write_ome_zarr(store_path, image_layer(image), [layer(label_volume(), 'nuclei')])
        changed = image // 2
        store = write_ome_zarr(store_path, image_layer(changed), [layer(label_volume(), 'mito-prediction')])

        assert ome_attrs(store, 'labels')['labels'] == ['mito-prediction']
        level0 = ome_attrs(store)['multiscales'][0]['datasets'][0]['path']
        np.testing.assert_array_equal(zarr.open_group(store, mode='r')[level0][:], changed)


class TestAxes:
    def test_axes_come_from_the_axis_labels(self):
        _, axes = layer_array(layer(np.zeros((3, 4, 5)), 'input', axis_labels=('Z', 'Y', 'X')))
        assert axes == ('z', 'y', 'x')

    def test_colour_samples_become_a_leading_channel_axis(self):
        data, axes = layer_array(layer(np.zeros((4, 5, 3)), 'rgb', axis_labels=('Y', 'X', 'S')))
        assert axes == ('c', 'y', 'x')
        assert data.shape == (3, 4, 5)

    def test_layer_without_axis_labels_takes_the_default(self):
        _, axes = layer_array(layer(np.zeros((4, 5)), 'seg'), default_axes=('y', 'x'))
        assert axes == ('y', 'x')

    def test_axes_in_pixels_get_no_unit(self, tmp_path):
        store = write_ome_zarr(tmp_path / 'pixels.ome.zarr',
                               layer(np.zeros((256, 256), dtype=np.uint8), 'input',
                                     axis_labels=('Y', 'X')))
        axes = ome_attrs(store)['multiscales'][0]['axes']
        assert all('unit' not in axis for axis in axes)


class TestLabelProperties:
    def test_panoptic_labels_are_split_into_classes(self):
        properties = label_properties(label_plane(), CLASS_NAMES, LABEL_DIVISOR)
        assert [(p['class-id'], p['class-name']) for p in properties] == [(1, 'mito'), (2, 'lipid')]

    def test_unknown_class_id_is_named_after_the_id(self):
        labels = np.array([[0, 3 * LABEL_DIVISOR + 1]])
        properties = label_properties(labels, CLASS_NAMES, LABEL_DIVISOR)
        assert properties[0]['class-name'] == 'class-3'

    def test_without_a_divisor_the_layer_name_is_the_class(self):
        properties = label_properties(np.array([[0, 1, 2]]), layer_name='mito-prediction')
        assert {p['class-name'] for p in properties} == {'mito'}

    def test_background_is_not_a_label(self):
        assert label_properties(np.zeros((4, 4), dtype=np.uint8)) == []

    def test_many_labels_are_not_listed(self, monkeypatch):
        monkeypatch.setattr(parameters, 'MAX_LABEL_PROPERTIES', 5)
        assert label_properties(np.arange(10).reshape(2, 5)) == []


class TestClassNameFromLayerName:
    @pytest.mark.parametrize('layer_name, expected', [
        ('mito-prediction', 'mito'),
        ('nucleus_batch_segs', 'nucleus'),
        ('empanada_seg_2d', 'segmentation'),
        ('panoptic-stack', 'segmentation'),
        ('', 'segmentation'),
        (None, 'segmentation'),
    ])
    def test_class_name(self, layer_name, expected):
        assert class_name_from_layer_name(layer_name) == expected
