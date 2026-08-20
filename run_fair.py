from magicgui.widgets import TextEdit, LineEdit, FileEdit, ComboBox, CheckBox, SpinBox, FloatSpinBox
import napari
from qtpy.QtWidgets import QAction, QWidget, QScrollArea


def fair_output_function():
    params = {}
    for name, widget in viewer.window.dock_widgets.items():
        params[name] = extract_params(widget)

    print('All parameters:', params)

    widget = find_widget(viewer.window.dock_widgets, ['2D Inference', '3D Inference'])
    if widget:
        inference_params = extract_params(widget)
        if inference_params:
            input_path = inference_params.get('image_layer')
            print('input:', input_path)

    widget = find_widget(viewer.window.dock_widgets, ['Measure Labels'])
    if widget:
        measure_params = extract_params(widget)
        if measure_params:
            output_path = measure_params.get('save_dir')
            print('output:', output_path)

    return params


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

# Create the action and connect it to your function
fair_output_action = QAction('FAIR output', viewer.window._qt_window)
fair_output_action.triggered.connect(fair_output_function)

# Add the action to the menu
viewer.window.plugins_menu.addAction(fair_output_action)

napari.run()
