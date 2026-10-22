VERSION = 'v0.1.0'

# writing one image-label property entry per instance label is pointless past
# this many
MAX_LABEL_PROPERTIES = 10000
# RO-Crate packaging: the run is described as a Bilayers workflow, generated
# from the widget values. The container is the one the Dockerfile builds; its
# tag is the one the image was built with, read from IMAGE_TAG_ENV at run time
WORKFLOW_CONFIG_NAME = 'config.yaml'
# the values the run gave the widgets, by widget, which the crate records
PARAMETERS_FILE_NAME = 'parameters.yaml'
BILAYERS_DOCKER_IMAGE = {'org': 'ghcr.io/nl-bioimaging', 'name': 'empanada-napari-xpra',
                         'platform': 'linux/amd64'}
IMAGE_TAG_ENV = 'FAIR_SEGMENTATION_IMAGE_TAG'
BILAYERS_CLI_COMMAND = 'python run_fair.py'
BILAYERS_CITATIONS = [{
    'name': 'empanada-napari',
    'doi': '10.1083/jcb.202208005',
    'license': 'BSD-3-Clause',
    'description': 'Panoptic segmentation of organelles in volume electron microscopy',
}]
