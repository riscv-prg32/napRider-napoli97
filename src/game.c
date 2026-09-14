#include "prg32.h"
#include <stdint.h>
#include "assets8.h"

#define W 320
#define H 200
#define TOP 18
#define PLAY_H 160
#define BOTTOM 178
#define C_BLACK 0x0000
#define C_WHITE 0xFFFF
#define C_GOLD 0xFDC0
#define C_GREEN 0x07E0
#define C_RED 0xF800
#define C_CYAN 0x07FF
#define C_BLUE 0x1A3F
#define C_DARK 0x0841
#define C_GRAY 0x7BEF

#define STAGE_COUNT 6
#define SURFACE_STAGES 5
#define STAGE_LENGTH 1250
#define MAX_SCOOTERS 8
#define MAX_SHOTS 10

typedef enum { GS_PLAY=0, GS_EGG_CHOICE, GS_END } game_state_t;
typedef struct { int16_t rel; int8_t lane; uint8_t frame; uint8_t active; uint8_t stun; } scooter_t;
typedef struct { int16_t rel; int8_t lane; uint8_t kind; uint8_t life; } shot_t;

static prg32_indexed_sprite_t tile_sprite, car_sprite, scooter_sprite, egg_sprite;
static scooter_t scooters[MAX_SCOOTERS];
static shot_t shots[MAX_SHOTS];
static uint32_t last_input, frame_no, rng_state=0x4E415039u;
static int stage, stage_progress, lane, speed, score, fuel, battery, turbo;
static int8_t steer;
static uint8_t auto_mode, lights, handbrake, gadget, pieces, piece_mask, egg_taken, checkpoint_used;
static game_state_t state;
static char message[36];
static uint8_t message_timer;

static uint32_t rnd(void){ rng_state^=rng_state<<13; rng_state^=rng_state>>17; rng_state^=rng_state<<5; return rng_state; }
static int absi(int v){ return v<0?-v:v; }
static void str_copy(char *d,const char*s,int n){int i=0;while(s[i]&&i<n-1){d[i]=s[i];i++;}d[i]=0;}
static void say(const char*s){str_copy(message,s,sizeof(message));message_timer=150;}
static void u32text(int x,int y,uint32_t v){char b[9];int i=7;b[8]=0;do{b[i--]=(char)('0'+v%10);v/=10;}while(v&&i>=0);while(i>=0)b[i--]='0';prg32_gfx_text8(x,y,b,C_WHITE,C_BLACK);}

static const char *stage_name(void){
    if(stage==0) return "CENTRO STORICO";
    if(stage==1) return "POSILLIPO";
    if(stage==2) return "QUARTIERI";
    if(stage==3) return "VOMERO";
    if(stage==4) return "VIRGILIANO";
    return "SOTTERRANEA";
}

static void setup_sprites(void){
    tile_sprite.pixels=nr_tiles; tile_sprite.palette=nr_palette; tile_sprite.width=NR_TILE_W; tile_sprite.height=NR_TILE_H;
    tile_sprite.frame_count=NR_TILE_COUNT; tile_sprite.palette_count=NR_PALETTE_COUNT; tile_sprite.bits_per_pixel=8; tile_sprite.transparent_index=-1;
    car_sprite.pixels=nr_car_pixels; car_sprite.palette=nr_palette; car_sprite.width=NR_CAR_W; car_sprite.height=NR_CAR_H;
    car_sprite.frame_count=NR_CAR_FRAMES; car_sprite.palette_count=NR_PALETTE_COUNT; car_sprite.bits_per_pixel=8; car_sprite.transparent_index=0;
    scooter_sprite.pixels=nr_scoot_pixels; scooter_sprite.palette=nr_palette; scooter_sprite.width=NR_SCOOT_W; scooter_sprite.height=NR_SCOOT_H;
    scooter_sprite.frame_count=NR_SCOOT_FRAMES; scooter_sprite.palette_count=NR_PALETTE_COUNT; scooter_sprite.bits_per_pixel=8; scooter_sprite.transparent_index=0;
    egg_sprite.pixels=nr_egg_pixels; egg_sprite.palette=nr_palette; egg_sprite.width=NR_EGG_W; egg_sprite.height=NR_EGG_H;
    egg_sprite.frame_count=1; egg_sprite.palette_count=NR_PALETTE_COUNT; egg_sprite.bits_per_pixel=8; egg_sprite.transparent_index=0;
}

