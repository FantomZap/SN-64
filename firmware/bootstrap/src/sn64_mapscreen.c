// SPDX-License-Identifier: GPL-3.0-or-later
#include "sn64_mapscreen.h"

#include <stdio.h>

// ---- where things are on the 320 x 240 screen (16 pixels kept free left and right)
#define X_LEFT     16               // the left half: the player's controller
#define X_RIGHT    164              // the right half: what the game sees, and the mapping under it
#define X_END      303              // the last pixel of the right half
#define Y_LIST     8                // the two list boxes: each names the controller drawn under it
#define LIST_H     13
#define LINE_H     11               // a line of an open list
#define Y_PAD      23               // the two pictures
#define Y_ROWS     96               // the rows of the list, under the Super NES controller
#define ROW_H      12
#define Y_TIP      163              // under the player's controller: the menu shortcut, in three lines
#define Y_NOTE     202              // and one line of notes
#define Y_FOOT     224              // the reset field and the help text
#define CHOICE_ROWS 7               // the choices for a button: two columns of seven and six
#define CHOICE_W   69
#define CHOICE_H   13

#define COL_TEXT   sn64_rgb(0xE0, 0xE0, 0xE0)
#define COL_DIM    sn64_rgb(0x80, 0x88, 0x98)
#define COL_HI     sn64_rgb(0xFF, 0xD8, 0x40)
#define COL_WARN   sn64_rgb(0xFF, 0x60, 0x50)
#define COL_BAR    sn64_rgb(0x28, 0x40, 0x80)   // behind the line the cursor is on
#define COL_BOX    sn64_rgb(0x08, 0x0C, 0x1C)   // inside a list box
#define COL_PANEL  sn64_rgb(0x18, 0x24, 0x48)   // behind the choices

void sn64_mapscreen_init(sn64_mapscreen_t *s, unsigned input_pad, unsigned snes_pad)
{
    s->input_pad = (uint8_t)(input_pad < SN64_PAD_INPUT_COUNT ? input_pad : 0);
    s->snes_pad = (uint8_t)(snes_pad < SN64_PAD_SNES_COUNT ? snes_pad : 0);
    sn64_mapscreen_open(s);
}

void sn64_mapscreen_open(sn64_mapscreen_t *s)
{
    s->col = 0;
    s->row = 0;
    s->first = 0;
    s->open = SN64_MS_CLOSED;
    s->pick = 0;
    s->b_armed = false;
    s->restored = false;
}

int sn64_mapscreen_entry(const sn64_mapscreen_t *s)
{
    if (s->row == SN64_MS_ROW_STICK)
        return SN64_IN_STICK;
    return (s->row > 0 && s->row < SN64_MS_LIST_ROWS) ? s->row - 1 : -1;
}

static int wrap(int v, int n)
{
    return ((v % n) + n) % n;
}

// The choices for a button stand in two columns: seven in the first, the other six in the second.
static int choice_column_length(int col)
{
    return col ? SN64_MAP_CHOICES - CHOICE_ROWS : CHOICE_ROWS;
}

