Implementation:
- (Realise as napari plugin, communicating with empanada-napari)
- Realise as napari script which runs empanada-napari, which is sufficient to capture empanada-napari plugin UI values

Workflow:
- Define input and output folder
- Read all files in input folder and convert to OME-Zarr (including acquisition metadata) - or do this @ export
- meta-tiff-reader napari reader: read tiff with metadata, convert to layer data + metadata dict
- Run napari plugin pointing to input folder (and output folder)
- Post- napari plugin:
  - Collect output into output folder if needed
  - Export make (and input image) to OME-Zarr file with label, including converted acq metadata
  - Create RO-Crate of all output, also pointing to input
  - Import & use integrated-metadata module for creating RO-Crate

Importing RO-Crate into OMERO
- https://forum.image.sc/t/ro-crate-and-omero/80610
- https://github.com/WU-BIMAC/W-IDM_OmeroImporter

OME-Zarr output (fair_segmentation.ome_zarr_output)
- One store per run holds the input pixels and the segmentation derived from them:

    <image>.ome.zarr/         multiscales, plus the converted acquisition metadata
                              and the widget values under the 'fair-segmentation' key
      labels/                 'labels': [<label name>]
        <label name>/         multiscales + 'image-label'

- Written with ngff-zarr (OME-Zarr 0.5, zarr v3, sharded), which has no notion
  of labelled images: the 'labels' listing and the 'image-label' metadata are
  merged into the group attributes and validated against the schemas ngff-zarr
  bundles. The levels are written flat ('0', '1', ...) rather than with
  ngff-zarr's own nested 'scale<n>/<image name>' paths: ome-zarr-py (so OMERO
  and napari) and ngff-zarr read either, but ome-zarr-models only resolves a
  dataset that is a direct child of the group.
- Label images are downsampled with itkwasm's label filter, so no level holds a
  label value that the full resolution level does not.
- The pyramid is ngff-zarr's own automatic one (scale_factors as a minimum
  length): it halves the spatial dimensions only, leaves the thin axis of an
  anisotropic volume alone, and stops at the chunk size. The chunk is therefore
  ZARR_CHUNK_XY (256), not the 1024 pixel inference tile: with a tile sized
  chunk an image of a few thousand pixels gets no overview level at all.
- Pixel sizes come from the common acquisition metadata (normalised to
  micrometer / second) and from the layer's own scale otherwise; an axis of
  unknown physical size is written without a unit rather than with a made up one.
- empanada encodes a panoptic segmentation as class * label_divisor + instance;
  'image-label.properties' gives every label value its class id and name, taken
  from the model config named in the inference widget, and
  'image-label.colors' gives every instance of a class the same colour.
- Both ome-zarr-py (reader.py, node.add(labels, visibility=False)) and
  napari-ome-zarr (ome_zarr_reader.py, "visible": False) open a labelled image
  hidden, and OME-Zarr has no visibility field for a label. A labelled image is
  a multiscale image as well, though, so the 'omero' rendering metadata applies:
  channels[0].active = true makes napari open the labels switched on
  (LABELS_VISIBLE). It must be written together with 'image-label.colors' -
  napari would otherwise hand the labels layer the omero channel colour as a
  continuous colormap, which raises. Above MAX_LABEL_PROPERTIES neither is
  written, so a segmentation with that many instances opens hidden.