static void spawn_scooter(int i){
    scooters[i].rel=(int16_t)(150+(int)(rnd()%800)); scooters[i].lane=(int8_t)(-38+(int)(rnd()%77));
    scooters[i].frame=6; scooters[i].active=1; scooters[i].stun=0;
}
static int nearest_scooter(void){int i,b=-1,bd=32767;for(i=0;i<MAX_SCOOTERS;i++)if(scooters[i].active){int d=absi(scooters[i].rel)+absi(scooters[i].lane-lane)*3;if(d<bd){bd=d;b=i;}}return b;}

static void reset_run(void){
    int i; stage=0;stage_progress=0;lane=0;speed=4;score=0;fuel=1000;battery=1000;turbo=100;
    steer=0;auto_mode=0;lights=1;handbrake=0;gadget=0;pieces=0;piece_mask=0;egg_taken=0;checkpoint_used=0;state=GS_PLAY;
    for(i=0;i<MAX_SCOOTERS;i++) spawn_scooter(i);
    for(i=0;i<MAX_SHOTS;i++) shots[i].life=0;
    say("vai cuonc cuonc");
}

static void fire_gadget(void){
    int i;for(i=0;i<MAX_SHOTS;i++)if(!shots[i].life){shots[i].rel=(gadget==0)?25:-25;shots[i].lane=(int8_t)lane;shots[i].kind=gadget;shots[i].life=(uint8_t)(gadget==0?70:110);prg32_audio_note_on_pan(5,(uint8_t)(4+gadget),76,220,(int8_t)(gadget?26:-26));return;}
}

void naprider_init(void){
    setup_sprites();
    prg32_band_set_game_info("napRider-napoli97 | A ACTION | B AUTO | SELECT FRENO");
    prg32_audio_play_track(0);
    reset_run();
}

static void complete_stage(void){
    if(stage<SURFACE_STAGES){
        if((piece_mask&(1u<<stage))==0){stage_progress=0;lane=0;say("TROVA IL FRAMMENTO");return;}
        score+=1500;stage++;stage_progress=0;lane=0;checkpoint_used=0;
        if(stage==5) say("MOSAICO COMPLETO: VARCO APERTO"); else say("ROTTA RICOMPOSTA");
    } else { state=GS_EGG_CHOICE; say("L'UOVO DI VIRGILIO"); }
}

static int track_scroll(void){return (stage_progress>>2)%(NR_STAGE_W*16);}
static uint8_t player_map_code(void){
    int mx=((96+track_scroll())>>4)%NR_STAGE_W;
    int py=128+(lane/2)-TOP,my=py>>4;
    if(my<0)my=0;if(my>=NR_STAGE_H)my=NR_STAGE_H-1;
    return nr_stage_maps[stage*NR_STAGE_W*NR_STAGE_H+my*NR_STAGE_W+mx];
}
static void collect_piece(uint8_t code){
    uint8_t bit=(uint8_t)(1u<<stage);
    if(stage<SURFACE_STAGES&&code==NR_MAP_PIECE_CODE&&(piece_mask&bit)==0){
        piece_mask|=bit;pieces++;score+=750;say("FRAMMENTO DI VIRGILIO");
        prg32_audio_note_on_pan(6,3,84,240,0);
    }
}

