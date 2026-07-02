# Install your plugin in editable mode in your virtual environment.
# For example, you could do this by running pip install -e .
# in the root directory of your plugin’s repository.

from napari import Viewer, run


viewer = Viewer()

#dock_widget, plugin_widget = viewer.window.add_plugin_dock_widget('fair-segmentation')

run()
