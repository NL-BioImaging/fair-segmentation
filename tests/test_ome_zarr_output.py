"""Tests for writing an image layer and its labels to one OME-Zarr store."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import zarr

from fair_segmentation import parameters
from fair_segmentation.ome_zarr_output import (
    class_name_from_layer_name,
    default_dims,
    dropped_dims,
    image_label_metadata,
    infer_dims,
    jsonable,
    metadata_scale,
    write_ome_zarr,
)


LABEL_DIVISOR = 10000
CLASS_NAMES = {1: 'mito', 2: 'lipid'}


def layer(data, name, scale=None, translate=None):
    """A stand-in for a napari layer: this module only duck types them."""
    ndim = data[0].ndim if isinstance(data, list) else data.ndim
    return SimpleNamespace(
        data=data,
        name=name,
        scale=scale if scale is not None else (1.0,) * ndim,
        translate=translate if translate is not None else (0.0,) * ndim,
        metadata={},
    )


def common_metadata(size_x=300, size_y=256, size_z=4):
    """Acquisition metadata on the common model, as the converter returns it."""
    return {
        'Image': {'Pixels': {
            'SizeX': size_x, 'SizeY': size_y, 'SizeZ': size_z, 'SizeC': 1, 'SizeT': 1,
            'PhysicalSizeX': 5.0, 'PhysicalSizeXUnit': 'nm',
            'PhysicalSizeY': 5.0, 'PhysicalSizeYUnit': 'nm',
            'PhysicalSizeZ': 50.0, 'PhysicalSizeZUnit': 'nm',
        }},
        'Instrument': {'Manufacturer': 'Acme', 'Model': 'Widget-1000'},
    }


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
    """Return the OME metadata of a group in a 0.5 store."""
    return dict(zarr.open_group(Path(store_path).joinpath(*group),
                                mode='r').attrs)['ome']


def custom_attrs(store_path, *group):
    """Return our own metadata of a group."""
    return dict(zarr.open_group(Path(store_path).joinpath(*group),
                                mode='r').attrs)[parameters.CUSTOM_METADATA_KEY]


@pytest.fixture()
def store(tmp_path):
    """A written store holding a small volume and its segmentation."""
    image = np.random.default_rng(0).integers(0, 255, (4, 256, 300), dtype=np.uint8)
    return write_ome_zarr(
        tmp_path / 'segmented.ome.zarr',
        layer(image, 'input'),
        [layer(label_volume(), 'mito-prediction')],
        common_metadata=common_metadata(),
        workflow_metadata={'model_config': 'MitoNet_v1'},
        class_names=CLASS_NAMES,
        label_divisor=LABEL_DIVISOR,
    )


class TestWriteOmeZarr:
    def test_image_multiscales(self, store):
        """The root is an OME-Zarr image with the acquisition pixel sizes in um."""
        multiscales = ome_attrs(store)['multiscales'][0]
        assert [axis['name'] for axis in multiscales['axes']] == ['z', 'y', 'x']
        assert [axis['unit'] for axis in multiscales['axes']] == ['micrometer'] * 3
        transformations = multiscales['datasets'][0]['coordinateTransformations']
        scale = next(transformation['scale'] for transformation in transformations
                     if transformation['type'] == 'scale')
        # 50 nm sections of 5 nm pixels, stated in micrometer
        assert scale == pytest.approx([0.05, 0.005, 0.005])

    def test_labels_group_lists_the_label(self, store):
        assert ome_attrs(store, 'labels')['labels'] == ['mito-prediction']

    def test_image_label_properties_carry_the_classes(self, store):
        image_label = ome_attrs(store, 'labels', 'mito-prediction')['image-label']
        assert image_label['source']['image'] == '../../'
        classes = {property['label-value']: property['class-name']
                   for property in image_label['properties']}
        assert classes == {
            LABEL_DIVISOR + 1: 'mito',
            LABEL_DIVISOR + 2: 'mito',
            2 * LABEL_DIVISOR + 3: 'lipid',
        }

    def test_label_group_validates_as_a_labelled_image(self, store):
        """The label group satisfies the OME-Zarr label schema."""
        import ngff_zarr as nz

        attrs = dict(zarr.open_group(
            Path(store) / 'labels' / 'mito-prediction', mode='r').attrs)
        nz.validate({'ome': attrs['ome']},
                    version=parameters.NGFF_VERSION, model='label')

    def test_every_level_resolves_within_its_group(self, store):
        """A dataset path is relative to the group whose multiscales names it."""
        for group in ((), ('labels', 'mito-prediction')):
            zarr_group = zarr.open_group(Path(store).joinpath(*group), mode='r')
            datasets = ome_attrs(store, *group)['multiscales'][0]['datasets']
            assert datasets
            for dataset in datasets:
                assert isinstance(zarr_group[dataset['path']], zarr.Array)

    def test_levels_are_direct_children_of_their_group(self, store):
        """The flat level paths, which every reader resolves."""
        for group in ((), ('labels', 'mito-prediction')):
            datasets = ome_attrs(store, *group)['multiscales'][0]['datasets']
            assert [dataset['path'] for dataset in datasets] == \
                [str(index) for index in range(len(datasets))]

    def test_store_parses_as_an_image_with_a_labelled_image(self, store):
        """ome-zarr-models, which only resolves a flat dataset path, reads it."""
        models = pytest.importorskip('ome_zarr_models')

        root = models.open_ome_zarr(zarr.open_group(store, mode='r'))
        assert type(root).__name__ == 'Image'
        label = models.open_ome_zarr(zarr.open_group(
            Path(store) / 'labels' / 'mito-prediction', mode='r'))
        assert type(label).__name__ == 'ImageLabel'

    def test_store_is_read_as_an_image_with_labels(self, store):
        """ome-zarr-py, which OMERO and napari read through, sees both."""
        pytest.importorskip('ome_zarr')
        from ome_zarr.io import parse_url
        from ome_zarr.reader import Reader

        nodes = list(Reader(parse_url(store))())
        specs = {type(spec).__name__ for node in nodes for spec in node.specs}
        assert {'Multiscales', 'Labels', 'Label'} <= specs, \
            f'the labelled image was not picked up, only {specs}'

        label_node = next(node for node in nodes
                          if any(type(spec).__name__ == 'Label' for spec in node.specs))
        assert label_node.data[0].shape == (4, 256, 300)
        assert {property['class-name']
                for property in label_node.metadata['properties'].values()} == \
            {'mito', 'lipid'}

    def test_labels_are_asked_to_open_switched_on(self, store):
        """Readers hide a labelled image; the omero metadata asks for it back."""
        label_attrs = ome_attrs(store, 'labels', 'mito-prediction')
        assert label_attrs['omero']['channels'][0]['active'] is True

    def test_label_layer_is_visible_in_napari(self, store):
        """What napari actually builds from the store: a visible labels layer."""
        pytest.importorskip('napari_ome_zarr')
        pytest.importorskip('napari')
        from napari.layers import Labels
        from napari_ome_zarr.ome_zarr_reader import read_ome_zarr

        layers = read_ome_zarr(zarr.open_group(store, mode='r'))()
        data, kwargs, layer_type = next(
            layer for layer in layers if layer[2] == 'labels')
        assert kwargs['visible'] is True

        # the omero metadata also hands napari a channel colour, which a labels
        # layer cannot use: without image-label.colors this raises
        layer = Labels(data[0], visible=kwargs['visible'],
                       colormap=kwargs['colormap'])
        assert layer.visible

    def test_labels_can_be_left_hidden(self, tmp_path):
        store = write_ome_zarr(
            tmp_path / 'hidden.ome.zarr',
            layer(np.zeros((256, 256), dtype=np.uint8), 'input'),
            [layer(label_plane(), 'mito-prediction')],
            class_names=CLASS_NAMES, label_divisor=LABEL_DIVISOR,
            labels_visible=False)
        assert 'omero' not in ome_attrs(store, 'labels', 'mito-prediction')

    def test_each_class_gets_one_colour(self, store):
        """Every instance of a class is drawn in the same colour."""
        image_label = ome_attrs(store, 'labels', 'mito-prediction')['image-label']
        colors = {color['label-value']: tuple(color['rgba'])
                  for color in image_label['colors']}
        assert colors[LABEL_DIVISOR + 1] == colors[LABEL_DIVISOR + 2]
        assert colors[LABEL_DIVISOR + 1] != colors[2 * LABEL_DIVISOR + 3]
        assert all(len(rgba) == 4 and all(0 <= value <= 255 for value in rgba)
                   for rgba in colors.values())

    def test_label_class_summary(self, store):
        summary = custom_attrs(store, 'labels', 'mito-prediction')
        assert summary['label_count'] == 3
        assert summary['label_divisor'] == LABEL_DIVISOR
        assert summary['classes'] == {'1': 'mito', '2': 'lipid'}

    def test_acquisition_metadata_is_kept(self, store):
        metadata = custom_attrs(store)
        assert metadata['acquisition_metadata']['Instrument']['Model'] == 'Widget-1000'
        assert metadata['workflow']['model_config'] == 'MitoNet_v1'
        assert metadata['version'] == parameters.VERSION

    def test_pixels_round_trip(self, tmp_path):
        """The image and the label values come back out of the store."""
        image = np.arange(64 * 80, dtype=np.uint8).reshape(64, 80)
        labels = np.zeros((64, 80), dtype=np.uint32)
        labels[10:20, 10:20] = LABEL_DIVISOR + 7
        store = write_ome_zarr(tmp_path / 'flat.ome.zarr', layer(image, 'input'),
                               [layer(labels, 'mito-prediction')])

        group = zarr.open_group(store, mode='r')
        written_image = group[ome_attrs(store)['multiscales'][0]['datasets'][0]['path']]
        np.testing.assert_array_equal(written_image[:], image)

        label_group = ome_attrs(store, 'labels', 'mito-prediction')
        written_labels = zarr.open_group(Path(store) / 'labels' / 'mito-prediction',
                                        mode='r')[
            label_group['multiscales'][0]['datasets'][0]['path']]
        np.testing.assert_array_equal(written_labels[:], labels)

    def test_label_pyramid_does_not_invent_label_values(self, tmp_path, monkeypatch):
        """Downsampling a label image keeps label values, it does not blend them."""
        monkeypatch.setattr(parameters, 'ZARR_CHUNKS',
                            dict(parameters.ZARR_CHUNKS, x=256, y=256))
        image = np.zeros((1024, 1024), dtype=np.uint8)
        labels = np.zeros((1024, 1024), dtype=np.uint32)
        for index in range(4):
            labels[index * 256:(index + 1) * 256] = LABEL_DIVISOR + index + 1
        store = write_ome_zarr(tmp_path / 'pyramid.ome.zarr', layer(image, 'input'),
                               [layer(labels, 'mito-prediction')])

        datasets = ome_attrs(store, 'labels', 'mito-prediction')['multiscales'][0]['datasets']
        assert len(datasets) > 1, 'expected a pyramid for a 1024 pixel label image'
        group = zarr.open_group(Path(store) / 'labels' / 'mito-prediction', mode='r')
        for dataset in datasets:
            level = group[dataset['path']][:]
            assert set(np.unique(level)) <= set(np.unique(labels))

    def test_multiscale_layer_uses_its_full_resolution_level(self, tmp_path):
        """A multiscale layer hands over a list of levels, not one array."""
        image = np.zeros((256, 300), dtype=np.uint8)
        levels = [image, image[::2, ::2]]
        store = write_ome_zarr(tmp_path / 'multiscale.ome.zarr',
                               layer(levels, 'input'))
        path = ome_attrs(store)['multiscales'][0]['datasets'][0]['path']
        assert zarr.open_group(store, mode='r')[path].shape == image.shape

    def test_store_without_labels(self, tmp_path):
        store = write_ome_zarr(tmp_path / 'image_only.ome.zarr',
                               layer(np.zeros((32, 32), dtype=np.uint8), 'input'))
        assert 'multiscales' in ome_attrs(store)
        assert not (Path(store) / 'labels').exists()

    def test_writes_the_0_4_layout(self, tmp_path):
        """0.4 keeps the OME metadata at the top level of a zarr v2 store."""
        store = write_ome_zarr(
            tmp_path / 'v04.ome.zarr',
            layer(np.zeros((256, 256), dtype=np.uint8), 'input'),
            [layer(label_plane(), 'mito-prediction')],
            class_names=CLASS_NAMES, label_divisor=LABEL_DIVISOR, version='0.4')

        assert (Path(store) / '.zgroup').exists()
        root = dict(zarr.open_group(store, mode='r').attrs)
        assert 'multiscales' in root and 'ome' not in root
        labels = dict(zarr.open_group(Path(store) / 'labels', mode='r').attrs)
        assert labels['labels'] == ['mito-prediction']
        label = dict(zarr.open_group(Path(store) / 'labels' / 'mito-prediction',
                                     mode='r').attrs)
        assert {property['class-name']
                for property in label['image-label']['properties']} == {'mito', 'lipid'}

    def test_consolidated_metadata_lists_the_labels(self, store):
        """A reader using the consolidated metadata still finds the labels."""
        consolidated = json.loads((Path(store) / 'zarr.json').read_text())
        members = consolidated['consolidated_metadata']['metadata']
        assert 'labels' in members
        assert 'labels/mito-prediction' in members

    def test_attributes_hold_no_unserialisable_metadata(self, tmp_path):
        """Metadata arrives with numpy scalars and tuples in it, json does not."""
        metadata = common_metadata()
        metadata['Instrument']['Model'] = np.uint16(7)
        metadata['Image']['Plane'] = {'PositionX': np.float32(1.5), 'Shape': (2, 3)}
        store = write_ome_zarr(
            tmp_path / 'numpy.ome.zarr',
            layer(np.zeros((4, 256, 300), dtype=np.uint8), 'input'),
            common_metadata=metadata)
        kept = custom_attrs(store)['acquisition_metadata']
        assert kept['Instrument']['Model'] == 7
        assert kept['Image']['Plane'] == {'PositionX': pytest.approx(1.5),
                                          'Shape': [2, 3]}


class TestDims:
    def test_metadata_names_the_axes(self):
        """Sizes that reproduce the shape name the axes."""
        assert infer_dims((4, 256, 300), common_metadata()) == ('z', 'y', 'x')

    def test_metadata_that_disagrees_is_not_used(self):
        """A cropped or squeezed array is named by its shape, not by stale sizes."""
        assert infer_dims((128, 128), common_metadata()) == ('y', 'x')

    @pytest.mark.parametrize('shape, expected', [
        ((256, 300), ('y', 'x')),
        ((256, 300, 3), ('y', 'x', 'c')),
        ((16, 256, 300), ('z', 'y', 'x')),
        ((2, 16, 256, 300), ('c', 'z', 'y', 'x')),
        ((20, 16, 256, 300), ('t', 'z', 'y', 'x')),
        ((5, 2, 16, 256, 300), ('t', 'c', 'z', 'y', 'x')),
    ])
    def test_default_dims(self, shape, expected):
        assert default_dims(shape) == expected

    def test_default_dims_rejects_too_many_axes(self):
        with pytest.raises(ValueError):
            default_dims((2, 2, 2, 2, 2, 2))

    @pytest.mark.parametrize('label_ndim, image_dims, expected', [
        (3, ('c', 'z', 'y', 'x'), ('c',)),
        (3, ('t', 'c', 'y', 'x'), ('c',)),
        (2, ('t', 'c', 'y', 'x'), ('c', 't')),
        (3, ('z', 'y', 'x'), ()),
        (2, ('y', 'x'), ()),
    ])
    def test_dropped_dims(self, label_ndim, image_dims, expected):
        """A segmentation of a multi-channel image is a single volume."""
        assert dropped_dims(label_ndim, image_dims) == expected

    def test_channel_axis_is_written_before_the_spatial_axes(self, tmp_path):
        """An rgb layer arrives as y, x, c; OME-Zarr wants c first."""
        store = write_ome_zarr(
            tmp_path / 'rgb.ome.zarr',
            layer(np.zeros((256, 300, 3), dtype=np.uint8), 'input'))
        axes = ome_attrs(store)['multiscales'][0]['axes']
        assert [axis['name'] for axis in axes] == ['c', 'y', 'x']

    def test_singleton_axes_are_dropped(self, tmp_path):
        """A single plane is written as a plane, not as a volume of one."""
        store = write_ome_zarr(
            tmp_path / 'single.ome.zarr',
            layer(np.zeros((1, 256, 300), dtype=np.uint8), 'input'),
            [layer(np.zeros((1, 256, 300), dtype=np.uint32), 'mito-prediction')])
        axes = ome_attrs(store)['multiscales'][0]['axes']
        assert [axis['name'] for axis in axes] == ['y', 'x']

    def test_layer_scale_is_used_without_acquisition_metadata(self, tmp_path):
        store = write_ome_zarr(
            tmp_path / 'layer_scale.ome.zarr',
            layer(np.zeros((4, 64, 64), dtype=np.uint8), 'input',
                  scale=(0.2, 0.01, 0.01), translate=(1.0, 2.0, 3.0)))
        transformations = (ome_attrs(store)['multiscales'][0]['datasets'][0]
                           ['coordinateTransformations'])
        by_type = {transformation['type']: transformation
                   for transformation in transformations}
        assert by_type['scale']['scale'] == pytest.approx([0.2, 0.01, 0.01])
        assert by_type['translation']['translation'] == pytest.approx([1.0, 2.0, 3.0])

    def test_axes_without_a_physical_size_are_unitless(self, tmp_path):
        """An unknown pixel size must not be written as one micrometer."""
        store = write_ome_zarr(
            tmp_path / 'no_pixel_size.ome.zarr',
            layer(np.zeros((64, 64), dtype=np.uint8), 'input'))
        axes = ome_attrs(store)['multiscales'][0]['axes']
        assert [axis.get('unit') for axis in axes] == [None, None]

    def test_mismatched_layer_scale_is_ignored(self, tmp_path):
        """A scale that does not describe these axes must not scale one of them."""
        image = layer(np.zeros((4, 64, 64), dtype=np.uint8), 'input')
        image.scale = (1.0, 1.0)
        store = write_ome_zarr(tmp_path / 'bad_scale.ome.zarr', image)
        transformations = (ome_attrs(store)['multiscales'][0]['datasets'][0]
                           ['coordinateTransformations'])
        scale = next(transformation['scale'] for transformation in transformations
                     if transformation['type'] == 'scale')
        assert scale == pytest.approx([1.0, 1.0, 1.0])


class TestMetadataScale:
    def test_units_are_normalised_to_micrometer(self):
        scale = metadata_scale(common_metadata(), ('z', 'y', 'x'))
        assert scale == pytest.approx({'z': 0.05, 'y': 0.005, 'x': 0.005})

    def test_missing_pixel_sizes_are_left_out(self):
        metadata = common_metadata()
        del metadata['Image']['Pixels']['PhysicalSizeZ']
        assert set(metadata_scale(metadata, ('z', 'y', 'x'))) == {'y', 'x'}

    def test_time_increment_is_normalised_to_seconds(self):
        metadata = common_metadata()
        metadata['Image']['Pixels'].update(TimeIncrement=500,
                                           TimeIncrementUnit='ms')
        assert metadata_scale(metadata, ('t', 'y', 'x'))['t'] == pytest.approx(0.5)

    def test_metadata_without_pixels(self):
        assert metadata_scale({'Instrument': {}}, ('y', 'x')) == {}
        assert metadata_scale(None, ('y', 'x')) == {}


class TestPyramid:
    """The pyramid is ngff-zarr's own: these pin the behaviour we rely on."""

    @pytest.fixture()
    def small_chunks(self, monkeypatch):
        """Chunk small, so a small test image still gets a pyramid."""
        monkeypatch.setattr(parameters, 'ZARR_CHUNKS',
                            dict(parameters.ZARR_CHUNKS, x=64, y=64, z=4))

    def shapes(self, store, *group):
        zarr_group = zarr.open_group(Path(store).joinpath(*group), mode='r')
        return [zarr_group[dataset['path']].shape for dataset
                in ome_attrs(store, *group)['multiscales'][0]['datasets']]

    def test_large_image_is_halved_level_by_level(self, tmp_path, small_chunks):
        store = write_ome_zarr(tmp_path / 'pyramid.ome.zarr',
                               layer(np.zeros((512, 512), dtype=np.uint8), 'input'))
        assert self.shapes(store) == [(512, 512), (256, 256), (128, 128), (64, 64)]

    def test_small_image_gets_no_pyramid(self, tmp_path):
        """A single chunk of pixels has nothing to downsample."""
        store = write_ome_zarr(tmp_path / 'small.ome.zarr',
                               layer(np.zeros((64, 64), dtype=np.uint8), 'input'))
        assert self.shapes(store) == [(64, 64)]

    def test_thin_axis_of_a_volume_is_kept(self, tmp_path, small_chunks):
        """An anisotropic volume must not downsample its few sections away."""
        store = write_ome_zarr(tmp_path / 'anisotropic.ome.zarr',
                               layer(np.zeros((4, 512, 512), dtype=np.uint8), 'input'))
        # every level keeps the four sections; only y and x are halved
        assert {shape[0] for shape in self.shapes(store)} == {4}
        assert [shape[-1] for shape in self.shapes(store)] == [512, 256, 128, 64]

    def test_labels_are_downsampled_with_the_image(self, tmp_path, small_chunks):
        """The label pyramid has the levels the image pyramid has."""
        store = write_ome_zarr(
            tmp_path / 'both.ome.zarr',
            layer(np.zeros((512, 512), dtype=np.uint8), 'input'),
            [layer(label_plane((512, 512)), 'mito-prediction')])
        assert self.shapes(store, 'labels', 'mito-prediction') == self.shapes(store)


