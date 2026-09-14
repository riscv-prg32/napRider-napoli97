#!/usr/bin/env python3
from pathlib import Path
import numpy as np
from PIL import Image
from sklearn.cluster import MiniBatchKMeans

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
        # panel backgrounds are nearly black/navy; only make very dark pixels transparent
        lum=flat.sum(axis=1)
        dark=(lum<55) & (flat.max(axis=1)<35)
        out[dark]=0
    return out.reshape(a.shape[:2])

# Build 16x16 tile bank by clustering all approved gameplay scenes. Each stage
# remains a 20x10 map; up to 160 representative tiles preserve detail while
# fitting comfortably in the 128 KiB cartridge package/RAM budget.
T=16
raw_tiles=[]; features=[]; owners=[]
for si,sc in enumerate(scene_imgs):
    ar=np.asarray(sc,dtype=np.uint8)
    for ty in range(10):
        for tx in range(20):
            tile=ar[ty*T:(ty+1)*T,tx*T:(tx+1)*T,:]
            raw_tiles.append(tile)
            # 4x4 RGB block means => compact perceptual feature
            f=tile.reshape(4,4,4,4,3).mean(axis=(1,3)).reshape(-1)
            features.append(f); owners.append((si,ty,tx))
features=np.asarray(features,dtype=np.float32)
K=min(96,len(features))
km=MiniBatchKMeans(n_clusters=K,random_state=1997,batch_size=256,n_init=3,max_iter=200)
labels=km.fit_predict(features)
# medoid-like representative: actual tile nearest each centroid
reps=[]
for k in range(K):
    idx=np.flatnonzero(labels==k)
    if len(idx)==0: reps.append(np.zeros((T,T,3),dtype=np.uint8)); continue
    d=((features[idx]-km.cluster_centers_[k])**2).sum(axis=1)
    reps.append(raw_tiles[int(idx[int(d.argmin())])])

# Reorder clusters by first appearance for locality and deterministic maps.
first={k:len(labels)+1 for k in range(K)}
for i,k in enumerate(labels):
    if i<first[int(k)]: first[int(k)]=i
order=sorted(range(K), key=lambda k:first[k]); remap={old:new for new,old in enumerate(order)}
reps=[reps[k] for k in order]
labels=np.array([remap[int(k)] for k in labels],dtype=np.uint8)

maps=np.zeros((6,10,20),dtype=np.uint8)
for lab,(si,ty,tx) in zip(labels,owners): maps[si,ty,tx]=lab

tile_pix=[]
for t in reps:
    tile_pix.append(map_rgb(Image.fromarray(t),False).reshape(-1))
tile_pix=np.concatenate(tile_pix).astype(np.uint8)

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
            k=int(maps[si,ty,tx]); tile=tile_pix[k*256:(k+1)*256].reshape(16,16)
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
