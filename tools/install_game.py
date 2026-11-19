r"""A dinosaur to jump over cactuses with while HeySpeaky installs.

The installer opens this as soon as its own Python is ready, and writes its
progress to a small JSON file that this window reads twice a second. Closing
the window never touches the install.

    pythonw.exe tools\install_game.py --progress <file> --parent <pid>

Standard library only: when this starts, nothing else is installed yet.
"""

import argparse
import ctypes
import json
import math
import random
import time
import tkinter as tk

# Layout in logical pixels, multiplied by the screen's scale when drawn.
WIDTH = 640
HEIGHT = 300
GROUND = 268
TICK_MS = 16

BACKGROUND = "#f7f7f7"
INK = "#535353"
MUTED = "#8b8b8b"
TRACK = "#e3e3e3"
FILL = "#34c759"
FAILED = "#ff4d4f"

GRAVITY = 0.65
JUMP_SPEED = -11.8
START_SPEED = 6.0
MAX_SPEED = 13.0

PIXEL = 3

# The T-rex, as rows of pixels. Legs are separate so they can run.
DINO_BODY = [
    "           ######## ",
    "          ##########",
    "          ## #######",
    "          ##########",
    "          ##########",
    "          #####     ",
    "          ########  ",
    "#        #####      ",
    "#       ######      ",
    "##    #########     ",
    "###  ######## #     ",
    "############        ",
    " ###########        ",
    "  #########         ",
    "   #######          ",
]
DINO_LEGS = [
    [
        "    ###  ##         ",
        "    ##    #         ",
        "    #     #         ",
        "    ##    ##        ",
    ],
    [
        "    ###  ##         ",
        "    #    ##         ",
        "    #     ##        ",
        "    ##              ",
    ],
]

_SMALL = [
    "  ##  ",
    "  ##  ",
    "# ## #",
    "# ## #",
    "# ## #",
    "######",
    "  ##  ",
    "  ##  ",
    "  ##  ",
    "  ##  ",
]
_LARGE = [
    "   ##   ",
    "   ##   ",
    "   ##  #",
    "#  ##  #",
    "#  ##  #",
    "#  ##  #",
    "#  #####",
    "#  ##   ",
    "#####   ",
    "   ##   ",
    "   ##   ",
    "   ##   ",
    "   ##   ",
    "   ##   ",
]
CACTI = [_SMALL, _LARGE, [row + " " + row for row in _SMALL]]


# -- progress ----------------------------------------------------------------


def progress(state, now):
    """The bar's fill and the seconds left, from the installer's progress file.

    Each step comes with a rough expected duration. Within a step the bar
    eases towards the step's end and never reaches it, so a slow download
    slows the bar down rather than parking it somewhere that looks finished.
    """
    if not state:
        return 0.0, None
    if state.get("state") == "done":
        return 1.0, 0.0
    try:
        finished = float(state.get("finished_share", 0.0))
        share = float(state.get("share", 0.0))
        expected = max(1.0, float(state.get("expected", 1.0)))
        started = float(state.get("started", now))
        after = float(state.get("remaining_after", 0.0))
    except (TypeError, ValueError):
        return 0.0, None
    elapsed = max(0.0, now - started)
    fraction = finished + share * (1.0 - math.exp(-elapsed / expected))
    left = max(0.0, expected - elapsed) + after
    return max(0.0, min(fraction, 0.99)), left


def time_left(seconds):
    """A deliberately vague estimate. The bar is there to reassure."""
    if seconds is None:
        return ""
    if seconds < 45:
        return "almost done"
    if seconds < 90:
        return "about a minute left"
    return "about {} minutes left".format(int(round(seconds / 60.0)))


def process_alive(pid):
    """False once the installer's PowerShell window has gone."""
    if not pid:
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        # SYNCHRONIZE
        handle = kernel32.OpenProcess(0x00100000, False, int(pid))
        if not handle:
            # Access denied means it exists; anything else means it does not.
            return ctypes.get_last_error() == 5
        try:
            return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0) != 0
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    except Exception:
        return True


# -- drawing -----------------------------------------------------------------


