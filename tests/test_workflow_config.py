"""Tests for describing a segmentation run as a Bilayers workflow."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from fair_segmentation.workflow_config import bilayers_config, parameter_entry, write_bilayers_config


WIDGET_NAME = '3D Inference (empanada-napari)'


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


@pytest.fixture()
def config():
    return bilayers_config(WIDGET_NAME, widget_params(), choices=widget_choices())


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
    def test_crate_holds_config_store_and_input(self, tmp_path, config):
        from fair_metadata_integration import create_ro_crate

        crate_dir = tmp_path / 'run'
        store = crate_dir / 'run.ome.zarr'
        store.mkdir(parents=True)
        (store / 'zarr.json').write_text('{}')
        input_image = tmp_path / 'run.tif'
        input_image.write_bytes(b'')
        config_path = write_bilayers_config(crate_dir / 'config.yaml', config)

        create_ro_crate(str(crate_dir), str(config_path), str(input_image),
                        output_paths=[str(store)])

        graph = json.loads((crate_dir / 'ro-crate-metadata.json').read_text())['@graph']
        root = next(entity for entity in graph if entity['@id'] == './')
        assert root['mainEntity'] == {'@id': 'config.yaml'}
        ids = {entity['@id'] for entity in graph}
        assert {'run.ome.zarr/', 'run.tif'} <= ids
        assert (crate_dir / 'run.tif').is_file()
