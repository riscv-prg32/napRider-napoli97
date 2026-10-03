/*
 * Host harness for napRider-napoli97.
 *
 * It includes the cartridge source and supplies the PRG32 calls with a
 * software model of both display back ends at once:
 *
 *   - `rgb`  : QEMU's RGB565 surface, where an indexed sprite writes its own
 *              palette colours and indexed primitives look the palette up;
 *   - `idx`  : the ESP32-C6 8-bit framebuffer, where every sprite colour is
 *              mapped to a 6x6x6 system-cube cell and expanded through the
 *              system palette when the frame is presented.
 *
 * A bot then plays the whole game. The harness asserts that the two back ends
 * show identical pixels in normal play, that nothing draws out of budget,
 * that the campaign can be finished, and that the failure paths work. With
 * NAPRIDER_SHOTS=<dir> it also dumps frames as PPM for tools/render_screens.py.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/game.c"
#include "font8.h"

#define FB_W 320
#define FB_H 200

static uint16_t rgb[FB_W * FB_H];
static uint8_t idx[FB_W * FB_H];
static uint16_t sys_pal[256];
static uint32_t pad, clock_ms, frames, sprite_draws, max_sprite_draws, prim_draws;
static int notes_on[8], note_events, track_now = -1, tracks_started;
static uint32_t submitted_score;
static int submissions;
static const char *shot_dir;

/* ---- the firmware's palette model -------------------------------------- */
static uint16_t default_colour(unsigned i) {
    static const uint16_t named[16] = {0x0000, 0xffff, 0xf800, 0x07e0, 0x001f, 0xffe0, 0x07ff, 0xf81f,
                                       0x8410, 0xc618, 0x8000, 0x0400, 0x0010, 0x8400, 0x0410, 0x8010};
    unsigned v, gray;
    if (i < 16) return named[i];
    if (i < 232) {
        v = i - 16;
        return (uint16_t)((((v / 36) * 31 / 5) << 11) | ((((v / 6) % 6) * 63 / 5) << 5) | ((v % 6) * 31 / 5));
    }
    gray = (i - 232) * 255 / 23;
    return (uint16_t)(((gray * 31 / 255) << 11) | ((gray * 63 / 255) << 5) | (gray * 31 / 255));
}

static uint8_t index_for(uint16_t c) {
    unsigned i;
    for (i = 0; i < 8; i++) if (c == default_colour(i)) return (uint8_t)i;
    return (uint8_t)(16 + ((c >> 11) * 5 / 31) * 36 + (((c >> 5) & 63) * 5 / 63) * 6 + ((c & 31) * 5 / 31));
}

static void put(int x, int y, uint16_t colour, uint8_t index) {
    if (x < 0 || y < 0 || x >= FB_W || y >= FB_H) return;
    rgb[y * FB_W + x] = colour;
    idx[y * FB_W + x] = index;
}

/* ---- PRG32 calls -------------------------------------------------------- */
uint32_t prg32_input_read(void) { return pad; }
uint32_t prg32_ticks_ms(void) { return clock_ms; }
void prg32_band_set_game_info(const char *text) { assert(strlen(text) < 96); }

void prg32_audio_play_track(uint16_t track_id) { assert(track_id < 8); track_now = track_id; tracks_started++; }
void prg32_audio_stop_track(void) { track_now = -1; }
void prg32_audio_note_on_pan(uint8_t channel, uint8_t instrument, uint8_t note, uint8_t volume, int8_t pan) {
    assert(channel >= 4 && channel < 8);              /* voices 0-3 belong to the tracker */
    assert(instrument >= 4 && instrument < 10 && note > 0 && note < 128 && volume > 0);
    assert(pan >= -64 && pan <= 63);
    notes_on[channel] = 1;
    note_events++;
}
void prg32_audio_note_off(uint8_t channel) { assert(channel < 8); notes_on[channel] = 0; }

int prg32_score_count(const char *game) { assert(!strcmp(game, "naprider")); return submissions ? 1 : 0; }
int prg32_score_get(const char *game, int index, prg32_score_t *out) {
    (void)game;
    if (index != 0 || !submissions) return -1;
    memset(out, 0, sizeof(*out));
    out->score = submitted_score;
    return 0;
}
int prg32_score_submit_current_player(const char *game, uint32_t value) {
    assert(!strcmp(game, "naprider"));
    if (value > submitted_score) submitted_score = value;
    submissions++;
    return 0;
}

