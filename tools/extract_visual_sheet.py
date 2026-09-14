#!/usr/bin/env python3
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'assets/source/naprider_visual_sheet.png'
OUT = ROOT / 'assets/generated'
HDR = ROOT / 'src/assets8.h'
OUT.mkdir(parents=True, exist_ok=True)
img = Image.open(SRC).convert('RGB')

# Crops intentionally follow the approved 1536x1024 visual sheet.
SCENES = [
    ('centro_storico', (459, 30, 1027, 320)),
    ('posillipo',      (1027, 30, 1536, 320)),
    ('quartieri',      (0, 410, 458, 625)),
    ('vomero',         (459, 410, 1027, 625)),
    ('virgiliano',     (1027, 410, 1536, 625)),
    ('sotterranea',    (0, 705, 490, 925)),
]

scene_imgs=[]
for name,box in SCENES:
    sc=img.crop(box).resize((320,160),Image.Resampling.LANCZOS)
    sc.save(OUT/f'stage_{name}.png')
    scene_imgs.append(sc)

# Global 128-color palette derived from the approved sheet. Index 0 is reserved
# for sprite transparency; opaque scenery uses indices 1..127.
thumb=img.resize((768,512),Image.Resampling.BILINEAR).quantize(colors=127, method=Image.Quantize.MEDIANCUT)
pal=thumb.getpalette()[:127*3]
colors=[(0,0,0)] + [tuple(pal[i:i+3]) for i in range(0,len(pal),3)]
colors=colors[:128]
pal_arr=np.array(colors,dtype=np.int16)

def rgb565(c):
    r,g,b=map(int,c); return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

