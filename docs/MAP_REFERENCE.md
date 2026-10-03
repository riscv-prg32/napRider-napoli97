# Napoli map reference

The stage maps use the [Tuttocitta Napoli city atlas](http://img.tuttocitta.it/pdf/TUT_NAPOLI.pdf) as geographic guidance. The atlas is modern, so the game keeps stable street and landscape relationships and fictionalises vehicles, signs and atmosphere as 1997.

The 20x10 maps are gameplay abstractions, not street plans. They are written as text in `tools/generate_assets.py`:

- **Centro Storico**: dense tenement blocks along a broad east-west street, recalling the parallel decumani; Vesuvius shows above the roofs.
- **Posillipo**: the hillside road beside the seawall and the Gulf, after Via Posillipo; Vesuvius stands across the water.
- **Quartieri Spagnoli**: tall fronts, washing overhead and frequent crossings west of Via Toledo; no view out.
- **Vomero**: high ground, gardens after the Villa Floridiana and the mouth of the Galleria, at night under umbrella pines.
- **Parco Virgiliano**: the green headland, ruins and open water at sunset, with an island on the horizon.
- **Napoli Sotterranea**: the historic-centre axis as tuff corridors, arches and torches; a fictional below-ground interpretation.

Rows 0-2 are the far layer (sky, sea, distant roofs), rows 3-4 the district layer, row 5 the near pavement with lamps and pumps, rows 6-8 the three lanes and row 9 the far pavement. Every surface map has exactly one fragment in a lane; the underground map has none and has rubble instead.
