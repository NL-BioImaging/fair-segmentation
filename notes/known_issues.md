# Known issues

- [ ] **Labels open hidden in napari** - opening an output `.ome.zarr` with napari-ome-zarr shows the image, but the
      labels layer is switched off (confirmed after f440977). ome-zarr-py's reader adds label images with
      `visibility=False` (`ome_zarr/reader.py`, `node.add(child_zarr, visibility=False)`), and an `omero` channel's
      `active` is combined with that (`active and node.visible`), so no metadata we write switches them on. `omero`
      on a label image also makes napari-ome-zarr pass `contrast_limits` to the labels layer, which raises, so label
      images get none. Options: an upstream change in ome-zarr-py (or napari-ome-zarr) to honour a visibility hint,
      or switching the labels on ourselves where fair-segmentation opens its own output.
