from fair_metadata_integration import create_ro_crate
from imaging_metadata_converter import convert_metadata
from magicgui.widgets import TextEdit, LineEdit, FileEdit, ComboBox, CheckBox, SpinBox, FloatSpinBox
import napari
import os.path
from qtpy.QtWidgets import QAction, QWidget, QScrollArea
import re
import sys

from fair_segmentation import parameters
from fair_segmentation.ome_zarr_output import class_info_from_params, write_ome_zarr
from fair_segmentation.util import get_filetitle, plain_value, write_yaml
from fair_segmentation.workflow_config import bilayers_config, is_layer, write_bilayers_config

READER_PLUGIN = 'napari-meta-tiff'
DEFAULT_OUTPUT_DIR = 'output'
# the layers the 2D widget adds its result to, when not 'Output to layer'
SLICE_RESULT_LAYER = 'empanada_seg_2d'
BATCH_RESULT_SUFFIX = '_batch_segs'


def fair_output_function():
    params = {}
    for name, widget in viewer.window.dock_widgets.items():
        params[name] = extract_params(widget)

    print('All parameters:', params)

    output_dir = find_output_dir()
    print('output dir:', output_dir)

    inference_params = {}
    widget_key, widget = find_widget(viewer.window.dock_widgets, ['2D Inference', '3D Inference'])
    if widget:
        inference_params = extract_params(widget)

    image_layer = inference_params.get('image_layer')
    if image_layer is None:
        print('no input image layer selected; nothing to write')
        return params

    # The reader hands us vendor specific acquisition metadata; map it
    # onto the common model so the FAIR output is instrument agnostic.
    common_metadata = convert_metadata(image_layer.metadata)
    print('common metadata', common_metadata)

    label_layers = find_label_layers(inference_params)
    print('labels:', [layer.name for layer in label_layers])

    # the model states which class each label value belongs to
    class_names, label_divisor = class_info_from_params(inference_params)

    # the output folder is the crate: the store, the workflow config and the
    # parameter values are written straight into it, so the crate does not
    # copy them; the acquisition metadata travels with the pixels
    store_path = os.path.join(output_dir, f'{store_name(image_layer)}.ome.zarr')
    write_ome_zarr(store_path, image_layer, label_layers,
                   acquisition_metadata=common_metadata,
                   class_names=class_names, label_divisor=label_divisor)
    print('written:', store_path)

    params['input_common_metadata'] = common_metadata
    params['output_ome_zarr'] = store_path

    input_path = getattr(image_layer.source, 'path', None)
    if not input_path:
        print('input image was not read from a file; no RO-Crate written')
        return params

    config = bilayers_config(widget_key, inference_params,
                             choices=extract_choices(widget),
                             input_format=image_format(input_path),
                             depth=image_layer.ndim >= 3)
    config_path = write_bilayers_config(
        os.path.join(output_dir, parameters.WORKFLOW_CONFIG_NAME), config)
    # the values of every widget, by widget: the layers are the run's data, not values
    run_parameters = {name: {key: plain_value(value) for key, value in values.items() if not is_layer(value)}
                      for name, values in params.items()}
    parameters_path = write_yaml(
        os.path.join(output_dir, parameters.PARAMETERS_FILE_NAME), run_parameters)
    create_ro_crate(output_dir, config_path, input_path, output_paths=[store_path],
                    parameters=parameters_path)
    print('packaged:', output_dir)

    params['output_ro_crate'] = output_dir
    return params


def image_format(path):
    """Return the Bilayers format name of an image file."""
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    return 'tiff' if ext == 'tif' else ext


def find_output_dir():
    """Return the folder to write to, which the user set on the measure widget."""
    _, widget = find_widget(viewer.window.dock_widgets, ['Measure Labels'])
    if widget:
        save_dir = extract_params(widget).get('save_dir')
        if save_dir:
            return str(save_dir)
    return DEFAULT_OUTPUT_DIR


def find_label_layers(inference_params):
    """Return the label layers to write alongside the image.

    The 2D widget segments into the layer the user picks when 'Output to layer'
    is on; otherwise it adds a result layer of its own, of which the newest is
    the output. The 3D widget adds a layer per class of its own instead, so
    every label layer in the viewer is taken as output there.
    """
    labels_layers = [layer for layer in viewer.layers
                     if isinstance(layer, napari.layers.Labels)]
    if 'output_to_layer' not in inference_params:
        return labels_layers
    if inference_params['output_to_layer']:
        output_layer = inference_params.get('output_layer')
        return [output_layer] if output_layer is not None else []
    image_layer = inference_params.get('image_layer')
    result_names = [SLICE_RESULT_LAYER]
    if image_layer is not None:
        result_names.append(f'{image_layer.name}{BATCH_RESULT_SUFFIX}')
    results = [layer for layer in labels_layers
               if base_layer_name(layer.name) in result_names]
    return results[-1:]


def base_layer_name(name):
    """Return a layer name without the ' [n]' napari appends to a repeated name."""
    return re.sub(r' \[\d+\]$', '', name)


def store_name(image_layer):
    """Name the store after the file the image was read from, or after the layer."""
    path = getattr(image_layer.source, 'path', None)
    if not path:
        return image_layer.name
    # an OME-Zarr or OME-TIFF input keeps no '.ome' of its own in the name
    return re.sub(r'\.ome$', '', get_filetitle(path.rstrip('\\/')))


def find_widget(widgets, widget_names):
    for widget_key, widget in widgets.items():
        for name in widget_names:
            if name in widget_key:
                return widget_key, widget
    return None, None


def magic_widget(widget):
    if isinstance(widget, QScrollArea):
        widget = widget.widget()
        if isinstance(widget, QWidget):
            widget = widget._magic_widget
    return widget


def extract_params(widget):
    params = {}
    for arg in magic_widget(widget):
        if isinstance(arg, (TextEdit, LineEdit, FileEdit, ComboBox, CheckBox, SpinBox, FloatSpinBox)):
            params[arg.name] = arg.value
    return params


def extract_choices(widget):
    """Return the values each drop-down of the widget offers."""
    return {arg.name: list(arg.choices) for arg in magic_widget(widget)
            if isinstance(arg, ComboBox)}


# Initialize the napari viewer
viewer = napari.Viewer()

# Open any files given on the command line, forcing our own tiff reader.
# Several plugins claim *.tif, so name the plugin explicitly instead of
# relying on napari's reader-choice dialog.
for path in sys.argv[1:]:
    viewer.open(path, plugin=READER_PLUGIN)

# Create the action and connect it to your function
fair_output_action = QAction('Package output', viewer.window._qt_window)
fair_output_action.triggered.connect(fair_output_function)

# Add the action to the menu
viewer.window.plugins_menu.addAction(fair_output_action)

napari.run()