bool sn64_mapscreen_input(sn64_mapscreen_t *s, sn64_map_t *map, uint16_t pressed, uint16_t released)
{
    bool up = (pressed & N64_BTN_D_UP) != 0, down = (pressed & N64_BTN_D_DOWN) != 0;
    bool left = (pressed & N64_BTN_D_LEFT) != 0, right = (pressed & N64_BTN_D_RIGHT) != 0;
    bool a = (pressed & N64_BTN_A) != 0, b = (pressed & N64_BTN_B) != 0;
    bool leave = false;

    if (released & N64_BTN_B) {
        leave = s->b_armed && s->open == SN64_MS_CLOSED;
        s->b_armed = false;
    }
    if (pressed)
        s->restored = false;

    if (s->open == SN64_MS_LIST_INPUT || s->open == SN64_MS_LIST_SNES || s->open == SN64_MS_STICK) {
        // one column: the controllers, or what the stick does
        int n = s->open == SN64_MS_LIST_INPUT ? SN64_PAD_INPUT_COUNT :
                s->open == SN64_MS_LIST_SNES  ? SN64_PAD_SNES_COUNT : SN64_STICK_CHOICES;
        if (up)   s->pick = (int8_t)wrap(s->pick - 1, n);
        if (down) s->pick = (int8_t)wrap(s->pick + 1, n);
        if (a) {
            if (s->open == SN64_MS_LIST_INPUT)     s->input_pad = (uint8_t)s->pick;
            else if (s->open == SN64_MS_LIST_SNES) s->snes_pad = (uint8_t)s->pick;
            else                                   sn64_map_set_stick(map, sn64_map_stick_choice(s->pick));
            s->open = SN64_MS_CLOSED;
        } else if (b) {
            s->open = SN64_MS_CLOSED;           // it goes away, the setting stays as it was
        }
    } else if (s->open == SN64_MS_TARGET) {
        int col = s->pick / CHOICE_ROWS, line = s->pick % CHOICE_ROWS;
        if (left != right) col ^= 1;
        if (line >= choice_column_length(col)) line = choice_column_length(col) - 1;
        if (up)   line = wrap(line - 1, choice_column_length(col));
        if (down) line = wrap(line + 1, choice_column_length(col));
        s->pick = (int8_t)(col * CHOICE_ROWS + line);
#ifdef SN64_FAULT_MAPSCREEN_CANCEL_SETS
        // Fault injection for the host test: B takes the choice as A does.
        if (b) a = true;
#endif
        if (a) {
            sn64_map_set_target(map, sn64_mapscreen_entry(s), sn64_map_choice(s->pick));
            s->open = SN64_MS_CLOSED;
        } else if (b) {
            s->open = SN64_MS_CLOSED;           // the row stays as it was
        }
    } else {
        // Up and Down go through the lists, the rows and the reset field, and round again.
        if (s->row == SN64_MS_ROW_LISTS) {
            if (left != right) s->col ^= 1;
            if (up)        s->row = SN64_MS_ROW_RESET;
            else if (down) s->row = 0;
        } else {
            if (up)        s->row--;
            else if (down) s->row = (int8_t)(s->row == SN64_MS_ROW_RESET ? SN64_MS_ROW_LISTS : s->row + 1);
        }
        // the list scrolls to keep the row under the cursor among the ten that are shown
        if (s->row >= 0 && s->row < SN64_MS_LIST_ROWS) {
            if (s->row < s->first)                    s->first = (uint8_t)s->row;
            if (s->row >= s->first + SN64_MS_VISIBLE) s->first = (uint8_t)(s->row - SN64_MS_VISIBLE + 1);
        }
        if (a) {
            if (s->row == SN64_MS_ROW_LISTS) {
                s->open = (uint8_t)(s->col ? SN64_MS_LIST_SNES : SN64_MS_LIST_INPUT);
                s->pick = (int8_t)(s->col ? s->snes_pad : s->input_pad);
            } else if (s->row == SN64_MS_ROW_RESET) {
                sn64_map_default(map);
                s->restored = true;
            } else if (s->row == SN64_MS_ROW_STICK) {
                s->open = SN64_MS_STICK;
                s->pick = (int8_t)sn64_map_stick_choice_index(map->stick_percent);
            } else {
                s->open = SN64_MS_TARGET;
                s->pick = (int8_t)sn64_map_choice_index(sn64_map_target(map, sn64_mapscreen_entry(s)));
            }
            s->b_armed = false;
        } else if (b) {
            s->b_armed = true;
        }
    }
    return leave;
}

// ---- drawing

typedef struct {
    const sn64_canvas_t *c;
    sn64_text_fn         text;
    void                *ctx;
} out_t;

// A list box: the name of what is chosen and the mark that says a list drops down from it.
static void list_box(const out_t *o, int x, const char *name, bool at)
{
    sn64_pad_fill(o->c, x, Y_LIST, x + SN64_PAD_W - 1, Y_LIST + LIST_H - 1, at ? COL_BAR : COL_BOX);
    sn64_pad_frame(o->c, x, Y_LIST, x + SN64_PAD_W - 1, Y_LIST + LIST_H - 1, at ? COL_HI : COL_DIM);
    o->text(o->ctx, x + 3, Y_LIST + 3, at ? COL_HI : COL_TEXT, name);
    sn64_pad_mark(o->c, x + SN64_PAD_W - 8, Y_LIST + 5, at ? COL_HI : COL_DIM);
}

