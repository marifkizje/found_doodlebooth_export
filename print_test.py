import win32print
import win32ui
from PIL import Image, ImageWin
import win32con

def print_image_direct(
    image_path=r"C:\Users\boris.binnendijk\OneDrive - BearingPoint GmbH\Documents\102.Data Expo\Foundry doodlebooth\styled_images\Scan_0002_1153.png",
    printer_name="HP417610 (HP OfficeJet Pro 7720 series)",
    offset_x=0,           # keep at 0 because offset_mm overrides it
    offset_mm=0,       # negative = move LEFT by 6 mm
    debug_print_caps=False
):
    """
    Print an image centred on the physical page, compensating for asymmetric margins.
    Positive offset moves RIGHT, negative moves LEFT.
    """
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer_name)
        dc.SetMapMode(win32con.MM_TEXT)

        # Get printer metrics
        printable_w  = dc.GetDeviceCaps(win32con.HORZRES)
        printable_h  = dc.GetDeviceCaps(win32con.VERTRES)
        phys_w       = dc.GetDeviceCaps(win32con.PHYSICALWIDTH)
        phys_h       = dc.GetDeviceCaps(win32con.PHYSICALHEIGHT)
        off_x        = dc.GetDeviceCaps(win32con.PHYSICALOFFSETX)
        off_y        = dc.GetDeviceCaps(win32con.PHYSICALOFFSETY)
        dpi_x        = dc.GetDeviceCaps(win32con.LOGPIXELSX)
        dpi_y        = dc.GetDeviceCaps(win32con.LOGPIXELSY)

        if debug_print_caps:
            print(f"[Printer caps] phys_w={phys_w}, phys_h={phys_h}, "
                  f"printable_w={printable_w}, printable_h={printable_h}, "
                  f"off_x={off_x}, off_y={off_y}, dpi_x={dpi_x}, dpi_y={dpi_y}")

        # Convert mm offset to pixels if provided
        if offset_mm is not None:
            offset_x = int(round((offset_mm / 25.4) * dpi_x))

        # Start print job
        dc.StartDoc(image_path)
        dc.StartPage()

        img = Image.open(image_path)
        dib = ImageWin.Dib(img)
        img_w, img_h = img.size

        # Scale to fit printable area
        scale = min(printable_w / img_w, printable_h / img_h)
        scaled_w = int(img_w * scale)
        scaled_h = int(img_h * scale)

        # Centre on physical page, then apply offset
        left_phys = (phys_w - scaled_w) // 2 + offset_x
        top_phys  = (phys_h - scaled_h) // 2

        # Convert to printable coords
        left   = left_phys - off_x
        top    = top_phys - off_y
        right  = left + scaled_w
        bottom = top + scaled_h

        # Clamp to printable area
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

        # Draw image
        dib.draw(dc.GetHandleOutput(), (left, top, right, bottom))

        dc.EndPage()
        dc.EndDoc()
        dc.DeleteDC()

        print(f"Printed with {offset_mm} mm shift to the LEFT (offset_x={offset_x}px).")

    except Exception as e:
        print(f"Printing failed: {e}")
    finally:
        win32print.ClosePrinter(hPrinter)


# --- Run the function ---
print_image_direct(debug_print_caps=True)
