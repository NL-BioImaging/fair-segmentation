Implementation options:
- napari plugin, communicating with empanada-napari
- napari script which runs empanada-napari, which is sufficient to capture empanada-napari plugin UI values
- empanada-napari plugin extension module, better integrating

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
- One store per run holds the image and the segmentation derived from it,
  always written from the layers, so it holds what the viewer showed:

    \<image\>.ome.zarr/           multiscales ('ome' is all zarr.json holds)
      acquisition-metadata.yaml  imaging-metadata-converter output, without SourceMap
      ro-crate-metadata.json     describes the store; links the yaml file, which
                                 conformsTo the converter's LinkML imaging model
      labels/                    'labels': [<label name>]
        <label name>/            multiscales + 'image-label'

- The acquisition metadata is kept with the pixels as biomero-converter keeps
  it (same file name, same link to the model), without depending on it.
- The run's widget values go to parameters.yaml in the output folder, by
  widget, which the top-level crate records (create_ro_crate(parameters=...)).
- Written with ome-zarr-py (OME-Zarr 0.5, zarr v3): write_image for the image,
  write_labels for every label layer, which also writes the 'labels' listing
  and 'image-label' (with the class of every label value as properties).
  ome-zarr-py leaves the version out of the 'labels' group, so it is added.
- Axes, pixel sizes and units are the layer's own, as napari-meta-tiff set them
  from the tiff (axis_labels, scale, units); a label layer without axis labels
  takes the trailing axes of the image. The layer's translate (stage position)
  is not written: ome-zarr-py takes a scale only.
- No consolidated metadata: it is not part of the zarr v3 specification.
- empanada encodes a panoptic segmentation as class * label_divisor + instance;
  'image-label.properties' gives every label value its class id and name, taken
  from the model config named in the inference widget.
- Labels open hidden in napari: ome-zarr-py's reader adds label images with
  visibility=False, and an 'omero' channel's 'active' is combined with that, so
  no metadata switches them on. 'omero' on a label image also makes
  napari-ome-zarr pass contrast_limits to the labels layer, which raises, so
  label images get none.