// Ten rows of the list. The stick's row: its small picture, an arrow, the D-pad with the
// arms it is pressing lit, and how far it has to be pushed. A button's row: its small picture,
// its name, an arrow, the Super NES button it gives, its name. A small mark above or below
// the list says that there are more rows that way.
static void draw_rows(const out_t *o, const sn64_mapscreen_t *s, const sn64_map_t *map,
                      uint16_t held, uint16_t passed, uint16_t snes, uint16_t stick_dirs)
{
    for (int v = 0; v < SN64_MS_VISIBLE; v++) {
        int row = s->first + v, e = row - 1;
        int x = X_RIGHT, y = Y_ROWS + v * ROW_H;
        bool at = s->open == SN64_MS_CLOSED && s->row == row;
        if (at)
            sn64_pad_fill(o->c, x, y, x + SN64_PAD_W - 1, y + SN64_ICON - 1, COL_BAR);
        sn64_pad_arrow(o->c, x + 71, y + 3, COL_DIM);
        if (row == SN64_MS_ROW_STICK) {
            char pct[8];
            sn64_pad_icon_input(o->c, x + 1, y, SN64_IN_STICK, stick_dirs != 0);
            o->text(o->ctx, x + 14, y + 2, at ? COL_HI : COL_TEXT, "Stick");
            if (map->stick_percent) {
                snprintf(pct, sizeof pct, "%u %%", map->stick_percent);
                sn64_pad_icon_dpad(o->c, x + 78, y, stick_dirs);
                o->text(o->ctx, x + 91, y + 2, at ? COL_HI : COL_TEXT, pct);
            } else {
                sn64_pad_icon_snes(o->c, x + 78, y, s->snes_pad, -1, false);
                o->text(o->ctx, x + 91, y + 2, COL_DIM, "none");
            }
        } else {
            int t = sn64_map_target(map, e);
            // the right-hand picture lights only if the game really gets the button (opposite
            // directions cancel, the menu shortcut is taken out)
            bool gives = (passed & sn64_map_n64_bit(e)) && t >= 0 && (snes & (1u << t));
            sn64_pad_icon_input(o->c, x + 1, y, e, (held & sn64_map_n64_bit(e)) != 0);
            o->text(o->ctx, x + 14, y + 2, at ? COL_HI : COL_TEXT, sn64_map_n64_name(e));
            sn64_pad_icon_snes(o->c, x + 78, y, s->snes_pad, t, gives);
            o->text(o->ctx, x + 91, y + 2, t < 0 ? COL_DIM : at ? COL_HI : COL_TEXT, t < 0 ? "none" : sn64_snes_button_name(t));
        }
    }
    if (s->first > 0)
        sn64_pad_mark_up(o->c, X_RIGHT + SN64_PAD_W / 2 - 2, Y_ROWS - 4, COL_HI);
    if (s->first + SN64_MS_VISIBLE < SN64_MS_LIST_ROWS)
        sn64_pad_mark(o->c, X_RIGHT + SN64_PAD_W / 2 - 2, Y_ROWS + SN64_MS_VISIBLE * ROW_H + 1, COL_HI);
}

// The panel the choices stand in, in the place of the list: both pictures stay in view.
static void choices_panel(const out_t *o, int entry, bool held, const char *head)
{
    sn64_pad_fill(o->c, X_RIGHT, Y_ROWS - 1, X_END, Y_ROWS + SN64_MS_VISIBLE * ROW_H - 1, COL_PANEL);
    sn64_pad_frame(o->c, X_RIGHT, Y_ROWS - 1, X_END, Y_ROWS + SN64_MS_VISIBLE * ROW_H - 1, COL_HI);
    sn64_pad_icon_input(o->c, X_RIGHT + 4, Y_ROWS + 3, entry, held);
    o->text(o->ctx, X_RIGHT + 18, Y_ROWS + 5, COL_HI, head);
}

