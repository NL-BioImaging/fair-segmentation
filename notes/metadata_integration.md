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
  - Import & use fair-metadata-integration (FMI) for creating RO-Crate

RO-Crate packaging, with fair-metadata-integration (>= 0.9.1)
- Everything generic lives in FMI; fair-segmentation keeps what is specific to
  napari, empanada and its container:
  - FMI: create_ro_crate (the run's crate), create_zarr_ro_crate (the store's
    crate), bilayers_config / image_entry / display_entry / bilayers_format /
    write_bilayers_config (the generated Bilayers config), write_parameters,
    write_yaml, plain_value, WORKFLOW_CONFIG_NAME, PARAMETERS_FILE_NAME.
  - fair-segmentation: reading the widgets (run_fair), leaving out the layers
    (workflow_config.is_layer), the empanada input/output entries, citation,
    Docker image and command (workflow_config.bilayers_config, parameters), the
    container tag (workflow_config.image_tag), and the imaging model schema the
    acquisition metadata conforms to (ome_zarr_output.model_schema).
- The output folder is the run's crate; the store, config.yaml and
  parameters.yaml are written straight into it, so the crate does not copy
  them. The input image is referenced by its file URI.
- OME-Zarr stores conform to the OME-NGFF version they state (conformsTo
  https://ngff.openmicroscopy.org/0.5/), in both crates.

Importing RO-Crate into OMERO
- https://forum.image.sc/t/ro-crate-and-omero/80610
- https://github.com/WU-BIMAC/W-IDM_OmeroImporter

OME-Zarr output (fair_segmentation.ome_zarr_output)
- One store per run holds the image and the segmentation derived from it,
  always written from the layers, so it holds what the viewer showed:

    \<image\>.ome.zarr/           multiscales ('ome' is all zarr.json holds)
      acquisition-metadata.yaml  imaging-metadata-converter output, without SourceMap
      ro-crate-metadata.json     FMI's create_zarr_ro_crate: describes the store
                                 (Zarr, conformsTo OME-NGFF 0.5); links the yaml
                                 file, which conformsTo the converter's LinkML
                                 imaging model
      labels/                    'labels': [<label name>]
        <label name>/            multiscales + 'image-label'

- The acquisition metadata is kept with the pixels as biomero-converter keeps
  it (same file name, same link to the model), without depending on it.
- The run's widget values go to parameters.yaml in the output folder, by
  widget (FMI's write_parameters), which the top-level crate records
  (create_ro_crate(parameters=...)). Every widget is a section of config.yaml
  (section_id: its name as a file name), so FMI finds each value at its entry:
  the inference widget's values are parameters, the other widgets' values
  display-only entries (workflow_config.run_values / bilayers_config).
- The run's crate names fair-segmentation (version: the image tag) as the
  software the workflow is part of, and names the run after the widget and
  the input file. Start and end times are not known, so not given.
- The store's crate is based on the input image (isBasedOn), with its
  acquisition (#acquisition: instrument and time from the converted
  metadata), its derivation (#derivation: segmentation by empanada-napari,
  with its installed version) and the number of objects of each class as
  measurements (variableMeasured).
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
