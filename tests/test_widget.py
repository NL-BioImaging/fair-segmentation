import numpy as np

from fair_segmentation._widget import (
    FairWidget,
)


# capsys is a pytest fixture that captures stdout and stderr output streams
def test_example_q_widget(make_napari_viewer, capsys):
    # make viewer and add an image layer using our fixture
    viewer = make_napari_viewer()
    viewer.add_image(np.random.random((100, 100)))

    # create our widget, passing in the viewer
    my_widget = FairWidget(viewer)

    # call our widget method
    #my_widget._on_click()

    # read captured output and check that it's as we expected
    #captured = capsys.readouterr()
    #assert captured.out == 'napari has 1 layers\n'

    viewer.show(block=True)
