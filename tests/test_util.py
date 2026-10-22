"""Tests for the yaml helpers."""

from pathlib import Path

import pytest
import yaml

from fair_segmentation.util import plain_value, write_yaml


class TestPlainValue:
    @pytest.mark.parametrize('value', ['text', 3, 0.5, True, None])
    def test_plain_values_are_kept(self, value):
        assert plain_value(value) == value

    def test_a_file_pickers_path_becomes_text(self):
        assert plain_value(Path('out')) == 'out'


class TestWriteYaml:
    def test_hierarchy_and_order_are_kept(self, tmp_path):
        data = {'3D Inference': {'model_config': 'MitoNet_v1', 'confidence_thr': 0.5},
                'Measure Labels': {'save_dir': 'out'}}
        path = write_yaml(tmp_path / 'run' / 'parameters.yaml', data)

        text = Path(path).read_text(encoding='utf-8')
        assert yaml.safe_load(text) == data
        assert text.index('model_config') < text.index('confidence_thr') < text.index('Measure Labels')
