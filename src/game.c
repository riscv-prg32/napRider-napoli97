/*
 * napRider-napoli97 - a PRG32 portable cartridge.
 *
 * A horizontal-parallax arcade drive through Naples in 1997: collect the five
 * Virgilian fragments, keep the scooter gangs off the white Fiat 500 L, open
 * Napoli Sotterranea and decide what to do with the Egg of Virgil.
 *
 * Graphics are palette-indexed. The ESP32-C6 framebuffer stores one byte per
 * pixel and maps every sprite colour to a cell of the firmware's 6x6x6 system
 * cube, so the cartridge writes each of its colours into the palette entry of
 * that colour's own cell (program()). The art keeps one colour per cell, so
 * the board shows the authored colours exactly, and QEMU - which keeps an
 * RGB565 surface - shows the same ones. Fades, the unlit tunnel, the white
 * flash and the shimmering sea are all palette effects built on that.
 *
 * Portable cartridges may be loaded at different addresses, so this file
 * keeps no pointer tables in static data: descriptors are filled at run time.
 */
#include "prg32.h"
#include <stdint.h>
#include "assets.h"

#define W 320
#define TOP 18                    /* first playfield row; the HUD is above */
#define BOTTOM 178                /* first row of the lower HUD band */
#define TICK_MS 33                /* simulation step; the firmware paces frames at 33 ms */

#define ROAD_TOP (TOP + 6 * NR_TILE_H)
#define FOOT_MIN (ROAD_TOP + 13)  /* car wheel line, top lane limit */
#define FOOT_MAX (TOP + 9 * NR_TILE_H - 1)
#define LANE_TOP_FOOT 131
#define LANE_MID_FOOT 147
#define LANE_LOW_FOOT 161
#define CAR_X 56                  /* the camera keeps the car here */

#define STAGE_COUNT NR_STAGE_COUNT
#define SURFACE_STAGES 5
#define STAGE_PX 2880             /* nine map widths per district */
#define MAP_PX (NR_STAGE_W * NR_TILE_W)

#define SPEED_CRUISE 64           /* 1/16 px per tick */
#define SPEED_TURBO 104
#define SPEED_AUTO 44
#define MAX_SCOOTERS 6
#define MAX_SHOTS 6
#define SCORE_GAME "naprider"

/* System palette entries the colour cube never maps to: safe for our own use. */
#define IDX_SKY 232
#define IDX_PANEL 240
#define IDX_BAR_OFF 241
#define IDX_OIL 242
#define IDX_GOLD 243
#define IDX_BLACK 0
#define IDX_WHITE 1
#define IDX_RED 2
#define IDX_GREEN 3
#define IDX_YELLOW 5
#define IDX_CYAN 6

#define C_BLACK PRG32_COLOR_BLACK
#define C_WHITE PRG32_COLOR_WHITE
#define C_YELLOW PRG32_COLOR_YELLOW
#define C_CYAN PRG32_COLOR_CYAN
#define C_GREEN PRG32_COLOR_GREEN
#define C_RED PRG32_COLOR_RED

/* Sound: the tracker owns voices 0-3, the game owns 4-7. */
#define V_ENGINE 4
#define V_FX 5
#define V_CHIME 6
#define V_GANG 7
#define I_ENGINE 4
#define I_ZAP 5
#define I_CHIME 6
#define I_CRASH 7
#define I_HORN 8
#define I_SCOOTER 9
#define TRACK_EGG 6
#define TRACK_OVER 7

typedef enum { GS_TITLE = 0, GS_INTRO, GS_PLAY, GS_CLEAR, GS_EGG, GS_END, GS_OVER } game_state_t;
typedef enum { GADGET_RAUTI = 0, GADGET_GRASSO, GADGET_CHIODI, GADGET_COUNT } gadget_t;

typedef struct {
    int32_t rel;                  /* left edge relative to the car's, 1/16 px */
    int16_t foot;                 /* wheel line, screen y */
    int16_t target;               /* lane the rider is heading for */
    int16_t speed;                /* 1/16 px per tick */
    uint8_t gang, chaser, stun, active;
} scooter_t;

typedef struct {
    int32_t rel;
    int16_t foot;
    uint8_t kind, life;
} shot_t;

static prg32_indexed_sprite_t tile_sprite, cut_sprite, car_sprite, egg_sprite, ves_sprite, isle_sprite, beam_sprite;
static prg32_indexed_sprite_t scoot_sprite[NR_GANG_COUNT];
/* Working palettes: the authored colours after the current effects. */
static uint16_t tile_pal[16], car_pal[16], egg_pal[16], far_pal[4], beam_pal[2];
static uint16_t gang_pal[NR_GANG_COUNT][16];

static scooter_t scooters[MAX_SCOOTERS];
static shot_t shots[MAX_SHOTS];
static game_state_t state;
static uint32_t rng_state = 0x4E415039u;
static uint32_t last_input, last_ms, tick_no, world_x, score, best_score;
static int32_t ms_bank;
static int stage, stage_end, speed, foot, fuel, battery, turbo, fuel_bank, state_timer;
static int8_t steer;
static uint8_t auto_mode, lights, handbrake, gadget, piece_mask, egg_taken, score_sent;
static uint8_t boost, invulnerable, shake, cooldown, pump_lock, warned_dark, combo_used;
/* Palette effect levels, 0..16. */
static uint8_t fade, dim, flash, palette_dirty, hud_dirty, clear_screen;
static uint32_t hud_signature;
static char message[40];
static uint8_t message_timer;
static uint8_t voice_timer[4];
static uint8_t chime_step, chime_kind, engine_note;

/* ------------------------------------------------------------------------ */
/* Small helpers                                                            */
/* ------------------------------------------------------------------------ */
static uint32_t rnd(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return rng_state;
}

