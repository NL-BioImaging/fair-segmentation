Implementation:
- (Realise as napari plugin, communicating with empanada-napari)
- Realise as napari script which runs empanada-napari, which is sufficient to capture empanada-napari plugin UI values

Workflow:
- Define input and output folder
- Read all files in input folder and convert to OME-Zarr (including acquisition metadata) - or do this @ export
- meta-tiff-loader napari loader: read tiff with metadata, convert to layer data + metadata dict
- Run napari plugin pointing to input folder (and output folder)
- Post- napari plugin:
  - Collect output into output folder if needed
  - Export make (and input image) to OME-Zarr file with label, including converted acq metadata
  - Create RO-Crate of all output, also pointing to input
  - Import & use integrated-metadata module for creating RO-Crate

Importing RO-Crate into OMERO
- https://forum.image.sc/t/ro-crate-and-omero/80610
- https://github.com/WU-BIMAC/W-IDM_OmeroImporter
