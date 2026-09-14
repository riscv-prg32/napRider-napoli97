#ifndef PRG32_H
#define PRG32_H
#include <stdint.h>
#define PRG32_BTN_A (1u<<0)
#define PRG32_BTN_B (1u<<1)
#define PRG32_BTN_UP (1u<<2)
#define PRG32_BTN_DOWN (1u<<3)
#define PRG32_BTN_LEFT (1u<<4)
#define PRG32_BTN_RIGHT (1u<<5)
#define PRG32_BTN_SELECT (1u<<6)
typedef struct { const uint8_t *pixels; const uint16_t *palette; uint16_t width,height,frame_count,palette_count; uint8_t bits_per_pixel; int16_t transparent_index; } prg32_indexed_sprite_t;
uint32_t prg32_input_read(void);
void prg32_band_set_game_info(const char *s);
void prg32_audio_play_track(uint16_t t);
void prg32_audio_note_on_pan(uint8_t voice,uint8_t instrument,uint8_t note,uint8_t velocity,int8_t pan);
void prg32_gfx_clear(uint16_t c);
void prg32_gfx_present(void);
void prg32_gfx_rect(int x,int y,int w,int h,uint16_t c);
void prg32_gfx_text8(int x,int y,const char *s,uint16_t fg,uint16_t bg);
void prg32_sprite_draw_indexed(int x,int y,const prg32_indexed_sprite_t *sprite,uint16_t frame);
#endif