static int absi(int v) { return v < 0 ? -v : v; }
static int clampi(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

static int text_len(const char *s) {
    int n = 0;
    while (s[n]) n++;
    return n;
}

static void text_centre(int y, const char *s, uint16_t fg) {
    prg32_gfx_text8((W - text_len(s) * 8) / 2, y, s, fg, C_BLACK);
}

static void text_number(int x, int y, uint32_t value, int digits, uint16_t fg) {
    char buf[9];
    int i;
    buf[digits] = 0;
    for (i = digits - 1; i >= 0; i--) {
        buf[i] = (char)('0' + value % 10);
        value /= 10;
    }
    prg32_gfx_text8(x, y, buf, fg, C_BLACK);
}

static const char *stage_name(int s) {
    if (s == 0) return "CENTRO STORICO";
    if (s == 1) return "POSILLIPO";
    if (s == 2) return "QUARTIERI";
    if (s == 3) return "VOMERO";
    if (s == 4) return "VIRGILIANO";
    return "SOTTERRANEA";
}

static const char *stage_hint(int s) {
    if (s == 0) return "TROVA IL FRAMMENTO DI VIRGILIO";
    if (s == 1) return "IL PIENO E SUL LUNGOMARE";
    if (s == 2) return "ATTENZIONE AI MOTORINI";
    if (s == 3) return "E BUIO: SELECT+B ACCENDE LE LUCI";
    if (s == 4) return "ULTIMO FRAMMENTO, POI IL VARCO";
    return "HIC VIRGILIUS MAGNA LATET";
}

static const char *gadget_name(int g) {
    if (g == GADGET_RAUTI) return "RAUTI ";
    if (g == GADGET_GRASSO) return "GRASSO";
    return "CHIODI";
}

static int stage_is_dark(int s) { return s == 3 || s == 5; }
static int stage_has_sea(int s) { return s == 1 || s == 4; }
static int stage_has_sky(int s) { return s < SURFACE_STAGES; }

static void say(const char *s) {
    int i = 0;
    while (s[i] && i < (int)sizeof(message) - 1) {
        message[i] = s[i];
        i++;
    }
    message[i] = 0;
    message_timer = 90;
}

/* ------------------------------------------------------------------------ */
/* Sound                                                                    */
/* ------------------------------------------------------------------------ */
static int pan_for_x(int x) { return clampi((x - W / 2) * 63 / (W / 2), -60, 60); }

/* Start a note on one of the game's voices and release it after `ticks`. */
static void sfx(int voice, int instrument, int note, int volume, int pan, int ticks) {
    prg32_audio_note_on_pan((uint8_t)voice, (uint8_t)instrument, (uint8_t)note, (uint8_t)volume, (int8_t)pan);
    voice_timer[voice - V_ENGINE] = (uint8_t)ticks;
}

static void chime(int kind) {
    chime_kind = (uint8_t)kind;
    chime_step = 1;
}

static void sound_tick(void) {
    int v;
    for (v = V_FX; v <= V_GANG; v++) {
        uint8_t *left = &voice_timer[v - V_ENGINE];
        if (*left && --*left == 0) prg32_audio_note_off((uint8_t)v);
    }
    /* Three-note arpeggios on the chime voice: 0 fragment, 1 petrol, 2 car talking. */
    if (chime_step && (tick_no & 3) == 0) {
        int base = chime_kind == 0 ? 76 : chime_kind == 1 ? 67 : 72;
        int step = chime_step - 1;
        int note = base + (chime_kind == 2 ? (step ? -4 : 0) : step * (chime_kind ? 4 : 5));
        sfx(V_CHIME, chime_kind == 2 ? I_HORN : I_CHIME, note, chime_kind == 2 ? 120 : 220, 0, 4);
        chime_step++;
        if (chime_step > (chime_kind == 2 ? 2 : 3)) chime_step = 0;
    }
}

/* The engine drone follows the speed; it is silent at a standstill. */
static void engine_tick(void) {
    int note = state == GS_PLAY && speed > 0 ? 31 + speed / 6 + (boost ? 5 : 0) : 0;
    if (note == engine_note) return;
    if ((tick_no & 3) && note) return;
    engine_note = (uint8_t)note;
    if (note) prg32_audio_note_on_pan(V_ENGINE, I_ENGINE, (uint8_t)note, 80, -12);
    else prg32_audio_note_off(V_ENGINE);
}

static void music(int track) {
    int v;
    prg32_audio_stop_track();
    for (v = 0; v < 4; v++) prg32_audio_note_off((uint8_t)v);
    prg32_audio_play_track((uint16_t)track);
}

/* ------------------------------------------------------------------------ */
/* Palette effects                                                          */
/* ------------------------------------------------------------------------ */
/* Blend two RGB565 colours, t = 0 (all a) .. 16 (all b). */
static uint16_t mix(uint16_t a, uint16_t b, int t) {
    int ar = a >> 11, ag = (a >> 5) & 63, ab = a & 31;
    int br = b >> 11, bg = (b >> 5) & 63, bb = b & 31;
    int r = ar + ((br - ar) * t) / 16, g = ag + ((bg - ag) * t) / 16, bl = ab + ((bb - ab) * t) / 16;
    return (uint16_t)((r << 11) | (g << 5) | bl);
}

/* Global look of one colour: tunnel darkness, fade to black, white flash. */
static uint16_t fx(uint16_t c) {
    int bright = fade * dim / 16;
    if (bright < 16) c = mix(c, C_BLACK, 16 - bright);
    if (flash) c = mix(c, C_WHITE, flash);
    return c;
}

static int is_named(uint16_t c) {
    return c == 0x0000 || c == 0xffff || c == 0xf800 || c == 0x07e0 || c == 0x001f || c == 0xffe0 ||
           c == 0x07ff || c == 0xf81f;
}

/* Put a colour in the system palette entry the firmware will choose for it. */
static void program(uint16_t c) {
    unsigned r = (unsigned)(c >> 11) * 5u / 31u, g = (unsigned)((c >> 5) & 63) * 5u / 63u, b = (unsigned)(c & 31) * 5u / 31u;
    if (!is_named(c)) prg32_palette_set((uint8_t)(16u + r * 36u + g * 6u + b), c);
}

/* Animated colours step through authored colours only (never an arbitrary
 * blend), so each still owns its cube cell: 0 base, 1 and 3 sparkle, 2 peak. */
static uint16_t step3(uint16_t base, uint16_t middle, uint16_t peak, int phase) {
    return phase == 0 ? base : phase == 2 ? peak : middle;
}

static void palette_apply(void) {
    const uint16_t *base = &nr_stage_pal[stage * 16];
    int phase = (int)((tick_no >> 3) & 3), i, g;

    for (i = 0; i < 16; i++) {
        uint16_t c = base[i];
        if (i == NR_ROLE_WATER_LIGHT && stage_has_sea(stage)) c = step3(c, nr_sparkle_pal[stage], C_WHITE, phase);
        if (i == NR_ROLE_LIT && stage == STAGE_COUNT - 1) c = step3(c, nr_sparkle_pal[stage], base[NR_ROLE_LANE], phase);
        tile_pal[i] = fx(c);
        program(tile_pal[i]);
    }
    for (i = 1; i < 4; i++) {
        far_pal[i] = fx(nr_far_pal[stage * 4 + i]);
        program(far_pal[i]);
    }
    for (i = 0; i < NR_SKY_BANDS; i++) prg32_palette_set((uint8_t)(IDX_SKY + i), fx(nr_sky_pal[stage * NR_SKY_BANDS + i]));
    for (g = 0; g < NR_GANG_COUNT; g++)
        for (i = 1; i < 16; i++) {
            gang_pal[g][i] = fx(nr_gang_pal[g * 16 + i]);
            program(gang_pal[g][i]);
        }
    for (i = 1; i < 16; i++) {
        uint16_t c = nr_egg_pal[i];
        if (i == NR_EGG_GLOW) c = step3(c, nr_egg_pal[NR_EGG_GLOW2], nr_egg_pal[NR_EGG_GOLD], phase);
        if (i == NR_EGG_STAR) c = step3(c, c, C_WHITE, phase);
        egg_pal[i] = fx(c);
        program(egg_pal[i]);
    }
    /* The car is programmed last: where colours share a cell, it wins. */
    for (i = 1; i < 16; i++) {
        car_pal[i] = fx(nr_car_pal[i]);
        program(car_pal[i]);
    }
    beam_pal[1] = NR_BEAM_COLOUR;
    program(beam_pal[1]);
    palette_dirty = 0;
}

static void sprite_setup(prg32_indexed_sprite_t *s, const uint8_t *pixels, const uint16_t *palette, int w, int h,
                         int frames, int colours, int bpp, int transparent) {
    s->pixels = pixels;
    s->palette = palette;
    s->width = (uint16_t)w;
    s->height = (uint16_t)h;
    s->frame_count = (uint16_t)frames;
    s->palette_count = (uint16_t)colours;
    s->bits_per_pixel = (uint8_t)bpp;
    s->transparent_index = (int16_t)transparent;
}

static void setup_sprites(void) {
    int g;
    sprite_setup(&tile_sprite, nr_tiles, tile_pal, NR_TILE_W, NR_TILE_H, NR_TILE_COUNT, 16, 4, -1);
    sprite_setup(&cut_sprite, nr_tiles, tile_pal, NR_TILE_W, NR_TILE_H, NR_TILE_COUNT, 16, 4, NR_ROLE_WATER);
    sprite_setup(&car_sprite, nr_car_pixels, car_pal, NR_CAR_W, NR_CAR_H, NR_CAR_FRAMES, 16, 4, 0);
    sprite_setup(&egg_sprite, nr_egg_pixels, egg_pal, NR_EGG_W, NR_EGG_H, 1, 16, 4, 0);
    sprite_setup(&ves_sprite, nr_ves_pixels, far_pal, NR_VES_W, NR_VES_H, 1, 4, 2, 0);
    sprite_setup(&isle_sprite, nr_isle_pixels, far_pal, NR_ISLE_W, NR_ISLE_H, 1, 4, 2, 0);
    sprite_setup(&beam_sprite, nr_beam_pixels, beam_pal, NR_BEAM_W, NR_BEAM_H, 1, 2, 1, 0);
    for (g = 0; g < NR_GANG_COUNT; g++)
        sprite_setup(&scoot_sprite[g], nr_scoot_pixels, gang_pal[g], NR_SCOOT_W, NR_SCOOT_H, NR_SCOOT_FRAMES, 16, 4, 0);
}

/* ------------------------------------------------------------------------ */
/* World                                                                    */
/* ------------------------------------------------------------------------ */
static int scroll_px(void) { return (int)(world_x >> 4); }

/* Map cell at a world column and playfield row, with collected or
 * not-yet-revealed fragments shown as plain road. */
static int map_code(int column, int row) {
    int code = nr_stage_maps[(stage * NR_STAGE_H + row) * NR_STAGE_W + column % NR_STAGE_W];
    if (code == NR_CODE_PIECE) {
        int revealed = (column / NR_STAGE_W) & 1;         /* every other map width */
        if (!revealed || (piece_mask & (1u << stage))) return row == 6 ? NR_CODE_ROAD : NR_CODE_DASH;
    }
    return code;
}

static int code_at(int screen_x, int foot_y) {
    int row = clampi((foot_y - 4 - TOP) >> 4, 0, NR_STAGE_H - 1);
    return map_code((scroll_px() + screen_x) >> 4, row);
}

static int lane_foot(int lane) { return lane == 0 ? LANE_TOP_FOOT : lane == 1 ? LANE_MID_FOOT : LANE_LOW_FOOT; }

static void spawn_scooter(int i) {
    scooter_t *s = &scooters[i];
    int limit = 2 + stage;                              /* gangs grow district by district */
    s->active = (uint8_t)(stage < SURFACE_STAGES && i < (limit > MAX_SCOOTERS ? MAX_SCOOTERS : limit));
    s->gang = (uint8_t)(rnd() % NR_GANG_COUNT);
    s->chaser = (uint8_t)(stage >= 2 && (rnd() & 3) == 0);
    s->stun = 0;
    s->foot = (int16_t)lane_foot((int)(rnd() % 3));
    s->target = s->foot;
    if (s->chaser) {
        s->rel = -(int32_t)(90 + rnd() % 120) * 16;
        s->speed = (int16_t)(70 + rnd() % 12);
    } else {
        s->rel = (int32_t)(300 + rnd() % 420) * 16;
        s->speed = (int16_t)(22 + rnd() % 18);
    }
}

static void start_stage(int s) {
    int i;
    stage = s;
    world_x = 0;
    stage_end = STAGE_PX;
    foot = LANE_MID_FOOT;
    speed = 0;
    boost = invulnerable = shake = cooldown = pump_lock = warned_dark = 0;
    steer = 0;
    for (i = 0; i < MAX_SCOOTERS; i++) spawn_scooter(i);
    for (i = 0; i < MAX_SHOTS; i++) shots[i].life = 0;
    state = GS_INTRO;
    state_timer = 75;
    fade = 0;
    dim = 16;
    flash = 0;
    palette_dirty = hud_dirty = clear_screen = 1;
    message_timer = 0;
    music(s);
}

static void reset_run(void) {
    score = 0;
    fuel = battery = 1000;
    turbo = 100;
    fuel_bank = 0;
    auto_mode = handbrake = 0;
    lights = 0;
    gadget = GADGET_RAUTI;
    piece_mask = egg_taken = score_sent = 0;
    start_stage(0);
    say("vai cuonc cuonc");
    chime(2);
}

static void goto_title(void) {
    prg32_score_t top;
    state = GS_TITLE;
    stage = 0;
    world_x = 0;
    foot = LANE_TOP_FOOT;
    speed = 0;
    lights = 0;
    fade = dim = 16;
    flash = 0;
    message_timer = 0;
    palette_dirty = hud_dirty = clear_screen = 1;
    if (prg32_score_count(SCORE_GAME) > 0 && prg32_score_get(SCORE_GAME, 0, &top) == 0 && top.score > best_score)
        best_score = top.score;
    music(0);
}

static void finish(game_state_t end_state) {
    state = end_state;
    state_timer = 0;
    speed = 0;
    if (!score_sent) {
        prg32_score_submit_current_player(SCORE_GAME, score);   /* local top five, Store sync when online */
        score_sent = 1;
    }
    if (score > best_score) best_score = score;
    hud_dirty = 1;
}

static void fire_gadget(void) {
    int i;
    if (cooldown) return;
    for (i = 0; i < MAX_SHOTS; i++) {
        shot_t *s = &shots[i];
        if (s->life) continue;
        s->kind = gadget;
        s->foot = (int16_t)foot;
        s->rel = gadget == GADGET_RAUTI ? (NR_CAR_W - 4) * 16 : -10 * 16;
        s->life = (uint8_t)(gadget == GADGET_RAUTI ? 45 : 160);
        cooldown = 14;
        sfx(V_FX, I_ZAP, gadget == GADGET_RAUTI ? 84 : 60 - gadget * 5, 200, gadget == GADGET_RAUTI ? -20 : -45, 5);
        return;
    }
}

static void crash(int penalty) {
    if (invulnerable) return;
    invulnerable = 45;
    shake = 10;
    speed /= 3;
    boost = 0;
    fuel -= penalty;
    if (fuel < 0) fuel = 0;
    sfx(V_GANG, I_CRASH, 50, 255, -30, 9);
}

static void collect_piece(void) {
    piece_mask |= (uint8_t)(1u << stage);
    score += 750;
    flash = 12;
    palette_dirty = 1;
    say("FRAMMENTO DI VIRGILIO");
    chime(0);
}

static void complete_stage(void) {
    if (stage < SURFACE_STAGES && !(piece_mask & (1u << stage))) {
        stage_end += STAGE_PX;                           /* the district goes round again until it is found */
        say("TROVA IL FRAMMENTO");
        return;
    }
    score += 1500 + (uint32_t)fuel / 10;
    if (stage == STAGE_COUNT - 1) {
        state = GS_EGG;
        speed = 0;
        say("ci siamo...");
        chime(2);
        music(TRACK_EGG);
    } else {
        state = GS_CLEAR;
        state_timer = 0;
        say(stage == SURFACE_STAGES - 1 ? "MOSAICO COMPLETO: VARCO APERTO" : "ROTTA RICOMPOSTA");
    }
    hud_dirty = 1;
}

/* Something in the car's lane, close ahead: a rider or underground rubble. */
static int threat_ahead(void) {
    int i, x;
    for (i = 0; i < MAX_SCOOTERS; i++) {
        const scooter_t *s = &scooters[i];
        if (s->active && !s->stun && s->rel > 0 && s->rel < 150 * 16 && absi(s->foot - foot) < 12) return 1;
    }
    for (x = NR_CAR_W; x <= NR_CAR_W + 48; x += 16)
        if (code_at(CAR_X + x, foot) == NR_CODE_RUBBLE) return 1;
    return 0;
}

static void drive(uint32_t in, uint32_t pressed, uint32_t released) {
    int lane_step = handbrake ? 3 : 2;
    steer = 0;
    /* B alone toggles self-drive and SELECT alone the handbrake, both on
     * release; pressing them together, in either order, toggles the lights. */
    if ((in & PRG32_BTN_B) && (in & PRG32_BTN_SELECT) && (pressed & (PRG32_BTN_B | PRG32_BTN_SELECT))) {
        combo_used = 1;
        if (battery > 0) lights = (uint8_t)!lights;
        else say("batteria scarica");
    }
    if (released & PRG32_BTN_B) {
        if (!combo_used) {
            auto_mode = (uint8_t)!auto_mode;
            say(auto_mode ? "SELF DRIVE ON" : "SELF DRIVE OFF");
        }
    } else if (released & PRG32_BTN_SELECT) {
        if (!combo_used) handbrake = (uint8_t)!handbrake;
    }
    if (!(in & (PRG32_BTN_B | PRG32_BTN_SELECT))) combo_used = 0;

    if (auto_mode) {
        int want = LANE_TOP_FOOT;
        if (pressed & PRG32_BTN_LEFT) gadget = (uint8_t)((gadget + GADGET_COUNT - 1) % GADGET_COUNT);
        if (pressed & PRG32_BTN_RIGHT) gadget = (uint8_t)((gadget + 1) % GADGET_COUNT);
        if (pressed & PRG32_BTN_A) fire_gadget();
        if (threat_ahead()) want = foot < LANE_MID_FOOT ? LANE_LOW_FOOT : LANE_TOP_FOOT;
        if (foot < want - 1) { foot += 2; steer = 1; }
        else if (foot > want + 1) { foot -= 2; steer = -1; }
        if (!handbrake && fuel > 0) {
            if (speed < SPEED_AUTO) speed += 2;
            else if (speed > SPEED_AUTO && !boost) speed--;
        }
    } else {
        if (in & PRG32_BTN_UP) { foot -= lane_step; steer = -1; }
        if (in & PRG32_BTN_DOWN) { foot += lane_step; steer = 1; }
        if (!handbrake && fuel > 0) {
            if (in & PRG32_BTN_RIGHT) { if (speed < SPEED_CRUISE) speed += 2; }
            else if (speed > 28 && !boost && (tick_no & 3) == 0) speed--;
        }
        if ((in & PRG32_BTN_LEFT) && speed > 8) speed -= 4;
        if ((pressed & PRG32_BTN_A) && turbo >= 25 && fuel > 0 && !handbrake) {
            turbo -= 25;
            boost = 30;
            score += 15;
            sfx(V_FX, I_ZAP, 72, 210, -30, 8);
        }
    }
    foot = clampi(foot, FOOT_MIN, FOOT_MAX);

    if (boost) {
        boost--;
        if (speed < SPEED_TURBO) speed += 6;
    } else if (speed > SPEED_CRUISE) {
        speed -= 3;
    }
    if (handbrake) {
        if (speed > 0) speed -= speed > 6 ? 6 : speed;
        if ((in & PRG32_BTN_RIGHT) && !message_timer) { say("ah il freno a mano"); chime(2); }
    }
    if (fuel <= 0 && speed > 0) speed -= speed > 2 ? 2 : speed;
}

static void systems(void) {
    int dark = stage_is_dark(stage), want_dim;
    world_x += (uint32_t)speed;
    fuel_bank += speed + (boost ? speed : 0);
    while (fuel_bank >= 220) {
        fuel_bank -= 220;
        if (fuel > 0) fuel--;
    }
    if (lights) {
        if ((tick_no & 3) == 0 && battery > 0) battery--;
        if (battery == 0) { lights = 0; say("hai lasciato le luci accese"); chime(2); }
        else if (!dark && battery < 300 && tick_no % 240 == 0) { say("hai lasciato le luci accese"); chime(2); }
    } else if (speed > 0 && battery < 1000 && tick_no % 3 == 0) {
        battery++;                                       /* the dynamo recharges while driving unlit */
    }
    if (fuel > 0 && fuel < 200 && tick_no % 180 == 0) { say("ho sete"); chime(2); }
    if (turbo < 100 && tick_no % 6 == 0) turbo++;
    if (dark && !lights && !warned_dark && state == GS_PLAY) {
        warned_dark = 1;
        say("accendi le luci: SELECT+B");
    }
    want_dim = dark && !lights ? 5 : 16;
    if (dim != want_dim) { dim = (uint8_t)want_dim; palette_dirty = 1; }
    if (flash) { flash--; palette_dirty = 1; }
    if (invulnerable) invulnerable--;
    if (shake) shake--;
    if (cooldown) cooldown--;
    if ((stage_has_sea(stage) || stage == STAGE_COUNT - 1) && (tick_no & 7) == 0) palette_dirty = 1;
}

static void road_events(void) {
    int here = code_at(CAR_X + NR_CAR_W / 2, foot);
    int column = (scroll_px() + CAR_X + NR_CAR_W / 2) >> 4;
    if ((here == NR_CODE_PIECE || here == NR_CODE_PIECE2) && stage < SURFACE_STAGES) collect_piece();
    if (code_at(CAR_X + NR_CAR_W - 10, foot) == NR_CODE_RUBBLE) {
        if (!invulnerable) { say("attenzione ai sassi!"); chime(2); }
        crash(35);
    }
    /* A pump on the pavement serves the top lane as the car passes it. */
    if (map_code(column, 5) == NR_CODE_PUMP && foot <= LANE_TOP_FOOT + 4) {
        if (!pump_lock && fuel < 1000) {
            fuel = 1000;
            score += 50;
            pump_lock = 1;
            say("il pieno, grazie");
            chime(1);
        }
    } else {
        pump_lock = 0;
    }
}

static void scooters_tick(void) {
    int i, j, nearest = 1 << 30, nearest_x = 0, nearest_gang = 0;
    for (i = 0; i < MAX_SCOOTERS; i++) {
        scooter_t *s = &scooters[i];
        int x;
        if (!s->active) continue;
        if (s->stun) {
            s->stun--;
            s->rel -= speed;                             /* knocked over: left behind with the road */
        } else {
            s->rel += s->speed - speed;
            if (s->chaser && s->rel > 70 * 16 && s->speed > 40) s->speed = 30;       /* got ahead: now he blocks */
            if ((tick_no + (uint32_t)i * 17u) % 48u == 0)
                s->target = (int16_t)(s->chaser && s->rel < 0 ? foot : lane_foot((int)(rnd() % 3)));
            if (s->foot < s->target) s->foot++;
            else if (s->foot > s->target) s->foot--;
        }
        if (s->rel < -260 * 16 || s->rel > 760 * 16) { spawn_scooter(i); continue; }
        x = CAR_X + s->rel / 16;
        if (!s->stun && s->rel > -22 * 16 && s->rel < (NR_CAR_W - 6) * 16 && absi(s->foot - foot) < 8) {
            if (!invulnerable) { say("attenzione ai motorini!"); chime(2); }
            crash(50);
            s->stun = 60;
            s->rel += 30 * 16;
        }
        if (!s->stun && absi(x - CAR_X) < nearest) {
            nearest = absi(x - CAR_X);
            nearest_x = x;
            nearest_gang = s->gang;
        }
    }
    /* The nearest two-stroke buzzes from its side of the stereo image. */
    if (nearest < 150 && tick_no % 20 == 0 && !voice_timer[V_GANG - V_ENGINE])
        sfx(V_GANG, I_SCOOTER, 52 + nearest_gang * 3, 150 - nearest / 2, pan_for_x(nearest_x), 8);

    for (i = 0; i < MAX_SHOTS; i++) {
        shot_t *shot = &shots[i];
        if (!shot->life) continue;
        shot->life--;
        shot->rel += shot->kind == GADGET_RAUTI ? 10 * 16 : -speed;
        for (j = 0; j < MAX_SCOOTERS; j++) {
            scooter_t *s = &scooters[j];
            if (!s->active || s->stun || absi(shot->rel - s->rel) > 16 * 16 || absi(shot->foot - s->foot) > 9) continue;
            s->stun = (uint8_t)(shot->kind == GADGET_RAUTI ? 60 : shot->kind == GADGET_GRASSO ? 100 : 150);
            shot->life = 0;
            score += 100;
            sfx(V_GANG, I_CRASH, 70, 200, pan_for_x(CAR_X + s->rel / 16), 6);
            break;
        }
    }
}

static void play_tick(uint32_t in, uint32_t pressed, uint32_t released) {
    drive(in, pressed, released);
    systems();
    road_events();
    scooters_tick();
    if (fuel <= 0 && speed == 0) {
        music(TRACK_OVER);
        finish(GS_OVER);
        return;
    }
    if (scroll_px() >= stage_end) complete_stage();
}

/* One 33 ms simulation step. */
static void tick(uint32_t in, uint32_t pressed, uint32_t released) {
    tick_no++;
    if (message_timer) message_timer--;
    sound_tick();
    engine_tick();
    if (state == GS_TITLE) {
        world_x += 20;
        if ((tick_no & 7) == 0) hud_dirty = 1;           /* blink "PREMI A" */
        if (pressed & PRG32_BTN_A) reset_run();
    } else if (state == GS_INTRO) {
        if (fade < 16) { fade++; palette_dirty = 1; }
        if (--state_timer <= 0 || ((pressed & PRG32_BTN_A) && fade == 16)) {
            state = GS_PLAY;
            fade = 16;
            palette_dirty = clear_screen = 1;
        }
    } else if (state == GS_PLAY) {
        play_tick(in, pressed, released);
    } else if (state == GS_CLEAR) {
        world_x += (uint32_t)speed;
        if (++state_timer > 45) {
            if (fade) { fade--; palette_dirty = 1; }
            else start_stage(stage + 1);
        }
    } else if (state == GS_EGG) {
        if ((tick_no & 7) == 0) palette_dirty = 1;       /* the Egg pulses */
        if (pressed & (PRG32_BTN_A | PRG32_BTN_B)) {
            egg_taken = (uint8_t)((pressed & PRG32_BTN_A) != 0);
            score += egg_taken ? 5000u : 7500u;
            finish(GS_END);
            chime(0);
        }
    } else {
        if ((tick_no & 7) == 0) palette_dirty = 1;
        if (++state_timer > 30 && (pressed & PRG32_BTN_A)) goto_title();
    }
}

/* ------------------------------------------------------------------------ */
/* Cartridge entry points                                                   */
/* ------------------------------------------------------------------------ */
void naprider_init(void) {
    static const uint16_t named[8] = {0x0000, 0xffff, 0xf800, 0x07e0, 0x001f, 0xffe0, 0x07ff, 0xf81f};
    int i;
    setup_sprites();
    /* Text and HUD use the eight named colours; make sure an earlier
     * cartridge has not left something else in their palette entries. */
    for (i = 0; i < 8; i++) prg32_palette_set((uint8_t)i, named[i]);
    prg32_palette_set(IDX_PANEL, 0x0849);
    prg32_palette_set(IDX_BAR_OFF, 0x2945);
    prg32_palette_set(IDX_OIL, 0x18c3);
    prg32_palette_set(IDX_GOLD, 0xfdc0);
    prg32_band_set_game_info("napRider-napoli97 | A TURBO/GADGET | B AUTO | SELECT FRENO | SELECT+B LUCI");
    last_ms = prg32_ticks_ms();
    last_input = 0;
    goto_title();
}

void naprider_update(void) {
    uint32_t in = prg32_input_read(), pressed = in & ~last_input, released = last_input & ~in;
    uint32_t now = prg32_ticks_ms();
    int steps;
    ms_bank += (int32_t)(now - last_ms);
    last_ms = now;
    /* Run as many fixed steps as real time asks for, so a slow frame on the
     * board does not slow the car down. */
    steps = clampi(ms_bank / TICK_MS, 1, 4);
    ms_bank -= steps * TICK_MS;
    if (ms_bank > 4 * TICK_MS || ms_bank < -TICK_MS) ms_bank = 0;
    while (steps--) {
        tick(in, pressed, released);
        pressed = released = 0;
    }
    last_input = in;
}

/* ------------------------------------------------------------------------ */
/* Drawing                                                                  */
/* ------------------------------------------------------------------------ */
static void fill(int x, int y, int w, int h, int index) { prg32_gfx_rect_indexed(x, y, w, h, (uint8_t)index); }

static void panel(int x, int y, int w, int h, int border) {
    fill(x, y, w, h, border);
    fill(x + 2, y + 2, w - 4, h - 4, IDX_BLACK);
}

static void draw_backdrop(int shake_x) {
    int px = scroll_px(), band;
    if (!stage_has_sky(stage)) return;
    for (band = 0; band < NR_SKY_BANDS; band++) fill(0, TOP + band * 6, W, 6, IDX_SKY + band);
    if (stage == 4) {
        prg32_sprite_draw_indexed(W - 40 - ((px >> 4) % (W + NR_ISLE_W)) + shake_x, TOP + 4, &isle_sprite, 0);
    } else if (stage != 2) {                             /* no view of the volcano from the alleys */
        int x = W + 60 - ((px >> 4) % (W + NR_VES_W + 120));
        prg32_sprite_draw_indexed(x + shake_x, TOP + 8, &ves_sprite, 0);
    }
}

static void draw_tiles(int shake_x) {
    int row, col, px = scroll_px();
    int sparkle = (int)((tick_no >> 2) & 1);
    for (row = 0; row < NR_STAGE_H; row++) {
        /* Far rows move at an eighth of the road speed, district rows at a quarter. */
        int scroll = row < 3 ? px >> 3 : row < 5 ? px >> 2 : px;
        int first = scroll >> 4, x0 = -(scroll & 15) + shake_x;
        int y = TOP + row * NR_TILE_H;
        for (col = 0; col < W / NR_TILE_W + 2; col++) {
            int code = map_code(first + col, row);
            if (code == NR_CODE_SKY) continue;
            if (code == NR_CODE_PIECE && sparkle) code = NR_CODE_PIECE2;
            if (code == NR_CODE_ROOF_A || code == NR_CODE_ROOF_B || code == NR_CODE_PINE || code == NR_CODE_COLUMN)
                prg32_sprite_draw_indexed(x0 + col * NR_TILE_W, y, &cut_sprite, (uint32_t)code);
            else
                prg32_sprite_draw_indexed(x0 + col * NR_TILE_W, y, &tile_sprite, (uint32_t)code);
        }
    }
    if (shake_x > 0) fill(0, TOP, shake_x, BOTTOM - TOP, IDX_BLACK);
}

static void draw_car(int shake_x) {
    int frame = steer < 0 ? 2 : steer > 0 ? 3 : (int)((world_x >> 6) & 1);
    int x = CAR_X + shake_x, y = foot - NR_CAR_H + 1;
    if (stage_is_dark(stage) && lights) prg32_sprite_draw_indexed(x + NR_CAR_W - 4, y + 2, &beam_sprite, 0);
    if (invulnerable & 2) return;                        /* blink after a crash */
    prg32_sprite_draw_indexed(x, y, &car_sprite, (uint32_t)frame);
    if (lights) fill(x + NR_CAR_W - 5, y + 12, 3, 3, IDX_YELLOW);
    if (handbrake || (last_input & PRG32_BTN_LEFT)) fill(x + 2, y + 12, 2, 3, IDX_RED);
    if (boost) {                                         /* exhaust flame */
        fill(x - 6 - (int)(tick_no & 3), y + 17, 6, 2, IDX_YELLOW);
        fill(x - 3, y + 16, 3, 4, IDX_RED);
    }
}

static void draw_scooters(int shake_x, int behind_car) {
    int i;
    for (i = 0; i < MAX_SCOOTERS; i++) {
        const scooter_t *s = &scooters[i];
        int x = CAR_X + s->rel / 16 + shake_x;
        if (!s->active || (s->foot <= foot) != behind_car || x < -NR_SCOOT_W || x >= W) continue;
        if (s->stun && (tick_no & 2)) continue;
        prg32_sprite_draw_indexed(x, s->foot - NR_SCOOT_H + 1, &scoot_sprite[s->gang], (tick_no >> 2) & 1);
    }
}

static void draw_shots(int shake_x) {
    int i;
    for (i = 0; i < MAX_SHOTS; i++) {
        const shot_t *s = &shots[i];
        int x = CAR_X + s->rel / 16 + shake_x, y = s->foot - 4;
        if (!s->life || x < -12 || x >= W) continue;
        if (s->kind == GADGET_RAUTI) {
            fill(x, y - 6, 6, 3, IDX_RED);
            fill(x - 5, y - 5, 5, 1, IDX_YELLOW);
        } else if (s->kind == GADGET_GRASSO) {
            fill(x, y, 12, 3, IDX_OIL);
            fill(x + 2, y - 1, 8, 5, IDX_OIL);
            fill(x + 3, y, 2, 1, IDX_WHITE);
        } else {
            fill(x, y, 1, 2, IDX_WHITE);
            fill(x + 4, y + 2, 1, 2, IDX_WHITE);
            fill(x + 8, y - 1, 1, 2, IDX_WHITE);
        }
    }
}

static void draw_bar(int x, int y, int value, int max, int index) {
    int i, lit = (value * 8 + max - 1) / max;
    for (i = 0; i < 8; i++) fill(x + i * 5, y, 4, 7, i < lit ? index : IDX_BAR_OFF);
}

static void draw_hud(void) {
    int i;
    fill(0, 0, W, TOP, IDX_BLACK);
    fill(0, BOTTOM, W, 200 - BOTTOM, IDX_BLACK);
    if (state == GS_TITLE) {
        prg32_gfx_text8(4, 5, "NAPOLI 1997", C_YELLOW, C_BLACK);
        prg32_gfx_text8(196, 5, "RECORD", C_WHITE, C_BLACK);
        text_number(252, 5, best_score, 6, C_CYAN);
        text_centre(185, "TRA MITO, STORIA E ASFALTO", C_CYAN);
        return;
    }
    prg32_gfx_text8(4, 5, "SC", C_WHITE, C_BLACK);
    text_number(24, 5, score, 6, C_WHITE);
    prg32_gfx_text8(84, 5, "F", C_YELLOW, C_BLACK);
    draw_bar(96, 5, fuel, 1000, fuel < 200 ? IDX_RED : IDX_GREEN);
    prg32_gfx_text8(148, 5, "B", C_CYAN, C_BLACK);
    draw_bar(160, 5, battery, 1000, IDX_CYAN);
    prg32_gfx_text8(212, 5, "L", lights ? C_YELLOW : C_WHITE, C_BLACK);
    fill(222, 6, 6, 6, lights ? IDX_YELLOW : IDX_BAR_OFF);
    for (i = 0; i < SURFACE_STAGES; i++)                 /* the mosaic */
        fill(244 + i * 14, 4, 10, 10, (piece_mask & (1u << i)) ? IDX_GOLD : IDX_BAR_OFF);
    prg32_gfx_text8(4, 185, auto_mode ? "AUTO" : "MAN ", auto_mode ? C_GREEN : C_WHITE, C_BLACK);
    prg32_gfx_text8(44, 185, handbrake ? "FRENO " : gadget_name(gadget), handbrake ? C_RED : C_YELLOW, C_BLACK);
    prg32_gfx_text8(100, 185, "T", C_WHITE, C_BLACK);
    draw_bar(112, 185, turbo, 100, IDX_RED);
    prg32_gfx_text8(164, 185, stage_name(stage), C_WHITE, C_BLACK);
    text_number(288, 185, (uint32_t)stage + 1, 1, C_YELLOW);
    prg32_gfx_text8(296, 185, "/6", C_WHITE, C_BLACK);
}

/* The HUD bands are never overdrawn by the playfield, so they are redrawn
 * only when something they show changes. */
static void refresh_hud(void) {
    uint32_t sig = score * 31u + (uint32_t)((fuel + 124) / 125) + (uint32_t)((battery + 124) / 125) * 16u +
                   (uint32_t)((turbo + 12) / 13) * 256u + (uint32_t)lights * 4096u + (uint32_t)auto_mode * 8192u +
                   (uint32_t)gadget * 16384u + (uint32_t)piece_mask * 65536u + (uint32_t)handbrake * (1u << 22) +
                   (uint32_t)stage * (1u << 23) + (uint32_t)(fuel < 200) * (1u << 27);
    if (!hud_dirty && sig == hud_signature) return;
    hud_signature = sig;
    hud_dirty = 0;
    draw_hud();
}

static void draw_message(void) {
    int w;
    if (!message_timer) return;
    w = text_len(message) * 8 + 16;
    panel((W - w) / 2, TOP + 3, w, 18, IDX_CYAN);
    text_centre(TOP + 8, message, C_WHITE);
}

static void draw_overlays(void) {
    if (state == GS_TITLE) {
        panel(52, 40, 216, 62, IDX_GOLD);
        text_centre(48, "n a p R i d e r", C_WHITE);
        text_centre(60, "- napoli97 -", C_YELLOW);
        text_centre(74, "UNA PICCOLA 500", C_CYAN);
        text_centre(84, "PER GRANDI AVVENTURE", C_CYAN);
        if (tick_no & 16) {
            panel(108, 148, 104, 16, IDX_CYAN);
            text_centre(152, "PREMI A", C_WHITE);
        }
    } else if (state == GS_INTRO) {
        char label[8];
        label[0] = (char)('1' + stage); label[1] = ' '; label[2] = 'D'; label[3] = 'I'; label[4] = ' ';
        label[5] = '6'; label[6] = 0;
        panel(24, 44, 272, 46, IDX_GOLD);
        text_centre(50, label, C_YELLOW);
        text_centre(62, stage_name(stage), C_WHITE);
        text_centre(76, stage_hint(stage), C_CYAN);
    } else if (state == GS_EGG) {
        panel(44, 44, 232, 44, IDX_GOLD);
        text_centre(50, "L'UOVO DI VIRGILIO", C_YELLOW);
        text_centre(62, "NON E' SOLO UN UOVO", C_WHITE);
        text_centre(74, "A PRENDI     B LASCIA", C_CYAN);
    } else if (state == GS_END) {
        panel(36, 44, 248, 56, IDX_GOLD);
        text_centre(50, egg_taken ? "HAI PRESO L'UOVO" : "HAI LASCIATO L'UOVO", C_YELLOW);
        text_centre(62, egg_taken ? "NAPOLI TRATTIENE IL FIATO" : "NAPOLI RESTA IN EQUILIBRIO", C_WHITE);
        prg32_gfx_text8(92, 74, "PUNTI", C_CYAN, C_BLACK);
        text_number(140, 74, score, 6, C_WHITE);
        text_centre(86, "A - TITOLO", C_GREEN);
    } else if (state == GS_OVER) {
        panel(60, 44, 200, 46, IDX_RED);
        text_centre(50, "SENZA BENZINA", C_RED);
        prg32_gfx_text8(92, 62, "PUNTI", C_CYAN, C_BLACK);
        text_number(140, 62, score, 6, C_WHITE);
        text_centre(74, "A - TITOLO", C_GREEN);
    }
}

void naprider_draw(void) {
    int shake_x = shake ? ((shake & 1) ? 3 : -3) : 0;
    if (clear_screen) {
        prg32_gfx_clear_indexed(IDX_BLACK);
        clear_screen = 0;
        hud_dirty = 1;
    }
    if (palette_dirty) palette_apply();
    draw_backdrop(shake_x);
    draw_tiles(shake_x);
    if (state != GS_TITLE) {
        draw_shots(shake_x);
        draw_scooters(shake_x, 1);
    }
    if (state == GS_EGG || state == GS_END) prg32_sprite_draw_indexed(216, LANE_MID_FOOT - NR_EGG_H + 4, &egg_sprite, 0);
    draw_car(shake_x);
    if (state != GS_TITLE) draw_scooters(shake_x, 0);
    draw_message();
    draw_overlays();
    refresh_hud();
    prg32_gfx_present();
}
