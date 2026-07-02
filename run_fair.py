from qtpy.QtWidgets import QAction
import napari


# Initialize the napari viewer
viewer = napari.Viewer()

def fair_output_function():
    print('docked widgets:', viewer.window.dock_widgets)

# Create the action and connect it to your function
fair_output_action = QAction("FAIR output", viewer.window._qt_window)
fair_output_action.triggered.connect(fair_output_function)

# Add the action to the menu
viewer.window.plugins_menu.addAction(fair_output_action)

napari.run()
