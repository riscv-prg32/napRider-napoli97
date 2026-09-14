# Game design

## Campaign

1. **Centro Storico** — first puzzle fragment; traffic and scooter tutorial.
2. **Posillipo** — faster coastal road and heavier traffic.
3. **Quartieri Spagnoli** — tighter visual corridor and aggressive scooter pressure.
4. **Vomero / Galleria** — tunnel atmosphere, headlights and battery become important.
5. **Parco Virgiliano** — myth clue reveals a route beneath the city.
6. **Napoli Sotterranea** — underground dungeon-like finale; reach the Egg of Virgil and choose whether to take it or leave it.

Each surface map stores one collectible fragment as a semantic byte cell. The player must drive over the fragment before leaving that district; otherwise the route loops. Five fragments reconstruct the Virgilian mosaic that opens Napoli Sotterranea. These pieces are game inventions, not historical artifacts.

## Car systems

Fuel, battery, lights, handbrake, manual/self-drive, turbo and the four car phrases are persistent systems. Petrol points exist to make route planning matter. AUTO lets the player hand steering to the car and focus on arcade gadgets.

## Track motion

Forward distance defines a horizontal track axis shared by the road, Fiat, scooters, projectiles and collectible collision. Map rows form three parallax bands: distant scenery moves at one eighth road speed, district scenery at one quarter, and the road at full camera speed. Up/down input changes road lane; right/left accelerates or brakes. Vehicle sprite headings reflect current lane movement rather than accumulated position.

## Tone

The atmosphere is affectionate, comic and mythological rather than violent. Scooter opponents are fictional arcade gangs. Gadgets cause temporary game-state disruption only.
