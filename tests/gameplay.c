#include <assert.h>
#include "../src/game.c"

uint32_t prg32_input_read(void) { return 0; }
void prg32_band_set_game_info(const char *s) { (void)s; }
void prg32_audio_play_track(uint16_t t) { (void)t; }
void prg32_audio_note_on_pan(uint8_t v, uint8_t i, uint8_t n, uint8_t vel, int8_t p)
{ (void)v; (void)i; (void)n; (void)vel; (void)p; }
void prg32_gfx_clear(uint16_t c) { (void)c; }
void prg32_gfx_present(void) {}
void prg32_gfx_rect(int x, int y, int w, int h, uint16_t c)
{ (void)x; (void)y; (void)w; (void)h; (void)c; }
void prg32_gfx_text8(int x, int y, const char *s, uint16_t f, uint16_t b)
{ (void)x; (void)y; (void)s; (void)f; (void)b; }
void prg32_sprite_draw_indexed(int x, int y, const prg32_indexed_sprite_t *s, uint16_t f)
{ (void)x; (void)y; (void)s; (void)f; }

int main(void)
{
    reset_run();
    stage_progress=540; lane=-34; speed=1; fuel=500;
    update_play(0,0);
    assert(fuel==1000 && score==25 && checkpoint_used);
    update_play(0,0);
    assert(score==25);

    stage_progress=STAGE_LENGTH-1;
    update_play(0,0);
    assert(stage==1 && !checkpoint_used);

    handbrake=1; lane=44; speed=1;
    update_play(PRG32_BTN_RIGHT,0);
    assert(lane==44);
    assert(steer==1 && car_frame()==1);
    handbrake=0;
    update_play(0,0);
    assert(steer==0 && car_frame()==0);
    return 0;
}
