#!/usr/bin/env python3
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
R=Path(__file__).resolve().parents[1]; A=R/'assets/generated'
bg=Image.open(A/'runtime_stage_0.png').convert('RGB').resize((320,160),Image.Resampling.NEAREST)
frame=Image.new('RGB',(320,200),(0,0,0)); frame.paste(bg,(0,18))
d=ImageDraw.Draw(frame)
# Sprite sheets are generated from the exact indexed asset source crops.
car=Image.open(A/'fiat500L_1971_white_8dir.png').convert('RGB').crop((0,0,48,40))
# Treat near-black panel background as transparent for preview.
mask=Image.new('L',car.size,255); ma=mask.load(); ca=car.load()
for y in range(car.height):
 for x in range(car.width):
  r,g,b=ca[x,y]
  if r+g+b<55: ma[x,y]=0
frame.paste(car,(136,115),mask)
sco=Image.open(A/'scooters_8bit.png').convert('RGB')
for box,pos in [((0,0,24,32),(205,75)),((24,0,48,32),(95,62)),((48,0,72,32),(240,112))]:
 s=sco.crop(box); m=Image.new('L',s.size,255); p=m.load(); q=s.load()
 for yy in range(s.height):
  for xx in range(s.width):
   rr,gg,bb=q[xx,yy]
   if rr+gg+bb<55:p[xx,yy]=0
 frame.paste(s,pos,m)
d.rectangle((0,0,319,17),fill=(0,0,0)); d.text((5,4),'SCORE 001250   BENZINA ||||||   BATTERIA |||||   SEGNI 1/5',fill=(255,238,170))
d.rectangle((0,178,319,199),fill=(0,0,0)); d.text((5,184),'MAN   A TURBO   B AUTO   CENTRO STORICO',fill=(220,245,255))
d.rectangle((35,145,285,172),fill=(0,0,0),outline=(20,220,255)); d.text((48,154),'vai cuonc cuonc',fill=(255,255,255))
frame.quantize(colors=128,method=Image.Quantize.MEDIANCUT).save(A/'screenshot.png',optimize=True)
print(A/'screenshot.png')
