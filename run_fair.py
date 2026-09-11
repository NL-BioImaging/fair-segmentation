from imaging_metadata_converter import convert_metadata
from magicgui.widgets import TextEdit, LineEdit, FileEdit, ComboBox, CheckBox, SpinBox, FloatSpinBox
import napari
import os.path
from qtpy.QtWidgets import QAction, QWidget, QScrollArea
import sys

from fair_segmentation.ome_zarr_output import class_info_from_params, write_ome_zarr
from fair_segmentation.util import get_filetitle

READER_PLUGIN = 'napari-meta-tiff'
DEFAULT_OUTPUT_DIR = 'output'


def fair_output_function():
    params = {}
    for name, widget in viewer.window.dock_widgets.items():
        params[name] = extract_params(widget)

    print('All parameters:', params)

    output_dir = find_output_dir()
    print('output dir:', output_dir)

    inference_params = {}
    widget = find_widget(viewer.window.dock_widgets, ['2D Inference', '3D Inference'])
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

    store_path = os.path.join(output_dir, f'{store_name(image_layer)}.ome.zarr')
    # the widget values are the record of how the segmentation was produced,
    # so they travel with the pixels
    write_ome_zarr(store_path, image_layer, label_layers,
                   common_metadata=common_metadata, workflow_metadata=params,
                   class_names=class_names, label_divisor=label_divisor)
    print('written:', store_path)

    params['input_common_metadata'] = common_metadata
    params['output_ome_zarr'] = store_path
    return params


def find_output_dir():
    """Return the folder to write to, which the user set on the measure widget."""
    widget = find_widget(viewer.window.dock_widgets, ['Measure Labels'])
    if widget:
        save_dir = extract_params(widget).get('save_dir')
        if save_dir:
            return str(save_dir)
    return DEFAULT_OUTPUT_DIR


def find_label_layers(inference_params):
    """Return the label layers to write alongside the image.

    The 2D widget segments into a layer the user picks, so that one layer is
    the output. The 3D widget adds a layer per class of its own instead, so
    every label layer in the viewer is taken as output there.
    """
    output_layer = inference_params.get('output_layer')
    if output_layer is not None:
        return [output_layer]
    return [layer for layer in viewer.layers
            if isinstance(layer, napari.layers.Labels)]


def store_name(image_layer):
    """Name the store after the file the image was read from, or after the layer."""
    path = getattr(image_layer.source, 'path', None)
    return get_filetitle(path) if path else image_layer.name


def find_widget(widgets, widget_names):
    for widget_key, widget in widgets.items():
        for name in widget_names:
            if name in widget_key:
                return widget
    return None


def extract_params(widget):
    params = {}
    if isinstance(widget, QScrollArea):
        widget = widget.widget()
        if isinstance(widget, QWidget):
            widget = widget._magic_widget

    for arg in widget:
        if isinstance(arg, (TextEdit, LineEdit, FileEdit, ComboBox, CheckBox, SpinBox, FloatSpinBox)):
            params[arg.name] = arg.value
    return params


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
