"""
Printer utility - same physical-page-centering logic as the original
doodle-to-avatar script, plus a duplex alignment-test helper.

Only needed on the Windows laptop connected to the printer; card
generation/composition works fine without pywin32 installed.

--------------------------------------------------------------------------
ABOUT FRONT/BACK ALIGNMENT
--------------------------------------------------------------------------
card_pipeline.py now guarantees the front and back images are pixel-
identical in canvas size and in where the outer border sits (both use the
same MARGIN/BORDER_RADIUS/BORDER_WIDTH constants). That fixes the part of
the misalignment that code can control.

The remaining part is physical: when you manually flip an A6 card over to
print the second side, which edge you flip it on (the short edge, like
turning a page, or the long edge, like turning a steering wheel) determines
whether the back image needs to be printed as-is or horizontally mirrored
to line up with the front. That depends on your printer/tray, not on the
code, so it needs a one-time real-world calibration - use
`print_alignment_test()` below to figure out the right settings for your
setup, then hard-code them (FLIP_EDGE / MIRROR_BACK) for the event.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    import win32con
    import win32print
    import win32ui
    from PIL import ImageWin
    _WINDOWS_PRINTING_AVAILABLE = True
except ImportError:
    _WINDOWS_PRINTING_AVAILABLE = False


def print_image_direct(
    image_path,
    printer_name: str = "HP417610 (HP OfficeJet Pro 7720 series)",
    offset_x: int = 0,          # in printer pixels: +right, -left
    offset_mm: float | None = 0,  # optional: overrides offset_x (mm -> px)
    debug_print_caps: bool = False,
):
    """
    Print an image centered on the *physical page*, compensating for
    asymmetric printer margins. Positive offset_x moves the image RIGHT,
    negative LEFT. If offset_mm is given it overrides offset_x.
    """
    if not _WINDOWS_PRINTING_AVAILABLE:
        raise RuntimeError(
            "pywin32 is not available on this machine - printing only works "
            "on the Windows laptop connected to the event printer. Card "
            "generation/composition still works fine without it."
        )

    image_path = str(image_path)

    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer_name)
        dc.SetMapMode(win32con.MM_TEXT)

        printable_w = dc.GetDeviceCaps(win32con.HORZRES)
        printable_h = dc.GetDeviceCaps(win32con.VERTRES)
        phys_w = dc.GetDeviceCaps(win32con.PHYSICALWIDTH)
        phys_h = dc.GetDeviceCaps(win32con.PHYSICALHEIGHT)
        off_x = dc.GetDeviceCaps(win32con.PHYSICALOFFSETX)
        off_y = dc.GetDeviceCaps(win32con.PHYSICALOFFSETY)
        dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
        dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)

        if debug_print_caps:
            print(f"[Printer caps] phys_w={phys_w}, phys_h={phys_h}, "
                  f"printable_w={printable_w}, printable_h={printable_h}, "
                  f"off_x={off_x}, off_y={off_y}, dpi_x={dpi_x}, dpi_y={dpi_y}")

        if offset_mm is not None:
            offset_x = int(round((offset_mm / 25.4) * dpi_x))

        dc.StartDoc(image_path)
        dc.StartPage()

        img = Image.open(image_path)
        dib = ImageWin.Dib(img)
        img_w, img_h = img.size

        scale = min(printable_w / img_w, printable_h / img_h)
        scaled_w = int(img_w * scale)
        scaled_h = int(img_h * scale)

        left_phys = (phys_w - scaled_w) // 2 + int(offset_x)
        top_phys = (phys_h - scaled_h) // 2

        left = left_phys - off_x
        top = top_phys - off_y
        right = left + scaled_w
        bottom = top + scaled_h

        if left < 0:
            right -= left
            left = 0
        if right > printable_w:
            left -= (right - printable_w)
            right = printable_w
        if top < 0:
            bottom -= top
            top = 0
        if bottom > printable_h:
            top -= (bottom - printable_h)
            bottom = printable_h

        dib.draw(dc.GetHandleOutput(), (left, top, right, bottom))

        dc.EndPage()
        dc.EndDoc()
        dc.DeleteDC()

        print(f"Printed centered on physical page (offset_x={offset_x}px).")

    except Exception as e:
        print(f"Printing failed: {e}")
    finally:
        win32print.ClosePrinter(hPrinter)


# --------------------------------------------------------------------------
# Duplex settings - determined once via print_alignment_test(), then reused
# for every real card print.
# --------------------------------------------------------------------------

MIRROR_BACK = False   # set True if the alignment test shows the back needs a horizontal flip
FRONT_OFFSET_MM = 0   # fine-tune per side if your printer's margins aren't symmetric
BACK_OFFSET_MM = 0


def print_card(front_path, back_path, printer_name: str = "HP417610 (HP OfficeJet Pro 7720 series)"):
    """
    Print both sides of a card as two separate single-sided jobs, using the
    MIRROR_BACK/FRONT_OFFSET_MM/BACK_OFFSET_MM settings calibrated via
    print_alignment_test(). Pauses aren't built in here since Streamlit
    already gives you a natural "flip the card now" moment between the two
    button clicks if you split this into two calls in the UI instead.
    """
    print_image_direct(front_path, printer_name=printer_name, offset_mm=FRONT_OFFSET_MM)

    back_image_path = back_path
    if MIRROR_BACK:
        mirrored = Image.open(back_path).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        back_image_path = str(Path(back_path).with_name(Path(back_path).stem + "_mirrored.png"))
        mirrored.save(back_image_path, dpi=(300, 300))

    print_image_direct(back_image_path, printer_name=printer_name, offset_mm=BACK_OFFSET_MM)


def print_alignment_test(printer_name: str = "HP417610 (HP OfficeJet Pro 7720 series)"):
    """
    Prints two A6 test pages - "SIDE A" and "SIDE B" - each with a big
    corner crosshair, a center crosshair, and a label. Use this ONCE to
    figure out your duplex settings:

    1. Run this function. It prints "SIDE A" first.
    2. Flip the printed page the way you plan to flip real cards during the
       event (e.g. flip on the short edge like a book, or the long edge).
    3. Feed it back in and it prints "SIDE B" on the reverse.
    4. Hold the card up to the light:
       - If the crosshairs line up -> your flip method works as-is, keep
         MIRROR_BACK = False.
       - If they're mirrored left-right -> set MIRROR_BACK = True in this
         file and re-test.
       - If they're offset but not mirrored -> adjust BACK_OFFSET_MM (and/or
         FRONT_OFFSET_MM) by the measured offset in mm and re-test.
    5. Once aligned, those settings are correct for every card for the rest
       of the event (same printer, same paper, same manual flip habit).
    """
    from card_pipeline import CARD_W, CARD_H, DPI

    def _make_test_page(label: str) -> Path:
        img = Image.new("RGB", (CARD_W, CARD_H), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(str(Path(__file__).parent / "assets/fonts/brand-bold.ttf"), 60)
        except Exception:
            font = ImageFont.load_default()

        margin = 40
        cross = 60
        # Corner crosshairs
        for cx, cy in [(margin, margin), (CARD_W - margin, margin), (margin, CARD_H - margin), (CARD_W - margin, CARD_H - margin)]:
            draw.line([cx - cross, cy, cx + cross, cy], fill="red", width=6)
            draw.line([cx, cy - cross, cx, cy + cross], fill="red", width=6)
        # Center crosshair
        cx, cy = CARD_W // 2, CARD_H // 2
        draw.line([cx - cross, cy, cx + cross, cy], fill="blue", width=6)
        draw.line([cx, cy - cross, cx, cy + cross], fill="blue", width=6)

        draw.text((cx, cy - 140), label, font=font, fill="black", anchor="mm")
        path = Path(__file__).parent / f"alignment_test_{label.replace(' ', '_').lower()}.png"
        img.save(path, dpi=(DPI, DPI))
        return path

    side_a = _make_test_page("SIDE A")
    side_b = _make_test_page("SIDE B")

    input(f"About to print {side_a.name}. Load a blank A6 sheet and press Enter...")
    print_image_direct(str(side_a), printer_name=printer_name)
    input(f"Now flip the sheet the way you'll flip real cards, load it back in, and press Enter to print {side_b.name}...")
    print_image_direct(str(side_b), printer_name=printer_name)
    print("Done - hold the card up to the light and check whether the crosshairs line up. See the docstring of this function for what to adjust.")
