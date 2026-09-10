"""Call the napari-meta-tiff reader directly, without starting napari.

Fast iteration loop for reader development: no Qt, no plugin machinery, and
exceptions come out as real tracebacks instead of napari notification popups.

    python debug_reader.py <path-to-tiff>

Set a breakpoint in napari_meta_tiff/_reader.py and run this under the
debugger to step through the reader itself.
"""
import sys

from napari_meta_tiff._reader import napari_get_reader


def main(path):
    reader = napari_get_reader(path)
    if reader is None:
        print(f'reader declined: {path}')
        return 1

    for index, (data, add_kwargs, layer_type) in enumerate(reader(path)):
        print(f'--- layer {index} ({layer_type}) ---')
        print('name:', add_kwargs.get('name'))
        # multiscale layers arrive as a list of levels, highest resolution first
        levels = data if isinstance(data, list) else [data]
        for level, level_data in enumerate(levels):
            print(f'level {level}: shape {level_data.shape} dtype {level_data.dtype}')
        print('scale:', add_kwargs.get('scale'))
        print('metadata:', add_kwargs.get('metadata'))
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
