import numpy as np
from tifffile import TiffFile, xml2dict


def float2int_image(image, target_dtype=np.dtype(np.uint8)):
    source_dtype = image.dtype
    if source_dtype.kind not in ('i', 'u') and not target_dtype.kind == 'f':
        maxval = 2 ** (8 * target_dtype.itemsize) - 1
        return (image * maxval).astype(target_dtype)
    else:
        return image


def extract_tiff_olympus(filename):
    pixel_size = {}
    tiff = TiffFile(filename)
    n = len(tiff.pages)
    page1 = tiff.pages[n - 1]
    metadata = tags_to_dict(page1.tags)
    if 'OlympusSIS' in metadata:
        metadata.update(metadata.pop('OlympusSIS'))
        pixel_size['x'] = metadata.get('pixelsizex')
        pixel_size['y'] = metadata.get('pixelsizey')
    else:
        pixel_size['x'] = convert_rational_value(metadata.get('XResolution'))
        pixel_size['y'] = convert_rational_value(metadata.get('YResolution'))

    data = page1.asarray()

    return data, metadata, pixel_size


def metadata_to_dict(xml_metadata):
    metadata = xml2dict(xml_metadata)
    if 'OME' in metadata:
        metadata = metadata['OME']
    return metadata


def tags_to_dict(tags):
    tag_dict = {}
    for tag in tags.values():
        tag_dict[tag.name] = tag.value
    return tag_dict


def convert_rational_value(value):
    if value is not None and isinstance(value, tuple):
        if value[0] == value[1]:
            value = value[0]
        else:
            value = value[0] / value[1]
    return value


def norm_image_minmax(image):
    min_value = np.min(image)
    max_value = np.max(image)
    normimage = (image - min_value) / (max_value - min_value)
    normimage = normimage.clip(0, 1).astype(np.float32)
    return normimage


def norm_image_quantiles(image, quantile=0.99):
    min_value = np.quantile(image, 1 - quantile)
    max_value = np.quantile(image, quantile)
    normimage = (image - min_value) / (max_value - min_value)
    normimage = normimage.clip(0, 1).astype(np.float32)
    return normimage


def norm_image_variance2(image0):
    if len(image0.shape) == 3 and image0.shape[2] == 4:
        image, alpha = image0[..., :3], image0[..., 3]
    else:
        image, alpha = image0, None
    normimage = ((image - np.mean(image)) / np.std(image) + 1) / 2
    normimage = normimage.clip(0, 1).astype(np.float32)
    if alpha is not None:
        normimage = np.dstack([normimage, alpha])
    return normimage