static void update_play(uint32_t in,uint32_t pressed){
    int i;
    steer=0;
    if((pressed&PRG32_BTN_B) && !(in&PRG32_BTN_SELECT)){auto_mode=(uint8_t)!auto_mode;say(auto_mode?"SELF DRIVE ON":"SELF DRIVE OFF");}
    if(pressed&PRG32_BTN_SELECT){if(in&PRG32_BTN_B)lights=(uint8_t)!lights;else handbrake=(uint8_t)!handbrake;}
    if(auto_mode){
        int t=nearest_scooter();
        if(pressed&PRG32_BTN_LEFT)gadget=(uint8_t)((gadget+2)%3);
        if(pressed&PRG32_BTN_RIGHT)gadget=(uint8_t)((gadget+1)%3);
        if(pressed&PRG32_BTN_A)fire_gadget();
        if(stage<5&&t>=0){if(lane<scooters[t].lane-2){lane+=2;steer=1;}else if(lane>scooters[t].lane+2){lane-=2;steer=-1;}}else{if(lane<0){lane++;steer=1;}else if(lane>0){lane--;steer=-1;}}
        if(speed<5)speed=5;
    }else{
        if(in&PRG32_BTN_UP){lane-=2;steer=-1;}
        if(in&PRG32_BTN_DOWN){lane+=2;steer=1;}
        if(in&PRG32_BTN_RIGHT){if(speed<7)speed++;}else if(speed>3&&(frame_no%8)==0)speed--;
        if(in&PRG32_BTN_LEFT&&speed>1)speed--;
        if((pressed&PRG32_BTN_A)&&turbo>=15){speed+=2;if(speed>9)speed=9;turbo-=15;score+=15;prg32_audio_note_on_pan(4,4,69,230,-20);}
    }
    if(lane<-44) lane=-44;
    if(lane>44) lane=44;
    if(handbrake){if(speed>2&&(frame_no%3)==0)speed--;if(in&PRG32_BTN_UP){lane-=2;steer=-1;}
        if(in&PRG32_BTN_DOWN){lane+=2;steer=1;}
        if((in&PRG32_BTN_RIGHT)&&(frame_no%75)==0) say("ah il freno a mano");
    }
    if(lane<-44) lane=-44;
    if(lane>44) lane=44;
    if(fuel<=0)speed=0;else{stage_progress+=speed;if((frame_no%3)==0)fuel--;}
    if(lights&&battery>0&&(frame_no%5)==0)battery--;
    if(fuel<130&&(frame_no%180)==0)say("ho sete");
    if(!speed&&lights&&battery<300&&(frame_no%210)==0)say("hai lasciato le luci accese");
    if(turbo<100&&(frame_no%18)==0)turbo++;
    /* Mythic route checkpoints double as petrol stops to keep exploration moving. */
    if(!checkpoint_used&&stage_progress>540&&stage_progress<575&&absi(lane+34)<14){fuel=1000;score+=25;checkpoint_used=1;}
    collect_piece(player_map_code());

    if(stage<5){
        for(i=0;i<MAX_SCOOTERS;i++)if(scooters[i].active){
            if(scooters[i].stun){scooters[i].stun--;continue;}
            scooters[i].rel-=(int16_t)(speed-2);if((frame_no+i*11)%70==0){int turn=(int)(rnd()%3)-1;scooters[i].lane+=(int8_t)(turn*7);scooters[i].frame=(uint8_t)(turn<0?7:turn>0?5:6);}else if((frame_no+i*7)%24==0)scooters[i].frame=6;
            if(scooters[i].lane<-42) scooters[i].lane=-42;
            if(scooters[i].lane>42) scooters[i].lane=42;
            if(scooters[i].rel<-120)spawn_scooter(i);
        }
        for(i=0;i<MAX_SHOTS;i++)if(shots[i].life){int j;shots[i].life--;shots[i].rel+=(int16_t)(shots[i].kind==0?11:-1);
            for(j=0;j<MAX_SCOOTERS;j++)if(scooters[j].active&&absi(shots[i].rel-scooters[j].rel)<25&&absi(shots[i].lane-scooters[j].lane)<15){
                scooters[j].stun=(uint8_t)(shots[i].kind==0?60:shots[i].kind==1?95:140);shots[i].life=0;score+=100;break;
            }
        }
    }
    if(stage_progress>=STAGE_LENGTH)complete_stage();
}

void naprider_update(void){
    uint32_t in=prg32_input_read(),pressed=in&~last_input;frame_no++;if(message_timer)message_timer--;
    if(state==GS_PLAY)update_play(in,pressed);
    else if(state==GS_EGG_CHOICE){if(pressed&PRG32_BTN_A){egg_taken=1;state=GS_END;score+=5000;}else if(pressed&PRG32_BTN_B){egg_taken=0;state=GS_END;score+=7500;}}
    else if(state==GS_END&&(pressed&PRG32_BTN_A))reset_run();
    last_input=in;
}

static void draw_stage_tiles(void){
    int sx,sy;
    for(sy=0;sy<NR_STAGE_H;sy++){
        int scroll_x=sy<3?(stage_progress>>5):sy<6?(stage_progress>>4):track_scroll();
        int tile_dx=(scroll_x>>4)%NR_STAGE_W,px=-(scroll_x&15);
        for(sx=0;sx<21;sx++){
        int mx=(sx+tile_dx)%NR_STAGE_W,my=sy;
        int code=nr_stage_maps[stage*NR_STAGE_W*NR_STAGE_H+my*NR_STAGE_W+mx];
        if(code==NR_MAP_PIECE_CODE&&(piece_mask&(1u<<stage)))code=NR_MAP_ROAD_CODE;
        int frame=stage*NR_MAP_CODE_COUNT+code;
        prg32_sprite_draw_indexed(px+sx*16,TOP+sy*16,&tile_sprite,frame);
    }}
}

static void project_entity(int rel,int ln,int *x,int *y){*x=96+(rel/3);*y=128+(ln/2);}
static int car_frame(void){
    if(handbrake&&steer<0)return 0;
    if(handbrake&&steer>0)return 4;
    if(steer<0) return 7;
    if(steer>0) return 5;
    return 6;
}

