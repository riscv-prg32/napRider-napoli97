/* Minimal host-side copy of the PRG32 declarations this cartridge uses.
 * Constants and layouts mirror components/prg32/include/prg32.h; the real
 * headers stay authoritative and this file is never packed into a cartridge. */
#ifndef PRG32_H
#define PRG32_H
#include <stddef.h>
#include <stdint.h>

#define PRG32_BTN_LEFT (1u << 0)
#define PRG32_BTN_RIGHT (1u << 1)
#define PRG32_BTN_UP (1u << 2)
#define PRG32_BTN_DOWN (1u << 3)
#define PRG32_BTN_A (1u << 4)
#define PRG32_BTN_B (1u << 5)
#define PRG32_BTN_START (1u << 6)
#define PRG32_BTN_SELECT PRG32_BTN_START

#define PRG32_COLOR_BLACK 0x0000
#define PRG32_COLOR_WHITE 0xffff
#define PRG32_COLOR_RED 0xf800
#define PRG32_COLOR_GREEN 0x07e0
#define PRG32_COLOR_BLUE 0x001f
#define PRG32_COLOR_YELLOW 0xffe0
#define PRG32_COLOR_CYAN 0x07ff
#define PRG32_COLOR_MAGENTA 0xf81f

typedef struct {
    const uint8_t *pixels;
    const uint16_t *palette;
    uint16_t width;
    uint16_t height;
    uint16_t frame_count;
    uint16_t palette_count;
    uint8_t bits_per_pixel;
    int16_t transparent_index;
} prg32_indexed_sprite_t;

typedef struct {
    char game[24];
    char player[24];
    uint32_t score;
} prg32_score_t;

uint32_t prg32_input_read(void);
uint32_t prg32_ticks_ms(void);
void prg32_band_set_game_info(const char *text);

void prg32_audio_play_track(uint16_t track_id);
void prg32_audio_stop_track(void);
void prg32_audio_note_on_pan(uint8_t channel, uint8_t instrument, uint8_t note, uint8_t volume, int8_t pan);
void prg32_audio_note_off(uint8_t channel);

int prg32_score_count(const char *game);
int prg32_score_get(const char *game, int index, prg32_score_t *out_score);
int prg32_score_submit_current_player(const char *game, uint32_t score);

void prg32_gfx_clear_indexed(uint8_t index);
void prg32_gfx_present(void);
void prg32_gfx_rect_indexed(int x, int y, int w, int h, uint8_t index);
void prg32_palette_set(uint8_t index, uint16_t rgb565);
void prg32_gfx_text8(int x, int y, const char *s, uint16_t fg, uint16_t bg);
void prg32_sprite_draw_indexed(int x, int y, const prg32_indexed_sprite_t *sprite, uint32_t frame);
#endif
