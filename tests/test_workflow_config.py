"""Tests for describing a segmentation run as a Bilayers workflow."""

from importlib.metadata import version
import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from fair_segmentation import parameters
from fair_metadata_integration import create_ro_crate, parameter_entry, write_bilayers_config
from fair_metadata_integration.bilayers import unknown_value_names

from fair_segmentation.workflow_config import bilayers_config, run_values, software


WIDGET_NAME = '3D Inference (empanada-napari)'
MEASURE_WIDGET_NAME = 'Measure Labels (empanada-napari)'


def widget_params():
    """Values of the 3D inference widget, as run_fair extracts them."""
    return {
        'image_layer': SimpleNamespace(data=np.zeros((2, 4, 4)), name='input'),
        'model_config': 'MitoNet_v1_mini',
        'use_gpu': False,
        'downsampling': 1,
        'confidence_thr': 0.5,
        'min_size': 500,
        'maximum_objects_per_class': '10000',
        'inference_plane': 'xy',
        'store_dir': Path('no zarr storage'),
    }


def widget_choices():
    return {
        'model_config': ['MitoNet_v1', 'MitoNet_v1_mini'],
        'downsampling': [1, 2, 4],
        'inference_plane': ['xy', 'xz', 'yz'],
    }


def all_widget_params():
    """Values of every widget, as run_fair extracts them."""
    return {WIDGET_NAME: widget_params(),
            MEASURE_WIDGET_NAME: {'labels_layer': SimpleNamespace(data=np.zeros((2, 4, 4)), name='mito'),
                                  'save_dir': Path('output'), 'unset': None}}


@pytest.fixture()
def config():
    return bilayers_config(WIDGET_NAME, widget_params(), choices=widget_choices(),
                           other_widgets=all_widget_params())


def parameters_by_name(config):
    return {param['name']: param for param in config['parameters']}


class TestBilayersConfig:
    def test_layers_are_not_parameters(self, config):
        assert 'image_layer' not in parameters_by_name(config)
        assert [entry['name'] for entry in config['inputs']] == ['input_image']
        assert [entry['name'] for entry in config['outputs']] == ['segmentation']

    def test_values_become_defaults(self, config):
        params = parameters_by_name(config)
        assert params['confidence_thr']['default'] == 0.5
        assert params['min_size']['default'] == 500
        assert params['use_gpu']['default'] is False
        assert params['store_dir']['default'] == 'no zarr storage'

    def test_types(self, config):
        types = {name: param['type'] for name, param in parameters_by_name(config).items()}
        assert types == {
            'model_config': 'dropdown',
            'use_gpu': 'checkbox',
            'downsampling': 'dropdown',
            'confidence_thr': 'float',
            'min_size': 'integer',
            'maximum_objects_per_class': 'textbox',
            'inference_plane': 'dropdown',
            'store_dir': 'textbox',
        }

    def test_dropdown_options(self, config):
        downsampling = parameters_by_name(config)['downsampling']
        assert downsampling['options'] == [{'label': '1', 'value': 1},
                                           {'label': '2', 'value': 2},
                                           {'label': '4', 'value': 4}]
        assert downsampling['multiselect'] is False

    def test_checkbox_states_append_value(self):
        assert parameter_entry('use_gpu', True)['append_value'] is False

    def test_widgets_are_sections(self, config):
        assert {param['section_id'] for param in config['parameters']} == {'3D_Inference_(empanada-napari)'}
        assert [(entry['section_id'], entry['name'], entry['default']) for entry in config['display_only']] == [
            ('Measure_Labels_(empanada-napari)', 'save_dir', 'output')]

    def test_run_values_are_at_their_entries(self, config):
        values = run_values(all_widget_params())
        assert set(values['Measure_Labels_(empanada-napari)']) == {'save_dir'}
        assert unknown_value_names(config, values) == []

    def test_write_round_trips(self, tmp_path, config):
        path = write_bilayers_config(tmp_path / 'crate' / 'config.yaml', config)
        assert yaml.safe_load(Path(path).read_text(encoding='utf-8')) == config


class TestValidation:
    def test_biomero_schema_accepts_config(self, config):
        adapters = pytest.importorskip('biomero_schema.adapters')
        workflow = adapters.parse_descriptor(config)
        inputs = {param.id: param for param in workflow.inputs}
        assert inputs['input_image'].type == 'image'
        assert inputs['downsampling'].value_choices == [1, 2, 4]
        assert inputs['use_gpu'].type == 'boolean'
        assert [param.id for param in workflow.outputs] == ['segmentation']

    def test_invalid_config_is_refused(self, tmp_path, config):
        pytest.importorskip('biomero_schema.adapters')
        config['citations'] = []
        with pytest.raises(ValueError):
            write_bilayers_config(tmp_path / 'config.yaml', config)
        assert not (tmp_path / 'config.yaml').exists()


class TestRoCrate:
    def test_output_folder_is_the_crate(self, tmp_path, config):
        """The store and config are in the crate where they were written; the input is referenced."""
        output_dir = tmp_path / 'output'
        store = output_dir / 'run.ome.zarr'
        store.mkdir(parents=True)
        (store / 'zarr.json').write_text('{}')
        input_image = tmp_path / 'data' / 'run.tif'
        input_image.parent.mkdir()
        input_image.write_bytes(b'II*\x00')
        config_path = write_bilayers_config(output_dir / 'config.yaml', config)

        with warnings.catch_warnings():
            warnings.simplefilter('error')
            create_ro_crate(str(output_dir), str(config_path), [str(input_image)],
                            output_paths=[str(store)], parameters=run_values(all_widget_params()),
                            run_name='3D inference of run.tif', software=software())

        graph = json.loads((output_dir / 'ro-crate-metadata.json').read_text())['@graph']
        root = next(entity for entity in graph if entity['@id'] == './')
        assert root['mainEntity'] == {'@id': 'config.yaml'}
        ids = {entity['@id'] for entity in graph}
        assert {'run.ome.zarr/', input_image.resolve().as_uri()} <= ids
        assert not (output_dir / 'run.tif').exists()
        run = next(entity for entity in graph if entity['@id'] == '#run')
        assert run['name'] == '3D inference of run.tif'
        workflow = next(entity for entity in graph if entity['@id'] == 'config.yaml')
        assert workflow['isPartOf'] == {'@id': parameters.SOFTWARE['url']}


class TestImageTag:
    def test_tag_from_environment(self, monkeypatch):
        monkeypatch.setenv(parameters.IMAGE_TAG_ENV, '1.2.3')
        config = bilayers_config(WIDGET_NAME, widget_params())
        assert config['docker_image']['org'] == 'ghcr.io/nl-bioimaging'
        assert config['docker_image']['tag'] == '1.2.3'

    def test_tag_falls_back_to_package_version(self, monkeypatch):
        monkeypatch.delenv(parameters.IMAGE_TAG_ENV, raising=False)
        config = bilayers_config(WIDGET_NAME, widget_params())
        assert config['docker_image']['tag'] == version('fair-segmentation')
