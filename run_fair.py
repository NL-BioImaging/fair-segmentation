from qtpy.QtWidgets import QAction, QWidget, QScrollArea
import napari


# Initialize the napari viewer
viewer = napari.Viewer()

def fair_output_function():
    for name, widget in viewer.window.dock_widgets.items():
        if 'empanada' in name:
            print('Found', name)
            if isinstance(widget, QScrollArea):
                widget = widget.widget()
                if isinstance(widget, QWidget):
                    widget = widget._magic_widget

            for arg in widget:
                print(arg.name, arg.value)

# Create the action and connect it to your function
fair_output_action = QAction("FAIR output", viewer.window._qt_window)
fair_output_action.triggered.connect(fair_output_function)

# Add the action to the menu
viewer.window.plugins_menu.addAction(fair_output_action)

napari.run()