class TestImageLabelMetadata:
    def test_panoptic_labels_are_split_into_classes(self):
        image_label, summary = image_label_metadata(
            label_volume(), class_names=CLASS_NAMES, label_divisor=LABEL_DIVISOR,
            layer_name='mito-prediction')
        assert [property['class-id'] for property in image_label['properties']] == [1, 1, 2]
        assert summary['classes'] == {'1': 'mito', '2': 'lipid'}

    def test_unknown_class_id_is_named_after_the_id(self):
        labels = np.array([[7 * LABEL_DIVISOR + 1]], dtype=np.uint32)
        image_label, _ = image_label_metadata(
            labels, class_names=CLASS_NAMES, label_divisor=LABEL_DIVISOR)
        assert image_label['properties'][0]['class-name'] == 'class-7'

    def test_without_a_divisor_the_layer_name_is_the_class(self):
        labels = np.array([[0, 1, 2]], dtype=np.uint32)
        image_label, summary = image_label_metadata(labels, layer_name='mito-prediction')
        assert {property['class-name'] for property in image_label['properties']} == {'mito'}
        assert summary['classes'] == {'1': 'mito'}
        assert summary['label_divisor'] is None

    def test_background_is_not_a_label(self):
        image_label, summary = image_label_metadata(
            np.zeros((4, 4), dtype=np.uint32), layer_name='mito-prediction')
        assert 'properties' not in image_label
        assert summary['label_count'] == 0

    def test_many_labels_are_summarised_rather_than_listed(self, monkeypatch):
        """Per-instance properties and colours are pointless past a cap."""
        monkeypatch.setattr(parameters, 'MAX_LABEL_PROPERTIES', 5)
        labels = (np.arange(1, 21) + LABEL_DIVISOR).astype(np.uint32)
        image_label, summary = image_label_metadata(
            labels, class_names=CLASS_NAMES, label_divisor=LABEL_DIVISOR)
        assert 'properties' not in image_label
        assert 'colors' not in image_label
        assert summary['label_count'] == 20
        assert summary['classes'] == {'1': 'mito'}


class TestClassNameFromLayerName:
    @pytest.mark.parametrize('layer_name, expected', [
        ('mito-prediction', 'mito'),
        ('lipid-prediction', 'lipid'),
        ('cell_batch_segs', 'cell'),
        ('empanada_seg_2d', 'segmentation'),
        ('input-panoptic-stack-z', 'segmentation'),
        ('', 'segmentation'),
        (None, 'segmentation'),
    ])
    def test_class_name(self, layer_name, expected):
        assert class_name_from_layer_name(layer_name) == expected


class TestJsonable:
    def test_converts_what_json_cannot_hold(self):
        converted = jsonable({
            np.uint8(1): np.float32(0.5),
            'array': np.arange(3),
            'bytes': b'raw',
            'nested': {'tuple': (1, np.int64(2))},
            'none': None,
        })
        assert converted == {'1': pytest.approx(0.5), 'array': [0, 1, 2],
                             'bytes': 'raw', 'nested': {'tuple': [1, 2]},
                             'none': None}
        json.dumps(converted)

    def test_unknown_objects_become_their_string(self):
        assert jsonable(object) == str(object)
