---
name: change-the-look
description: Change how the HeySpeaky pill looks without breaking the three things that make it invisible - no focus, no blocked clicks, no Alt+Tab.
---

# Changing the look

Every colour, size and timing lives in `heyspeaky/theme.py`. Change numbers
there first, and only go into `glass.py` when the shape itself must change.

## Look at it before you ship it

```powershell
.venv\Scripts\python.exe tools\ui_lab.py --out lab.png
.venv\Scripts\python.exe tools\ui_lab.py --desktop --out lab-real.png
```

The first draws every state over colourful, light and dark desktops. The
second uses a picture of the real screen, which is the honest test. Open the
PNG and look at it. A change nobody looked at is not finished.

## What the drawing has to keep doing

- **Measure, do not assume.** The glass photographs the desktop underneath, so
  brightness is known: the text colour, how much white goes into the glass and
  how the rim light is blended all follow from it. Adding light to a white
  document does nothing, which is why the rim is painted on over light
  desktops and screened in over dark ones.
- **Stay cheap.** The heavy half is built once per appearance by `prepare()`;
  each frame only paints the dot, the waveform and the text. Measure after any
  change:

```python
glass.prepare(...)   # about 50 ms, once
glass.paint(...)     # about 1 ms, thirty times a second
```

  A whole frame used to cost 39 ms and stole the processor from recording.

- **Draw smooth things at twice the size and scale them down.** Tk has no
  antialiasing, and hard edges on a rounded pill look cheap.

## Never break these

The window must keep `WS_EX_NOACTIVATE`, `WS_EX_TRANSPARENT` and
`WS_EX_TOOLWINDOW`: no focus, clicks pass through, invisible to Alt+Tab. After
any change to `overlay.py`, run the window for real and check that clicking
where it sits still hits what is underneath, and that the caret stays where it
was.

## Tests

`tests/test_heyspeaky.py` has a `GlassPill` class: frame size, the light and
dark decision, that the glass is built once and painted many times, and that
long text is shortened rather than spilling.