// The choices for a button: the 12 Super NES buttons and nothing.
static void draw_choices(const out_t *o, const sn64_mapscreen_t *s, uint16_t held)
{
    int entry = sn64_mapscreen_entry(s);
    char head[24];
    snprintf(head, sizeof head, "%s gives:", sn64_map_n64_name(entry));
    choices_panel(o, entry, (held & sn64_map_n64_bit(entry)) != 0, head);
    for (int i = 0; i < SN64_MAP_CHOICES; i++) {
        int x = X_RIGHT + 2 + (i / CHOICE_ROWS) * CHOICE_W, y = Y_ROWS + 20 + (i % CHOICE_ROWS) * CHOICE_H;
        int bit = sn64_map_choice(i);
        if (i == s->pick)
            sn64_pad_fill(o->c, x - 1, y - 1, x + CHOICE_W - 2, y + SN64_ICON, COL_BAR);
        sn64_pad_icon_snes(o->c, x, y, s->snes_pad, bit, false);
        o->text(o->ctx, x + 12, y + 2, i == s->pick ? COL_HI : COL_TEXT, sn64_snes_button_name(bit));
    }
}

// The choices for the stick: the D-pad from 20, 30 ... 80 percent of its travel, or nothing.
static void draw_stick_choices(const out_t *o, const sn64_mapscreen_t *s, uint16_t stick_dirs)
{
    choices_panel(o, SN64_IN_STICK, stick_dirs != 0, "Stick gives:");
    for (int i = 0; i < SN64_STICK_CHOICES; i++) {
        int x = X_RIGHT + 4, y = Y_ROWS + 20 + i * ROW_H;
        unsigned percent = sn64_map_stick_choice(i);
        char label[28];
        if (i == s->pick)
            sn64_pad_fill(o->c, x - 3, y, X_END - 1, y + SN64_ICON - 1, COL_BAR);
        if (percent) {
            snprintf(label, sizeof label, "D-pad from %u %%", percent);
            sn64_pad_icon_dpad(o->c, x, y, i == s->pick ? stick_dirs : 0);
        } else {
            snprintf(label, sizeof label, "nothing");
            sn64_pad_icon_snes(o->c, x, y, s->snes_pad, -1, false);
        }
        o->text(o->ctx, x + 12, y + 2, i == s->pick ? COL_HI : COL_TEXT, label);
    }
}

// An open controller list, over the top of its picture.
static void draw_list(const out_t *o, const sn64_mapscreen_t *s)
{
    bool input = s->open == SN64_MS_LIST_INPUT;
    int n = input ? SN64_PAD_INPUT_COUNT : SN64_PAD_SNES_COUNT;
    int x = input ? X_LEFT : X_RIGHT, y = Y_LIST + LIST_H - 1;
    sn64_pad_fill(o->c, x, y, x + SN64_PAD_W - 1, y + n * LINE_H + 3, COL_BOX);
    sn64_pad_frame(o->c, x, y, x + SN64_PAD_W - 1, y + n * LINE_H + 3, COL_HI);
    for (int i = 0; i < n; i++) {
        int ly = y + 2 + i * LINE_H;
        if (i == s->pick)
            sn64_pad_fill(o->c, x + 1, ly, x + SN64_PAD_W - 2, ly + LINE_H - 1, COL_BAR);
        o->text(o->ctx, x + 3, ly + 2, i == s->pick ? COL_HI : COL_TEXT,
                input ? sn64_input_pad_name((unsigned)i) : sn64_snes_pad_name((unsigned)i));
    }
}