class Sprite:
    """Pixel art as canvas rectangles, one per horizontal run of pixels."""

    def __init__(self, canvas, rows, x, y, scale, color=INK):
        self.canvas = canvas
        self.tag = "sprite{}".format(id(self))
        self.scale = scale
        self.width = max(len(row) for row in rows) * PIXEL
        self.height = len(rows) * PIXEL
        self.x = x
        self.y = y
        for row_index, row in enumerate(rows):
            col = 0
            while col < len(row):
                if row[col] != "#":
                    col += 1
                    continue
                start = col
                while col < len(row) and row[col] == "#":
                    col += 1
                canvas.create_rectangle(
                    (x + start * PIXEL) * scale,
                    (y + row_index * PIXEL) * scale,
                    (x + col * PIXEL) * scale,
                    (y + (row_index + 1) * PIXEL) * scale,
                    fill=color, width=0, tags=self.tag,
                )

    def move_to(self, x, y):
        self.canvas.move(self.tag, (x - self.x) * self.scale,
                         (y - self.y) * self.scale)
        self.x, self.y = x, y

    def show(self, visible):
        self.canvas.itemconfigure(
            self.tag, state="normal" if visible else "hidden")

    def delete(self):
        self.canvas.delete(self.tag)


class Game:
    def __init__(self, root, progress_path, parent):
        self.root = root
        self.path = progress_path
        self.parent = parent
        self.k = root.winfo_fpixels("1i") / 96.0
        k = self.k

        canvas = tk.Canvas(root, width=WIDTH * k, height=HEIGHT * k,
                           bg=BACKGROUND, highlightthickness=0)
        canvas.pack()
        self.canvas = canvas

        # Progress, across the top.
        self.label = canvas.create_text(
            16 * k, 20 * k, anchor="w", text="Getting ready",
            fill=INK, font=("Segoe UI", 10))
        self.left = canvas.create_text(
            (WIDTH - 16) * k, 20 * k, anchor="e", text="",
            fill=MUTED, font=("Segoe UI", 9))
        canvas.create_rectangle(16 * k, 34 * k, (WIDTH - 16) * k, 44 * k,
                                fill=TRACK, width=0)
        self.bar = canvas.create_rectangle(16 * k, 34 * k, 16 * k, 44 * k,
                                           fill=FILL, width=0)
        self.state = None
        self.shown = 0.0
        self.closing = False
        self.polls = 0

        # The game, below it.
        canvas.create_line(0, GROUND * k, WIDTH * k, GROUND * k, fill=INK,
                           width=max(1, round(k)))
        self.pebbles = []
        for _ in range(9):
            x = random.uniform(0, WIDTH)
            y = GROUND + random.choice((5, 9, 13))
            item = canvas.create_rectangle(
                x * k, y * k, (x + random.choice((2, 4, 6))) * k,
                (y + 2) * k, fill=INK, width=0)
            self.pebbles.append([item, x])
        self.score_text = canvas.create_text(
            (WIDTH - 16) * k, 66 * k, anchor="e", text="",
            fill=INK, font=("Consolas", 11, "bold"))
        self.message = canvas.create_text(
            WIDTH / 2 * k, 120 * k, text="Press Space to play",
            fill=INK, font=("Segoe UI", 12, "bold"))

        self.dino_x = 48
        body_height = len(DINO_BODY) * PIXEL
        legs_height = len(DINO_LEGS[0]) * PIXEL
        self.ground_y = GROUND - body_height - legs_height
        self.body = Sprite(canvas, DINO_BODY, self.dino_x, self.ground_y, k)
        self.legs = [
            Sprite(canvas, rows, self.dino_x, self.ground_y + body_height, k)
            for rows in DINO_LEGS
        ]
        self.body_height = body_height

        self.cacti = []
        self.best = 0
        self.mode = "ready"
        self.reset()

        for key in ("<space>", "<Up>", "<Button-1>"):
            root.bind(key, self.press)

        self.tick()
        self.poll()

    # -- game --------------------------------------------------------------

    def reset(self):
        for cactus in self.cacti:
            cactus.delete()
        self.cacti = []
        self.y = self.ground_y
        self.vy = 0.0
        self.speed = START_SPEED
        self.distance = 0.0
        self.frame = 0
        self.gap = 0.0
        self.place_dino()

    def place_dino(self):
        self.body.move_to(self.dino_x, self.y)
        for legs in self.legs:
            legs.move_to(self.dino_x, self.y + self.body_height)

    def press(self, _event=None):
        if self.mode != "running":
            self.reset()
            self.mode = "running"
            self.canvas.itemconfigure(self.message, text="")
        elif self.y >= self.ground_y:
            self.vy = JUMP_SPEED

    def spawn(self):
        rows = random.choice(CACTI)
        height = len(rows) * PIXEL
        self.cacti.append(
            Sprite(self.canvas, rows, WIDTH + 10, GROUND - height, self.k))
        self.gap = random.uniform(260, 520) * (self.speed / START_SPEED) ** 0.5

    def hit(self, cactus):
        left, top = self.dino_x + 10, self.y + 6
        right = self.dino_x + 20 * PIXEL - 12
        bottom = self.y + self.body_height + 8
        return (left < cactus.x + cactus.width - 3 and right > cactus.x + 3
                and top < cactus.y + cactus.height and bottom > cactus.y + 3)

    def step_game(self):
        self.vy += GRAVITY
        self.y = min(self.ground_y, self.y + self.vy)
        if self.y >= self.ground_y:
            self.vy = 0.0
        self.frame += 1
        running = self.y >= self.ground_y and (self.frame // 5) % 2
        self.legs[0].show(not running)
        self.legs[1].show(bool(running))
        self.place_dino()

        self.distance += self.speed
        score = int(self.distance / 12)
        self.speed = min(MAX_SPEED, START_SPEED + score / 180.0)

        for cactus in list(self.cacti):
            cactus.move_to(cactus.x - self.speed, cactus.y)
            if cactus.x + cactus.width < 0:
                cactus.delete()
                self.cacti.remove(cactus)
        if not self.cacti or self.cacti[-1].x < WIDTH - self.gap:
            self.spawn()

        k = self.k
        for pebble in self.pebbles:
            pebble[1] -= self.speed
            if pebble[1] < -8:
                pebble[1] += WIDTH + random.uniform(10, 80)
            _, y0, _, y1 = self.canvas.coords(pebble[0])
            width = self.canvas.coords(pebble[0])[2] - self.canvas.coords(
                pebble[0])[0]
            self.canvas.coords(pebble[0], pebble[1] * k, y0,
                               pebble[1] * k + width, y1)

        self.canvas.itemconfigure(
            self.score_text,
            text="HI {:05d}  {:05d}".format(self.best, score)
            if self.best else "{:05d}".format(score))

        if any(self.hit(cactus) for cactus in self.cacti):
            self.best = max(self.best, score)
            self.mode = "over"
            self.canvas.itemconfigure(
                self.message, text="Game over. Space to play again")

    def tick(self):
        if self.closing:
            return
        if self.mode == "running":
            self.step_game()
        self.draw_progress()
        self.root.after(TICK_MS, self.tick)

    # -- progress ----------------------------------------------------------

    def draw_progress(self):
        target, _ = progress(self.state, time.time())
        # Ease towards the target, and never move backwards.
        self.shown = max(self.shown, self.shown + (target - self.shown) * 0.08)
        k = self.k
        right = 16 + (WIDTH - 32) * min(1.0, self.shown)
        self.canvas.coords(self.bar, 16 * k, 34 * k, right * k, 44 * k)

    def poll(self):
        if self.closing:
            return
        try:
            with open(self.path, "r", encoding="utf-8-sig") as handle:
                self.state = json.load(handle)
        except (OSError, ValueError):
            pass

        kind = (self.state or {}).get("state")
        if kind == "done":
            self.shown = 1.0
            self.canvas.itemconfigure(self.label, text="HeySpeaky is installed")
            self.canvas.itemconfigure(self.left, text="")
            self.closing = True
            self.draw_progress()
            self.root.after(4000, self.root.destroy)
            return
        if kind == "failed":
            self.canvas.itemconfigure(
                self.label,
                text="The install stopped. The PowerShell window says why.")
            self.canvas.itemconfigure(self.left, text="")
            self.canvas.itemconfigure(self.bar, fill=FAILED)
        elif self.state:
            _, seconds = progress(self.state, time.time())
            self.canvas.itemconfigure(self.label,
                                      text=self.state.get("label") or "")
            self.canvas.itemconfigure(self.left, text=time_left(seconds))

        self.polls += 1
        if self.polls % 4 == 0 and not process_alive(self.parent):
            # The installer's window is gone, so nothing will finish.
            self.closing = True
            self.root.destroy()
            return
        self.root.after(500, self.poll)


def main():
    parser = argparse.ArgumentParser(description="HeySpeaky install game")
    parser.add_argument("--progress", required=True)
    parser.add_argument("--parent", type=int, default=0)
    args = parser.parse_args()

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.title("Installing HeySpeaky")
    root.resizable(False, False)
    root.configure(bg=BACKGROUND)
    Game(root, args.progress, args.parent)

    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 3
    root.geometry("+{}+{}".format(max(0, x), max(0, y)))
    root.lift()
    root.attributes("-topmost", True)
    root.after(800, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    main()
