# Game design

## Campaign

1. **Centro Storico** — afternoon among the tenements; two riders; the first fragment.
2. **Posillipo** — the coast road above the Gulf, Vesuvius across the water; the first petrol pump.
3. **Quartieri Spagnoli** — narrow and busy; from here some riders come up from behind.
4. **Vomero** — night; gardens and the Galleria. Without headlights the road is almost black.
5. **Parco Virgiliano** — sunset over the headland ruins; the last fragment opens the way down.
6. **Napoli Sotterranea** — tuff corridors, torches and rubble; no riders. The Egg of Virgil waits at the end.

Each surface district hides one fragment in a road lane. It is shown every other map width, so there are four chances per pass; a district left without its fragment goes round again. The fragments are game inventions, not historical artefacts.

## Car systems

- **Speed**: RIGHT accelerates to cruising speed, LEFT brakes, releasing coasts. Turbo (A) takes a quarter of the turbo bar and recharges with time.
- **Fuel**: burns with distance, twice as fast under turbo. Pumps on the pavement refill it from the top lane. Collisions spill some. An empty tank ends the run.
- **Lights and battery**: SELECT+B. Needed in Vomero and underground; they drain the battery, which recharges while driving unlit. A flat battery switches them off.
- **Handbrake**: SELECT. Stops the car and makes lane changes faster.
- **Self-drive**: B. Holds a steady speed in the top lane, dodges riders and rubble, and leaves the gadgets to the player. It refuels at pumps but does not fetch fragments.
- **Gadgets** (self-drive, A): rauti fly ahead; grasso and chiodi stay on the road behind. A rider who meets one is stopped for a while. They cause temporary game-state disruption only.

## Riders

Blockers ride slower than the car and change lane now and then. Chasers appear from the third district: they arrive from behind, steer for the car's lane and slow down once in front. A collision costs fuel and two thirds of the speed, shakes the screen and leaves the car blinking and untouchable for a second and a half.

## Motion

World distance is kept in sixteenths of a pixel. The road scrolls at full speed, the district layer at a quarter and the far layer at an eighth. The simulation advances in 33 ms steps driven by the firmware clock.

## Scoring

Fragment 750, district 1500 plus a fuel bonus, rider stopped 100, pump 50, turbo 15. Taking the Egg 5000; leaving it 7500.

## Tone

Affectionate, comic and mythological rather than violent. The scooter gangs are fictional arcade opponents.
