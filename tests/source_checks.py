#!/usr/bin/env python3
from pathlib import Path
import re, sys
r=Path(__file__).resolve().parents[1]
g=(r/'src/game.c').read_text()
a=(r/'src/assets8.h').read_text()
required=['naprider_init','naprider_update','naprider_draw','prg32_sprite_draw_indexed','bits_per_pixel=8','L\'UOVO DI VIRGILIO','SOTTERRANEA','vai cuonc cuonc','ho sete','hai lasciato le luci accese','ah il freno a mano']
missing=[x for x in required if x not in g]
if missing: raise SystemExit('missing: '+', '.join(missing))
for banned in ['TESORO RECUPERATO','San Gennaro','vesuvio_init','development-c6']:
    if banned in g: raise SystemExit('obsolete gameplay/source token: '+banned)
mt=re.search(r'#define NR_TILE_COUNT (\d+)',a); assert mt
assets=(96*16*16)+(8*48*40)+(8*24*32)+(40*56)+(6*20*10)+128*2
if assets>56000: raise SystemExit(f'indexed assets too large: {assets}')
if not (r/'assets/source/naprider_visual_sheet.png').exists(): raise SystemExit('source visual sheet missing')
print(f'OK: 8-bpp assets ~{assets} bytes, {mt.group(1)} tile frames, mythology scope active')