void sn64_mapscreen_draw(const sn64_mapscreen_t *s, const sn64_map_t *map, const sn64_canvas_t *c,
                         sn64_text_fn text, void *ctx, uint16_t n64_buttons, int8_t stick_x, int8_t stick_y,
                         unsigned frame)
{
    const out_t o = { c, text, ctx };
    bool blink = (frame & 16u) != 0;                    // about a quarter of a second on, a quarter off
    bool chord = (n64_buttons & N64_BTN_C_ALL) == N64_BTN_C_ALL;
    bool closed = s->open == SN64_MS_CLOSED;
    int entry = sn64_mapscreen_entry(s);

    // What the pictures show: the mapping as it is or, while choices are open, as it would be
    // with the one under the cursor, so a choice can be tried before it is taken.
    sn64_map_t shown = *map;
    if (s->open == SN64_MS_TARGET) sn64_map_set_target(&shown, entry, sn64_map_choice(s->pick));
    if (s->open == SN64_MS_STICK)  sn64_map_set_stick(&shown, sn64_map_stick_choice(s->pick));
    uint16_t passed = sn64_map_strip_menu_chord(n64_buttons);   // what the game would be given
    uint16_t snes = sn64_map_buttons(&shown, passed, stick_x, stick_y);
    uint16_t stick_dirs = sn64_map_stick(&shown, stick_x, stick_y);
    int target = entry < 0 ? -1 :
                 entry == SN64_IN_STICK ? (shown.stick_percent ? SN64_OUT_DPAD : -1) : sn64_map_target(&shown, entry);

    list_box(&o, X_LEFT, sn64_input_pad_name(s->input_pad),
             s->open == SN64_MS_LIST_INPUT || (closed && s->row == SN64_MS_ROW_LISTS && s->col == 0));
    list_box(&o, X_RIGHT, sn64_snes_pad_name(s->snes_pad),
             s->open == SN64_MS_LIST_SNES || (closed && s->row == SN64_MS_ROW_LISTS && s->col == 1));

    // The two pictures: what is held lights on the left, what the game is given lights on the
    // right, and the row under the cursor is marked in both.
    sn64_pad_draw_input(c, X_LEFT, Y_PAD, s->input_pad, n64_buttons, stick_x, stick_y, stick_dirs != 0, entry, blink);
    sn64_pad_draw_snes(c, X_RIGHT, Y_PAD, s->snes_pad, snes, target, blink);

    if (s->open == SN64_MS_TARGET)     draw_choices(&o, s, n64_buttons);
    else if (s->open == SN64_MS_STICK) draw_stick_choices(&o, s, stick_dirs);
    else                               draw_rows(&o, s, map, n64_buttons, passed, snes, stick_dirs);

    // Under the player's controller: how the menu is reached from a game (it lights up while
    // the four buttons are held), then one line of notes: with the cursor on the stick, how far
    // the stick is pushed now; else the Super NES buttons that nothing gives any more, as their
    // small pictures or their number, or the reset.
    {
        uint16_t tip = chord ? COL_HI : COL_DIM;
        uint16_t missing = sn64_map_unreachable(map);
        char note[32];
        int count = 0;
        text(ctx, X_LEFT, Y_TIP, tip, "In a game, all");
        text(ctx, X_LEFT, Y_TIP + 10, tip, "four C buttons");
        text(ctx, X_LEFT, Y_TIP + 20, tip, "bring up the menu");
        for (unsigned bit = 0; bit < SNES_BUTTONS; bit++)
            if (missing & (1u << bit)) count++;
        if (entry == SN64_IN_STICK) {
            snprintf(note, sizeof note, "Stick now: %u %%", sn64_stick_push(stick_x, stick_y));
            text(ctx, X_LEFT, Y_NOTE, stick_dirs ? COL_HI : COL_TEXT, note);
        } else if (count > 5) {
            snprintf(note, sizeof note, "Unmapped: %d/12", count);
            text(ctx, X_LEFT, Y_NOTE, COL_WARN, note);
        } else if (count) {
            int x = X_LEFT + 9 * 8 + 3;
            text(ctx, X_LEFT, Y_NOTE, COL_WARN, "Unmapped:");
            for (int i = 0; i < SN64_MAP_CHOICES; i++) {
                int bit = sn64_map_choice(i);
                if (bit >= 0 && (missing & (1u << bit))) {
                    sn64_pad_icon_snes(c, x, Y_NOTE - 2, s->snes_pad, bit, false);
                    x += SN64_ICON + 1;
                }
            }
        } else if (s->restored) {
            text(ctx, X_LEFT, Y_NOTE, COL_TEXT, "Defaults are back");
        }
    }

    {
        bool at = closed && s->row == SN64_MS_ROW_RESET;
        sn64_pad_fill(c, X_LEFT, Y_FOOT, X_LEFT + SN64_PAD_W - 1, Y_FOOT + LIST_H - 1, at ? COL_BAR : COL_BOX);
        sn64_pad_frame(c, X_LEFT, Y_FOOT, X_LEFT + SN64_PAD_W - 1, Y_FOOT + LIST_H - 1, at ? COL_HI : COL_DIM);
        text(ctx, X_LEFT + 3, Y_FOOT + 3, at ? COL_HI : sn64_map_is_default(map) ? COL_DIM : COL_TEXT, "Restore defaults");
        text(ctx, X_RIGHT, Y_FOOT + 3, COL_DIM, closed ? "A change   B back" : "A pick   B cancel");
    }

    if (s->open == SN64_MS_LIST_INPUT || s->open == SN64_MS_LIST_SNES)
        draw_list(&o, s);
}