static void draw_entities(void){
    int i,x,y;
    if(stage<5){
        for(i=0;i<MAX_SHOTS;i++)if(shots[i].life){project_entity(shots[i].rel,shots[i].lane,&x,&y);prg32_gfx_rect(x-2,y-2,5,4,shots[i].kind==0?C_RED:shots[i].kind==1?C_GOLD:C_WHITE);}
        for(i=0;i<MAX_SCOOTERS;i++)if(scooters[i].active){project_entity(scooters[i].rel,scooters[i].lane,&x,&y);if(x>-30&&x<320&&y>TOP-20&&y<BOTTOM)prg32_sprite_draw_indexed(x-12,y-28,&scooter_sprite,scooters[i].frame%NR_SCOOT_FRAMES);}
    }
    if(state==GS_EGG_CHOICE||state==GS_END){prg32_sprite_draw_indexed(140,60,&egg_sprite,0);}
    project_entity(0,lane,&x,&y);prg32_sprite_draw_indexed(x-24,y-15,&car_sprite,car_frame());
}

static void draw_bar(int x,int y,int n,int max,uint16_t c){int i,fill=(n*8)/max;for(i=0;i<8;i++)prg32_gfx_rect(x+i*5,y,4,7,i<fill?c:C_DARK);}
static void draw_hud(void){
    char s[2];s[1]=0;prg32_gfx_rect(0,0,W,TOP,C_BLACK);prg32_gfx_text8(4,5,"SCORE",C_WHITE,C_BLACK);u32text(45,5,(uint32_t)score);
    prg32_gfx_text8(110,5,"F",C_GOLD,C_BLACK);draw_bar(122,5,fuel,1000,C_GREEN);
    prg32_gfx_text8(166,5,"B",C_CYAN,C_BLACK);draw_bar(178,5,battery,1000,C_CYAN);
    prg32_gfx_text8(222,5,lights?"L+":"L-",lights?C_GOLD:C_GRAY,C_BLACK);
    s[0]=(char)('0'+pieces);prg32_gfx_text8(248,5,"PZ",C_GOLD,C_BLACK);prg32_gfx_text8(270,5,s,C_WHITE,C_BLACK);prg32_gfx_text8(279,5,"/5",C_GRAY,C_BLACK);
    prg32_gfx_rect(0,BOTTOM,W,H-BOTTOM,C_BLACK);prg32_gfx_text8(4,184,auto_mode?"AUTO":"MAN",auto_mode?C_GREEN:C_WHITE,C_BLACK);
    prg32_gfx_text8(43,184,gadget==0?"RAUTI":gadget==1?"GRASSO":"CHIODI",C_GOLD,C_BLACK);prg32_gfx_text8(110,184,"T",C_WHITE,C_BLACK);draw_bar(122,184,turbo,100,C_RED);
    prg32_gfx_text8(170,184,stage_name(),C_WHITE,C_BLACK);
}

static void draw_message(void){if(message_timer){prg32_gfx_rect(34,144,252,28,C_BLACK);prg32_gfx_rect(35,145,250,26,C_CYAN);prg32_gfx_rect(37,147,246,22,C_BLACK);prg32_gfx_text8(46,154,message,C_WHITE,C_BLACK);}}
static void draw_choice(void){
    if(state!=GS_EGG_CHOICE) return;
    prg32_gfx_rect(63,88,194,54,C_BLACK); prg32_gfx_rect(65,90,190,50,C_GOLD); prg32_gfx_rect(67,92,186,46,C_BLACK);
    prg32_gfx_text8(92,98,"L'UOVO DI VIRGILIO",C_GOLD,C_BLACK);prg32_gfx_text8(83,116,"A PRENDI   B LASCIA",C_WHITE,C_BLACK);
}
static void draw_end(void){
    if(state!=GS_END) return;
    prg32_gfx_rect(35,55,250,85,C_BLACK); prg32_gfx_rect(38,58,244,79,C_BLUE);
    prg32_gfx_text8(72,70,egg_taken?"HAI PRESO L'UOVO":"HAI LASCIATO L'UOVO",C_GOLD,C_BLUE);
    prg32_gfx_text8(59,89,egg_taken?"NAPOLI TRATTIENE IL FIATO":"NAPOLI RESTA IN EQUILIBRIO",C_WHITE,C_BLUE);
    prg32_gfx_text8(80,115,"A - NUOVA PARTITA",C_WHITE,C_BLUE);
}

void naprider_draw(void){
    prg32_gfx_clear(C_BLACK);draw_stage_tiles();draw_entities();draw_hud();draw_message();draw_choice();draw_end();prg32_gfx_present();
}
