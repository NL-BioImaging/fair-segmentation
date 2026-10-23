# Known issues

- [x] **Labels open hidden in napari** (by design in napari-ome-zarr; documented in the README) - opening an output `.ome.zarr` with napari-ome-zarr shows the image, but the
      labels layer is switched off (confirmed after f440977). ome-zarr-py's reader adds label images with
      `visibility=False` (`ome_zarr/reader.py`, `node.add(child_zarr, visibility=False)`), and an `omero` channel's
      `active` is combined with that (`active and node.visible`), so no metadata we write switches them on. `omero`
      on a label image also makes napari-ome-zarr pass `contrast_limits` to the labels layer, which raises, so label
      images get none. Options: an upstream change in ome-zarr-py (or napari-ome-zarr) to honour a visibility hint,
      or switching the labels on ourselves where fair-segmentation opens its own output.

      Checked with dummy stores (2026-10-23), written by ome-zarr-py 0.18 (`write_labels` twice) and by ngff-zarr 0.48
      (image with `to_ngff_zarr`, each label as its own multiscales under `labels/`, `image-label` and the `labels`
      list added by hand, since ngff-zarr has no labels writer):
      - napari-ome-zarr 0.10 no longer uses ome-zarr-py's reader. Its own `Label.metadata()` returns
        `"visible": False  # labels not visible initially`, so every label opens hidden whichever library wrote the
        store, and opening `labels/` or `labels/<name>` directly loads the parent image the same way. The layers are
        named `labels/labels/<name>`.
      - ome-zarr-py's `Reader` (used by older napari-ome-zarr) gives the label nodes `visible=False` too.
      - napari's built-in reader in the `napari` pixi env (no napari-ome-zarr installed there) cannot open the
        ome-zarr-py store ("No arrays found in zarr group"). It opens the ngff-zarr store as a single image with no labels.
      - ngff-zarr writes consolidated metadata at the root, so labels added afterwards are invisible to readers
        (zarr lists only `scale0`, `scale1`) until `zarr.consolidate_metadata` is run again.
      - No upstream issue on label visibility found in ome/napari-ome-zarr or ome/ome-zarr-py.
      So no metadata change on our side can switch the labels on. Setting `layer.visible = True` after opening, or an
      upstream change, are the only fixes.
