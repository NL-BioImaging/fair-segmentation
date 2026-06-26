# Integrated FAIR workflow metadata in BIOMERO

## Joost de Folter<sup>A</sup>, Pascal de Boer<sup>G</sup>, Ben Giepmans<sup>G</sup>, Ron Hoebe<sup>A</sup>, Przemek Krawczyk<sup>A</sup>, Torec Luik<sup>A</sup>, Maarten Paul<sup>L</sup>, Eric Reits<sup>A</sup>, Lennard Voortman<sup>L</sup>, Katy Wolstencroft<sup>A</sup>
### <sup>A</sup> Amsterdam UMC, <sup>G</sup> UMC Groningen, <sup>L</sup> Leiden UMC


*Intro*: Effective microscopy data management is crucial for keeping complex imaging datasets reproducible, interoperable, and reusable across workflows.

*Problem*: While REMBI (Recommended Metadata for Biological Images) metadata standards and OMERO advance FAIR data practices, gaps persist between acquisition and analysis due to fragmented metadata and limited support across microscopy types, hindering integration and reproducibility.

*Objective*: FAIR (Findable, Accessible, Interoperable and Reusable) approaches are essential for reproducibility, scalable analysis, and meeting publication and funding requirements, while also enabling cross-disciplinary data reuse, including integration with x-omics. We build on BIOMERO 2.0, which transforms OMERO into a FAIR-compliant, provenance-aware bioimaging platform.

*Solution*: Building on BIOMERO 2.0, this work introduces a FAIR workflow metadata layer linking data, analysis, and provenance into a machine-readable format, improving reproducibility, transparency, and workflow integration while reducing metadata burden.
By providing standardised metadata, this facilitates compatibility for key public image archives such as BioImage Archive.
Standardised metadata supports integration with leading public image repositories such as the BioImage Archive.

```mermaid
---
config:
  themeVariables:
    fontSize: 20px
  layout: elk
---
flowchart
 subgraph omero["OMERO"]
        data("fa:fa-image Data"):::blue
        metadata("fa:fa-list Metadata"):::gold
        rembi("REMBI/ISA metadata
• TTL
• CSV/XLS"):::red
        acq("Acquisition metadata
• LM: OME-XML
• EM: RO-Crate"):::red
  end
 subgraph output["Output"]
        data2("fa:fa-image Data"):::blue
        metadata2("fa:fa-list Metadata"):::gold
        rocrate("fa:fa-box RO-Crate")
  end
 subgraph xpra["Interactive interface"]
        napari["napari/empanada image analysis (segmentation &amp; annotation)"]
  end
 subgraph biomero["BIOMERO"]
 direction LR
        xpra
        schema("Workflow schema
• CWL
• Bilayers
• (Biaflows)"):::red
        workflow("Workflow output
• Image data
• Labels mask
• Measurements"):::red
  end
    biomero --> output
    omero --> biomero
    data --- metadata
    data2 --- metadata2
    output --> omero & archive("fa:fa-globe Public archive"):::red
    omero ~~~ biomero

    style rocrate stroke:#FF6D00,fill:#FFD600,stroke-width:4px
    style xpra fill:#ffddcc,stroke:#400000,color:#300000
    style napari fill:#ffeedd,stroke:#400000,color:#300000

    classDef blue fill:#e0f7fa,stroke:#006064,color:#006064
    classDef gold fill:#fff5e9,stroke:#5e4e20,color:#5e4e20
    classDef red fill:#fff3e0,stroke:#e65100,color:#e65100
    classDef gray fill:#eceff1,stroke:#37474f,color:#37474f
```

*Research Object Crate (RO-Crate)*: RO-Crate is a community effort to establish a lightweight approach to packaging research data with their metadata.

[researchobject.org/ro-crate](https://researchobject.org/ro-crate)

*BioImage Archive* is a free, publicly available online resource which stores and distributes biological images.

[ebi.ac.uk/bioimage-archive](https://ebi.ac.uk/bioimage-archive)

*Empanada* is a tool for panoptic segmentation of organelles in 2D and 3D.

[empanada.readthedocs.io](https://empanada.readthedocs.io)

Zenodo record for this poster: https://zenodo.org/records/20919503