void prg32_palette_set(uint8_t index, uint16_t colour) {
    assert(index >= 16 || colour == default_colour(index));    /* the eight named colours keep their values */
    sys_pal[index] = colour;
}
void prg32_gfx_rect_indexed(int x, int y, int w, int h, uint8_t index) {
    int i, j;
    assert(w > 0 && h > 0 && w <= FB_W && h <= FB_H);
    assert(index < 8 || index >= 232);                 /* never a cube cell the art may have reprogrammed */
    prim_draws++;
    for (j = 0; j < h; j++) for (i = 0; i < w; i++) put(x + i, y + j, sys_pal[index], index);
}
void prg32_gfx_clear_indexed(uint8_t index) { prg32_gfx_rect_indexed(0, 0, FB_W, FB_H, index); }
void prg32_gfx_text8(int x, int y, const char *s, uint16_t fg, uint16_t bg) {
    assert(index_for(fg) < 8 && index_for(bg) < 8);   /* text uses exact named colours only */
    assert(x >= 0 && y >= 0 && y + 8 <= FB_H && x + (int)strlen(s) * 8 <= FB_W);
    for (; *s; s++, x += 8) {
        unsigned ch = (unsigned char)*s;
        int row, col;
        assert(ch >= 32 && ch < 127);
        for (row = 0; row < 8; row++)
            for (col = 0; col < 8; col++) {
                uint16_t c = (harness_font8[ch - 32][row] & (0x80u >> col)) ? fg : bg;
                put(x + col, y + row, c, index_for(c));
            }
    }
    prim_draws++;
}
void prg32_sprite_draw_indexed(int x, int y, const prg32_indexed_sprite_t *s, uint32_t frame) {
    unsigned bpp = s->bits_per_pixel, px, py;
    size_t frame_bits = (size_t)s->width * s->height * bpp;
    const uint8_t *data;
    assert(bpp == 1 || bpp == 2 || bpp == 4);
    assert(s->palette_count <= (1u << bpp) && s->transparent_index < (int)s->palette_count);
    assert(x > -400 && x < 720 && y > -200 && y < 400);
    frame %= s->frame_count;
    data = s->pixels + frame * ((frame_bits + 7) / 8);
    sprite_draws++;
    for (py = 0; py < s->height; py++)
        for (px = 0; px < s->width; px++) {
            size_t bit = ((size_t)py * s->width + px) * bpp;
            unsigned v = (data[bit / 8] >> (8 - bpp - bit % 8)) & ((1u << bpp) - 1);
            if (v >= s->palette_count || (int)v == s->transparent_index) continue;
            put(x + (int)px, y + (int)py, s->palette[v], index_for(s->palette[v]));
        }
}

static int backends_differ(void) {
    int i, n = 0;
    for (i = 0; i < FB_W * FB_H; i++)
        if (sys_pal[idx[i]] != rgb[i]) {
            if (!n) fprintf(stderr, "first at (%d,%d): QEMU %04x, ESP32-C6 entry %u = %04x\n", i % FB_W, i / FB_W,
                            (unsigned)rgb[i], (unsigned)idx[i], (unsigned)sys_pal[idx[i]]);
            n++;
        }
    return n;
}

static void dump(const char *name) {
    char path[512];
    FILE *f;
    int i;
    if (!shot_dir) return;
    snprintf(path, sizeof(path), "%s/%s.ppm", shot_dir, name);
    f = fopen(path, "wb");
    assert(f);
    fprintf(f, "P6\n%d %d\n255\n", FB_W, FB_H);
    for (i = 0; i < FB_W * FB_H; i++) {
        uint16_t c = sys_pal[idx[i]];                  /* what the ESP32-C6 panel shows */
        fputc((c >> 11) * 255 / 31, f);
        fputc(((c >> 5) & 63) * 255 / 63, f);
        fputc((c & 31) * 255 / 31, f);
    }
    fclose(f);
}

void prg32_gfx_present(void) {
    int normal = fade == 16 && dim == 16 && flash == 0;
    frames++;
    if (sprite_draws > max_sprite_draws) max_sprite_draws = sprite_draws;
    assert(sprite_draws <= 260 && prim_draws <= 120);
    /* The authored colours must reach both displays unchanged. */
    if (normal && frames > 1) {
        int bad = backends_differ();
        if (bad) {
            fprintf(stderr, "frame %u state %d stage %d: %d pixels differ between ESP32-C6 and QEMU\n",
                    (unsigned)frames, (int)state, stage, bad);
            dump("mismatch");
            exit(1);
        }
    }
    sprite_draws = prim_draws = 0;
}

/* ---- driving ------------------------------------------------------------ */
static void frame(uint32_t buttons) {
    pad = buttons;
    clock_ms += TICK_MS;
    naprider_update();
    naprider_draw();
}

