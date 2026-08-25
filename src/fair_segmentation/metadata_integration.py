import os.path
from rocrate.model import ContextEntity

from fair_segmentation.zarr_extension import ZarrCrate


def create_ro_crate(dest_path, workflow_schema_filename, input_path, output_paths=[]):
    crate = ZarrCrate()

    for image_path in output_paths:
        rel_path = os.path.relpath(image_path, dest_path)
        output_entity = crate.add_dataset(dest_path=rel_path)

    input_entity = crate.add_dataset(dest_path=os.path.basename(input_path.rstrip('\\/')))

    workflow = crate.add_workflow(dest_path=os.path.basename(workflow_schema_filename))
    workflow['input'] = input_entity
    workflow['output'] = output_entity

    crate.write(dest_path)
    return crate