def map_rgb(arr, transparent=False):
    a=np.asarray(arr.convert('RGB'),dtype=np.int16)
    flat=a.reshape(-1,3)
    # chunked nearest palette to cap memory
    out=np.empty(len(flat),dtype=np.uint8)
    start=1 if transparent else 1
    candidates=pal_arr[start:]
    for i in range(0,len(flat),4096):
        q=flat[i:i+4096].astype(np.int32)
        c32=candidates.astype(np.int32)
        d=((q[:,None,:]-c32[None,:,:])**2).sum(axis=2)
        out[i:i+len(q)]=d.argmin(axis=1).astype(np.uint8)+start
    if transparent:
        # Remove dark panel pixels and colors connected to the crop border.
        # This suppresses the blue/brown scene residue around vehicle silhouettes.
        lum=flat.sum(axis=1)
        dark=(lum<55) & (flat.max(axis=1)<35)
        border=np.concatenate((a[0],a[-1],a[:,0],a[:,-1])).astype(np.int32)
        border=np.unique((border//16)*16,axis=0)
        near_border=np.zeros(len(flat),dtype=bool)
        for i in range(0,len(flat),4096):
            q=flat[i:i+4096].astype(np.int32)
            near_border[i:i+len(q)]=(((q[:,None,:]-border[None,:,:])**2).sum(axis=2).min(axis=1)<18**2)
        out[dark|near_border]=0
    return out.reshape(a.shape[:2])

# Semantic byte maps describe a stylized 1997 Naples rather than shuffling
# arbitrary photographic fragments. Rows form far, district and road layers;
# the runtime scrolls each layer horizontally at a different speed.
T=16
C_BUILDING_A,C_BUILDING_B,C_ROAD,C_ROAD_LEFT,C_ROAD_RIGHT,C_CROSS,C_SEA,C_SEAWALL,C_PARK,C_PLAZA,C_WALL,C_PIECE=range(12)
CODE_COUNT=12
STAGE_COLORS=[
    ((139,91,55),(190,141,78)), ((224,201,151),(157,116,74)),
    ((174,102,56),(213,151,82)), ((150,127,97),(198,176,129)),
    ((178,142,88),(213,184,119)), ((77,62,49),(125,91,54)),
]

def semantic_tile(stage,code):
    a,b=STAGE_COLORS[stage]; im=Image.new('RGB',(T,T),a); d=ImageDraw.Draw(im)
    if code in (C_BUILDING_A,C_BUILDING_B):
        roof=b if code==C_BUILDING_A else a; wall=a if code==C_BUILDING_A else b
        d.rectangle((0,0,15,15),fill=wall); d.polygon(((0,5),(8,0),(15,4),(7,9)),fill=roof)
        d.line((0,5,7,10,15,5),fill=(70,48,35)); d.rectangle((4,10,6,13),fill=(30,45,50)); d.rectangle((10,8,12,11),fill=(225,185,75))
    elif code in (C_ROAD,C_CROSS,C_PIECE):
        d.rectangle((0,0,15,15),fill=(47,51,53)); d.line((2,8,10,8),fill=(215,190,116))
        if code==C_CROSS:
            for x in (1,5,9,13): d.rectangle((x,0,x+1,15),fill=(205,205,190))
        if code==C_PIECE:
            d.rectangle((5,5,11,11),fill=(247,194,45)); d.rectangle((3,7,5,9),fill=(247,194,45)); d.rectangle((7,3,9,5),fill=(247,194,45)); d.point((9,11),fill=(47,51,53))
    elif code==C_ROAD_LEFT:
        d.rectangle((0,8,15,15),fill=(47,51,53)); d.line((0,7,15,7),fill=(220,204,164),width=2)
    elif code==C_ROAD_RIGHT:
        d.rectangle((0,0,15,10),fill=(47,51,53)); d.line((0,10,15,10),fill=(220,204,164),width=2)
    elif code==C_SEA:
        d.rectangle((0,0,15,15),fill=(24,92,128))
        for y in (3,8,13): d.line((0,y,5,y-1,10,y,15,y-1),fill=(75,169,190))
    elif code==C_SEAWALL:
        d.rectangle((0,0,15,7),fill=(24,92,128)); d.rectangle((0,8,15,15),fill=(174,155,119)); d.line((0,8,15,8),fill=(235,220,180),width=2)
    elif code==C_PARK:
        d.rectangle((0,0,15,15),fill=(44,93,55)); d.ellipse((1,1,9,10),fill=(28,119,63)); d.ellipse((8,4,15,14),fill=(60,135,67)); d.line((0,15,15,0),fill=(188,157,104),width=2)
    elif code==C_PLAZA:
        d.rectangle((0,0,15,15),fill=(177,155,118))
        for q in range(0,16,4): d.line((q,0,q,15),fill=(130,111,87)); d.line((0,q,15,q),fill=(130,111,87))
    else:
        d.rectangle((0,0,15,15),fill=(58,48,42))
        for y in range(0,16,4): d.line((0,y,15,y),fill=(112,80,52)); d.line(((y//4%2)*4,y,(y//4%2)*4,y+3),fill=(112,80,52))
    return im

maps=np.zeros((6,10,20),dtype=np.uint8)
for stage in range(6):
    for y in range(10):
        for x in range(20):
            code=C_BUILDING_A if (x+y)%2 else C_BUILDING_B
            # Rows 0..2 are the far layer; 3..5 are district scenery.
            if stage==1:
                if y<=2: code=C_SEA
                elif y==3: code=C_SEAWALL
                elif y==4 and x%7==0: code=C_PARK
            elif stage==2:
                if y==4 and x%4 in (0,1): code=C_PLAZA
            elif stage==3:
                if y<=2 or (y<=4 and 7<=x<=12): code=C_PARK if (x+y)%3 else C_PLAZA
            elif stage==4:
                code=C_SEA if y<=1 else C_PARK
                if y==2: code=C_SEAWALL
            elif stage==5:
                code=C_WALL if (x+y)%3 else C_PLAZA
            # A continuous horizontal roadway occupies the foreground.
            cross_every=(6,10,4,8,10,6)[stage]
            if y==5: code=C_ROAD_LEFT
            elif 6<=y<=8: code=C_CROSS if x%cross_every in (0,1) else C_ROAD
            elif y==9: code=C_ROAD_RIGHT
            maps[stage,y,x]=code

# One persistent puzzle fragment is encoded directly in each surface map.
# All positions lie on the invariant main route and are unique per district.
piece_columns=(14,4,17,8,12)
for stage,x in enumerate(piece_columns): maps[stage,7,x]=C_PIECE

tile_pix=np.concatenate([map_rgb(semantic_tile(stage,code),False).reshape(-1)
                         for stage in range(6) for code in range(CODE_COUNT)]).astype(np.uint8)
K=6*CODE_COUNT

# Sprite crops from the actual sprite strip in the sheet. We use eight clear
# Fiat views, preserving the white 1971 500 L body and chrome/dark details.
car_boxes=[]
xs=[843,891,939,987,1035,1083]
for x in xs: car_boxes.append((x,704,x+45,747))
car_boxes += [(891,752,936,799),(1035,752,1080,799)]
car_frames=[]
for box in car_boxes:
    sp=img.crop(box).resize((48,40),Image.Resampling.LANCZOS)
    car_frames.append(map_rgb(sp,True).reshape(-1))
car_pix=np.concatenate(car_frames).astype(np.uint8)
car_sheet=Image.new('RGB',(48*8,40),(0,0,0))
for i,box in enumerate(car_boxes):
    car_sheet.paste(img.crop(box).resize((48,40),Image.Resampling.NEAREST),(i*48,0))
car_sheet.save(OUT/'fiat500L_1971_white_8dir.png')

# Scooter/rider crops from the gang panel; eight compact frames, different colors and poses.
scoot_boxes=[]
centers=[(1168,742),(1205,742),(1242,742),(1278,742),
         (1168,782),(1205,782),(1242,782),(1278,782)]
for cx,cy in centers:
    scoot_boxes.append((cx-14,cy-18,cx+14,cy+18))
scoot_frames=[]
for box in scoot_boxes:
    sp=img.crop(box).resize((24,32),Image.Resampling.LANCZOS)
    scoot_frames.append(sp)
scoot_pix=np.concatenate([map_rgb(s,True).reshape(-1) for s in scoot_frames]).astype(np.uint8)
sheet=Image.new('RGB',(24*8,32),(0,0,0))
for i,s in enumerate(scoot_frames): sheet.paste(s,(i*24,0))
sheet.save(OUT/'scooters_8bit.png')

# Virgil's Egg from the approved choice panel.
egg=img.crop((616,720,742,900)).resize((40,56),Image.Resampling.LANCZOS)
egg_pix=map_rgb(egg,True).reshape(-1).astype(np.uint8)
egg.save(OUT/'virgil_egg.png')

# Title/store artwork from the actual sheet.
icon=img.crop((0,0,458,381)).resize((160,160),Image.Resampling.LANCZOS)
icon.quantize(colors=128,method=Image.Quantize.MEDIANCUT).save(OUT/'icon.png',optimize=True)
screen=img.crop((459,0,1027,381)).resize((320,200),Image.Resampling.LANCZOS)
screen.quantize(colors=128,method=Image.Quantize.MEDIANCUT).save(OUT/'screenshot.png',optimize=True)

# Reconstructed stage preview using exactly the tile bank and maps that go in C.
def indices_to_rgb(ind):
    a=pal_arr[ind]
    return Image.fromarray(a.astype(np.uint8),'RGB')
previews=[]
for si in range(6):
    canvas=np.zeros((160,320),dtype=np.uint8)
    for ty in range(10):
        for tx in range(20):
            code=int(maps[si,ty,tx]); k=si*CODE_COUNT+code
            tile=tile_pix[k*256:(k+1)*256].reshape(16,16)
            canvas[ty*16:(ty+1)*16,tx*16:(tx+1)*16]=tile
    p=indices_to_rgb(canvas); p.save(OUT/f'runtime_stage_{si}.png'); previews.append(p)
contact=Image.new('RGB',(640,480),(0,0,0))
for i,p in enumerate(previews): contact.paste(p,((i%2)*320,(i//2)*160))
contact.save(OUT/'runtime_stages_contact.png')

# C header: 8-bit indexed frames, one byte/pixel.
def c_array(name,arr,ctype='uint8_t',per=20):
    vals=[]
    if ctype=='uint16_t': vals=[f'0x{int(x):04X}' for x in arr]
    else: vals=[str(int(x)) for x in arr]
    lines=[]
    for i in range(0,len(vals),per): lines.append('  '+','.join(vals[i:i+per])+',')
    return f'static const {ctype} {name}[{len(vals)}] = {{\n'+'\n'.join(lines)+'\n};\n'

with HDR.open('w') as f:
    f.write('#ifndef NAPRIDER_ASSETS8_H\n#define NAPRIDER_ASSETS8_H\n#include <stdint.h>\n')
    f.write(f'#define NR_PALETTE_COUNT {len(colors)}\n#define NR_TILE_COUNT {K}\n')
    f.write(f'#define NR_MAP_CODE_COUNT {CODE_COUNT}\n')
    f.write(f'#define NR_MAP_ROAD_CODE {C_ROAD}\n#define NR_MAP_PIECE_CODE {C_PIECE}\n')
    f.write('#define NR_TILE_W 16\n#define NR_TILE_H 16\n#define NR_STAGE_W 20\n#define NR_STAGE_H 10\n')
    f.write('#define NR_CAR_W 48\n#define NR_CAR_H 40\n#define NR_CAR_FRAMES 8\n')
    f.write('#define NR_SCOOT_W 24\n#define NR_SCOOT_H 32\n#define NR_SCOOT_FRAMES 8\n')
    f.write('#define NR_EGG_W 40\n#define NR_EGG_H 56\n')
    f.write(c_array('nr_palette',[rgb565(c) for c in colors],'uint16_t',12))
    f.write(c_array('nr_tiles',tile_pix,'uint8_t',24))
    f.write(c_array('nr_stage_maps',maps.reshape(-1),'uint8_t',24))
    f.write(c_array('nr_car_pixels',car_pix,'uint8_t',24))
    f.write(c_array('nr_scoot_pixels',scoot_pix,'uint8_t',24))
    f.write(c_array('nr_egg_pixels',egg_pix,'uint8_t',24))
    f.write('#endif\n')

print('palette',len(colors),'tiles',K,'tile bytes',len(tile_pix),'car',len(car_pix),'scoot',len(scoot_pix),'egg',len(egg_pix))