static void frames_n(uint32_t buttons, int n) { while (n--) frame(buttons); }
static void tap(uint32_t buttons) { frame(buttons); frame(0); }

/* A patient driver: fetches the fragment, refuels, dodges, lights the tunnel. */
static uint32_t bot(void) {
    uint32_t in = PRG32_BTN_RIGHT;
    int want = LANE_MID_FOOT, i, look;
    int px = scroll_px(), row;
    if (stage_is_dark(stage) && !lights && battery > 0 && !(last_input & PRG32_BTN_SELECT))
        return PRG32_BTN_B | PRG32_BTN_SELECT;
    if (fuel < 700)
        for (look = 0; look < 14; look++)
            if (map_code(((px + CAR_X) >> 4) + look, 5) == NR_CODE_PUMP) want = LANE_TOP_FOOT;
    if (stage < SURFACE_STAGES && !(piece_mask & (1u << stage)))
        for (look = 0; look < 12; look++)
            for (row = 6; row <= 8; row++)
                if (map_code(((px + CAR_X) >> 4) + look, row) == NR_CODE_PIECE) want = lane_foot(row - 6);
    /* Step aside for whatever is in the wanted lane. */
    for (i = 0; i < 3; i++) {
        int blocked = 0, j, x;
        for (j = 0; j < MAX_SCOOTERS; j++)
            if (scooters[j].active && !scooters[j].stun && scooters[j].rel > -30 * 16 && scooters[j].rel < 120 * 16 &&
                absi(scooters[j].foot - want) < 14) blocked = 1;
        for (x = 0; x <= NR_CAR_W + 64; x += 16)
            if (code_at(CAR_X + x, want) == NR_CODE_RUBBLE) blocked = 1;
        if (!blocked) break;
        want = want == LANE_MID_FOOT ? LANE_LOW_FOOT : want == LANE_LOW_FOOT ? LANE_TOP_FOOT : LANE_MID_FOOT;
    }
    if (foot < want - 1) in |= PRG32_BTN_DOWN;
    if (foot > want + 1) in |= PRG32_BTN_UP;
    return in;
}

static void play_campaign(void) {
    int guard, shot_stage = -1;
    char name[32];
    frames_n(0, 40);
    assert(state == GS_TITLE && track_now == 0);
    dump("01-title");
    tap(PRG32_BTN_A);
    assert(state == GS_INTRO && score == 0 && fuel == 1000);
    frames_n(0, 30);
    dump("02-intro");
    for (guard = 0; guard < 60000 && state != GS_EGG && state != GS_OVER; guard++) {
        frame(state == GS_PLAY ? bot() : 0);
        if (state == GS_PLAY && shot_stage != stage && scroll_px() > 700 && fade == 16 && dim == 16 && !flash &&
            !invulnerable) {
            shot_stage = stage;
            snprintf(name, sizeof(name), "%02d-%s", 3 + stage, stage == 0 ? "centro-storico" : stage == 1 ? "posillipo" :
                     stage == 2 ? "quartieri" : stage == 3 ? "vomero" : stage == 4 ? "virgiliano" : "sotterranea");
            dump(name);
            assert(track_now == stage);
        }
    }
    printf("campaign: %d frames, state %d, stage %d, fuel %d, score %u\n", guard, (int)state, stage, fuel, (unsigned)score);
    assert(state == GS_EGG && stage == STAGE_COUNT - 1);
    assert(piece_mask == 0x1f && track_now == TRACK_EGG);
    frames_n(0, 20);
    dump("09-egg");
    {
        uint32_t before = score;
        tap(PRG32_BTN_B);                              /* leave the Egg where it is */
        assert(state == GS_END && !egg_taken && score == before + 7500);
    }
    assert(submissions == 1 && submitted_score == score);
    frames_n(0, 40);
    dump("10-ending");
    tap(PRG32_BTN_A);
    assert(state == GS_TITLE && best_score == submitted_score);
}

static void start_run(void) {
    if (state != GS_TITLE) goto_title();
    frame(0);
    tap(PRG32_BTN_A);
    frames_n(0, 80);
    assert(state == GS_PLAY);
}

