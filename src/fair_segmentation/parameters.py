VERSION = 'v0.1.0'

TILE_SIZE = 1024

ZARR_CHUNK_SIZE = TILE_SIZE
ZARR_SHARD_MULTIPLIER = 10

# OME-Zarr output
NGFF_VERSION = '0.5'
# chunking per dimension; the non-spatial dimensions stay single-plane so a
# viewer can pull one channel / timepoint without reading its neighbours.
# Smaller than the inference tile on purpose: ngff-zarr stops downsampling a
# dimension at its chunk size, so a tile sized chunk would leave an image of a
# few thousand pixels without any overview level at all
ZARR_CHUNK_XY = 256
ZARR_CHUNKS = {'x': ZARR_CHUNK_XY, 'y': ZARR_CHUNK_XY, 'z': 64, 'c': 1, 't': 1}
# ngff-zarr keeps halving the spatial dimensions until a level holds fewer than
# twice this many pixels, leaving the thin axis of an anisotropic volume alone
# and never downsampling a dimension below its chunk size
ZARR_MULTISCALE_MIN_LENGTH = 128
# group attribute key holding metadata that is ours rather than OME-Zarr's
CUSTOM_METADATA_KEY = 'fair-segmentation'
# writing one property entry per instance label is pointless past this many;
# the class summary in the custom attributes covers the whole label image.
# Colours are written per label value too, so this caps them as well, and with
# them the request to open the labels switched on
MAX_LABEL_PROPERTIES = 10000
# ask a viewer to open the label layers switched on: readers hide a labelled
# image by default, which for a segmentation of one image is not what we want
LABELS_VISIBLE = True
