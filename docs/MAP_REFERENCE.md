# Napoli map reference

The semantic stage maps use the [Tuttocitta Napoli city atlas](http://img.tuttocitta.it/pdf/TUT_NAPOLI.pdf) as geographic guidance. The atlas is a modern reference, so the game uses stable street and landscape relationships while keeping vehicles, signs, street furniture and atmosphere fictionalized as 1997.

The 20x10 maps are gameplay abstractions rather than copied street plans:

- Centro Storico uses dense blocks around a broad east-west route, recalling the parallel historic-center axes.
- Posillipo follows a hillside road beside the seawall and Gulf of Naples, based on the Via Posillipo and Discesa Coroglio coastline.
- Quartieri Spagnoli uses tight blocks and frequent crossings west of Via Toledo.
- Vomero mixes winding high-ground roads, plazas and garden areas, informed by the hill plan and Villa Floridiana area.
- Parco Virgiliano is a green headland bordered by a coastal edge and open water.
- Napoli Sotterranea mirrors the historic-center axis as masonry corridors and chambers; it is a fictional below-ground interpretation.

Every stored map byte is a semantic cell. Codes distinguish buildings, road surface, road edges, crossings, sea, seawall, park, plaza and underground wall. District-specific tile frames render those codes without changing their meaning.