static void check_controls(void) {
    start_run();
    /* SELECT+B toggles the headlights in either press order, without also
     * flipping self-drive or the handbrake. */
    frame(PRG32_BTN_SELECT); frame(PRG32_BTN_SELECT | PRG32_BTN_B); frame(0);
    assert(lights == 1 && !auto_mode && !handbrake);
    frame(PRG32_BTN_B); frame(PRG32_BTN_SELECT | PRG32_BTN_B); frame(PRG32_BTN_SELECT); frame(0);
    assert(lights == 0 && !auto_mode && !handbrake);
    tap(PRG32_BTN_B);
    assert(auto_mode == 1);
    frames_n(0, 60);
    assert(speed == SPEED_AUTO);                       /* self-drive holds its own speed */
    tap(PRG32_BTN_RIGHT);
    assert(gadget == GADGET_GRASSO);
    tap(PRG32_BTN_A);
    assert(shots[0].life && shots[0].kind == GADGET_GRASSO && notes_on[V_FX]);
    frames_n(0, 12);
    assert(!notes_on[V_FX]);                           /* effect notes are released, not left droning */
    tap(PRG32_BTN_B);
    assert(auto_mode == 0);
    tap(PRG32_BTN_SELECT);
    assert(handbrake == 1);
    frames_n(PRG32_BTN_RIGHT, 30);
    assert(speed == 0);
    tap(PRG32_BTN_SELECT);
    frames_n(PRG32_BTN_RIGHT | PRG32_BTN_DOWN, 60);
    assert(foot == FOOT_MAX && speed == SPEED_CRUISE);
    frames_n(PRG32_BTN_UP, 60);
    assert(foot == FOOT_MIN);
    {
        int before = turbo;
        tap(PRG32_BTN_A);
        assert(boost && turbo < before);
        frames_n(PRG32_BTN_RIGHT, 12);
        assert(speed > SPEED_CRUISE);
    }
}

static void check_rules(void) {
    int i;
    /* A district without its fragment loops instead of ending. */
    start_run();
    for (i = 0; i < MAX_SCOOTERS; i++) scooters[i].active = 0;
    foot = LANE_TOP_FOOT;                              /* Centro's fragment lies in the middle lane */
    world_x = (uint32_t)(STAGE_PX - 4) * 16;
    frames_n(PRG32_BTN_RIGHT, 30);
    assert(state == GS_PLAY && stage == 0 && stage_end == 2 * STAGE_PX);

    /* A rider in the way costs fuel and speed, once. */
    start_run();
    for (i = 1; i < MAX_SCOOTERS; i++) scooters[i].active = 0;
    scooters[0].active = 1; scooters[0].stun = 0; scooters[0].chaser = 0; scooters[0].speed = 0;
    scooters[0].rel = 60 * 16; scooters[0].foot = scooters[0].target = (int16_t)foot;
    frames_n(PRG32_BTN_RIGHT, 40);
    assert(fuel < 960 && fuel > 900 && scooters[0].stun);
    dump("11-crash");

    /* An unlit tunnel is dark; the lights bring the colours back. */
    start_run();
    start_stage(3);
    frames_n(0, 90);
    assert(state == GS_PLAY && dim == 5);
    dump("12-vomero-unlit");
    frame(PRG32_BTN_SELECT | PRG32_BTN_B); frame(0);
    assert(lights && dim == 16);

    /* Lights drain the battery and switch themselves off when it is flat. */
    battery = 2;
    frames_n(PRG32_BTN_RIGHT, 20);
    assert(!lights && battery < 10);            /* flat, then the dynamo starts recharging */

    /* Running dry ends the run instead of freezing it, and the score is kept. */
    start_run();
    for (i = 0; i < MAX_SCOOTERS; i++) scooters[i].active = 0;
    submissions = 0;
    fuel = 1;
    frames_n(PRG32_BTN_RIGHT, 300);
    assert(state == GS_OVER && track_now == TRACK_OVER && submissions == 1);
    dump("13-senza-benzina");
    frames_n(0, 40);
    tap(PRG32_BTN_A);
    assert(state == GS_TITLE);

    /* Taking the Egg is the other ending. */
    start_run();
    piece_mask = 0x1f;
    start_stage(STAGE_COUNT - 1);
    frames_n(0, 90);
    lights = 1;
    world_x = (uint32_t)(STAGE_PX - 2) * 16;
    foot = LANE_TOP_FOOT;
    frames_n(PRG32_BTN_RIGHT, 20);
    assert(state == GS_EGG);
    tap(PRG32_BTN_A);
    assert(state == GS_END && egg_taken);
}

int main(void) {
    unsigned i;
    shot_dir = getenv("NAPRIDER_SHOTS");
    for (i = 0; i < 256; i++) sys_pal[i] = default_colour(i);
    for (i = 0; i < 8; i++) sys_pal[i] = 0x1234;       /* as if another cartridge had left its palette behind */
    clock_ms = 1000;
    naprider_init();
    play_campaign();
    check_controls();
    check_rules();
    assert(tracks_started > 8 && note_events > 50);
    printf("OK: %u frames, both display back ends identical, at most %u sprite draws per frame\n",
           (unsigned)frames, (unsigned)max_sprite_draws);
    return 0;
}
