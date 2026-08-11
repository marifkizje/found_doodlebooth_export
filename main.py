from pathlib import Path
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
import base64
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
import win32print
import win32ui
from PIL import Image, ImageWin
import win32con

# Load environment variables
env_path = Path(__file__).parent / "environment_variables.env"
load_dotenv(dotenv_path=env_path)

# Retrieve the API key from the environment variabless
API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize folder paths
base_dir = Path(__file__).resolve().parent
input_folder = base_dir / "input_images"
output_folder = base_dir / "output_images"
polaroid_folder = base_dir / "styled_images"

# Ensure folders exist early in your module (right after you define them)
for p in (input_folder, output_folder, polaroid_folder):
    p.mkdir(parents=True, exist_ok=True)
    
prompt = """Take this drawing created by my child and transform it into a photorealistic image or realistic 3D render. I don't know what it's supposed to be - it could be a creature, object," 
"or something completely from their imagination. Keep the original shape, proportions, line lengths, and all imperfections exactly as they are in the drawing - including any slanted eyes, uneven "
"lines, or strange markings. Do not correct, smooth out, or change any details of their design. Make it look like this thing exists in the real world, with realistic and colorfull textures (skin, fur, metal, etc.) "
"and natural lighting. Make the creatures look happy and colorfull like they are an adorable character from a disney movie. You can add realistic shadows and an environment or background that fits the feel of the drawing, but don't change anything about the form or details of what they created. "
"No pencil crayon textures or hand-drawn styles - this must look like a photo or CGI render, but staying true to their imagination."""

client = OpenAI(api_key=API_KEY)

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

#create a function which monitors the folder
def start_monitoring():
    observer = Observer()
    observer.schedule(ImageHandler(), str(input_folder), recursive=False)
    observer.start()
    print(f"Started monitoring folder: {input_folder}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping folder monitor...")
        observer.stop()
    observer.join()

# #Create a class for monitoring the folder
# class ImageHandler(FileSystemEventHandler):
#     def on_created(self, event):
#         # Only act if it is a file (not directory) and supported image type
#         input_image_path = Path(event.src_path)
#         print("SLEEPING FOR 10 SECONDS TO TEST BEFORE CALLING THE API")
#         time.sleep(10)
#         print(f"New image detected, calling model function for image: {input_image_path.stem}")
            
#         call_stable_diffusion_with_image(prompt=prompt, input_image_path=input_image_path)

def wait_for_file_ready(path: Path, timeout: float = 120.0, poll: float = 0.5) -> bool:
    """
    Return True when:
      1) size is stable across two polls, and
      2) the file can be opened for read (no exclusive lock).
    Timeout returns False.
    """
    deadline = time.time() + timeout
    last_size = -1
    while time.time() < deadline:
        try:
            # Size stabilization check
            size = path.stat().st_size
            if size == 0 or size != last_size:
                last_size = size
                time.sleep(poll)
                continue
 
            # Open test (will raise PermissionError if still locked)
            with open(path, "rb") as f:
                f.read(1)
            return True
        except (FileNotFoundError, PermissionError):
            time.sleep(poll)
    return False

class ImageHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self._seen = set()  # de-dup by resolved path
    def _maybe_process(self, path: Path):
        # Normalize
        try:
            path = path.resolve()
        except Exception:
            pass
 
        # Skip duplicates (on_created + on_moved for the same file)
        if path in self._seen:
            return
        self._seen.add(path)
 
        # Only files with supported image extensions
        if path.suffix.lower() not in SUPPORTED_EXTS:
            return
 
        print(f"Detected image candidate: {path.name}. Waiting for write to finish...")
        if not wait_for_file_ready(path):
            print(f"Timed out waiting for {path} to be ready. Skipping.")
            return
 
        print(f"Image is ready. Calling model for: {path.name}")
        call_stable_diffusion_with_image(prompt=prompt, input_image_path=path)
 
    def on_created(self, event):
        if event.is_directory:
            return
        self._maybe_process(Path(event.src_path))
 
    def on_moved(self, event):
        # Many scanners write to a temp file and rename when complete — this is the best event to use
        if event.is_directory:
            return
        self._maybe_process(Path(event.dest_path))


def call_stable_diffusion_with_image(prompt: str, input_image_path: Path):
    start_time = time.time() #start recording how long it takes to execute this function

    try:
        # Open image safely
        with open(input_image_path, "rb") as img_file:
            result = client.images.edit(
                model="gpt-image-1",
                image=[img_file],
                prompt=prompt,
                quality="high",
                size = "1024x1536"
            )

        # Validate response
        if not result or not result.data or not result.data[0].b64_json:
            print("Error: No image data found in response.")
            return

        image_base64 = result.data[0].b64_json
        full_output_path = output_folder / f"{input_image_path.stem}.png"
        image_bytes = base64.b64decode(image_base64)
        
        # Save the image to a file
        with open(full_output_path, "wb") as f:
            f.write(image_bytes)
        
        print(f"File was saved succesfully to: {full_output_path}")

        full_output_path_polaroid = polaroid_folder / f"{input_image_path.stem}.png"
        logo1_path = base_dir / "styling/bearingpoint_logo_red.png"
        logo2_path = base_dir / "styling/data_expo_logo.png"
        create_polaroid(
            photo_path=full_output_path,
            logo1_path = logo1_path,
            logo2_path = logo2_path,
            output_path = full_output_path_polaroid,
            logo1_size_factor = 1.4,
            logo2_size_factor = 0.7,
            logo1_offset = (0, +20),
            logo2_offset = (+10, 0)
        )

        print_image_direct(image_path=full_output_path_polaroid)
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"API call, adding styling and sending printer call took: {elapsed:.2f} seconds.")
    except OpenAIError as e:
        print(f"OpenAI API error occurred: {e}")
    except FileNotFoundError:
        print(f"Error: File not found - {input_image_path}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def create_polaroid(photo_path, logo1_path, logo2_path, output_path, dpi=300, size_mm="A6", 
                    logo1_size_factor=1.2, logo2_size_factor=0.8,
                    logo1_offset=(0,0), logo2_offset=(0,0)):
    
    if size_mm == "A6":
        size_mm = (105, 148)
    elif size_mm == "A4":
        size_mm = (210,297)
    else:
        print("error: improper paper format was passed, try A6 or A4")
    mm_to_inch = 0.0393701
    width_px = int(size_mm[0] * mm_to_inch * dpi)
    height_px = int(size_mm[1] * mm_to_inch * dpi)

    border_side = int(width_px * 0.05)     # 5% side borders
    border_top = int(height_px * 0.05)     # 5% top border
    border_bottom = int(height_px * 0.15)  # 15% bottom border for logos

    photo = Image.open(photo_path).convert("RGB")
    logo1 = Image.open(logo1_path).convert("RGBA")
    logo2 = Image.open(logo2_path).convert("RGBA")

    photo_area_width = width_px - 2 * border_side
    photo_area_height = height_px - border_top - border_bottom

    photo.thumbnail((photo_area_width, photo_area_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (width_px, height_px), "white")

    photo_x = (width_px - photo.width) // 2
    photo_y = border_top + (photo_area_height - photo.height) // 2
    canvas.paste(photo, (photo_x, photo_y))

    max_logo_height = int(border_bottom * 0.7)
    max_logo_width = int(width_px * 0.4)

    def resize_logo(logo):
        logo.thumbnail((max_logo_width, max_logo_height), Image.Resampling.LANCZOS)
        return logo

    logo1 = resize_logo(logo1)
    logo2 = resize_logo(logo2)

    # Apply size factors
    new_logo1_size = (int(logo1.width * logo1_size_factor), int(logo1.height * logo1_size_factor))
    logo1 = logo1.resize(new_logo1_size, Image.Resampling.LANCZOS)

    new_logo2_size = (int(logo2.width * logo2_size_factor), int(logo2.height * logo2_size_factor))
    logo2 = logo2.resize(new_logo2_size, Image.Resampling.LANCZOS)

    spacing = int(width_px * 0.05)
    logos_total_width = logo1.width + logo2.width + spacing

    logos_start_x = (width_px - logos_total_width) // 2
    logos_y = height_px - border_bottom + (border_bottom - max(logo1.height, logo2.height)) // 2

    # Paste logos with offset
    canvas.paste(logo1, (logos_start_x + logo1_offset[0], logos_y + logo1_offset[1]), logo1)
    canvas.paste(logo2, (logos_start_x + logo1.width + spacing + logo2_offset[0], logos_y + logo2_offset[1]), logo2)

    canvas.save(output_path, dpi=(dpi, dpi))
    print("Styling was added successfully")

def print_image_direct(
    image_path,
    printer_name="HP417610 (HP OfficeJet Pro 7720 series)",
    offset_x=0,          # in printer pixels: +right, -left
    offset_mm=0,      # optional: overrides offset_x (mm -> px)
    debug_print_caps=False
):
    """
    Print an image centered on the *physical page*, compensating for asymmetric printer margins.

    - Positive offset_x moves the image to the RIGHT, negative to the LEFT.
    - If offset_mm is provided, it overrides offset_x (converted using printer DPI).

    The image is uniformly scaled to fit within the printable area.
    """
    image_path = str(image_path)

    # Open the printer and create a printer DC
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer_name)

        # Ensure pixel units (MM_TEXT is default, but we set it explicitly)
        dc.SetMapMode(win32con.MM_TEXT)

        # --- Device caps we need ---
        printable_w  = dc.GetDeviceCaps(win32con.HORZRES)         # width of printable area (px)
        printable_h  = dc.GetDeviceCaps(win32con.VERTRES)         # height of printable area (px)
        phys_w       = dc.GetDeviceCaps(win32con.PHYSICALWIDTH)   # full physical page width (px)
        phys_h       = dc.GetDeviceCaps(win32con.PHYSICALHEIGHT)  # full physical page height (px)
        off_x        = dc.GetDeviceCaps(win32con.PHYSICALOFFSETX) # left non-printable margin (px)
        off_y        = dc.GetDeviceCaps(win32con.PHYSICALOFFSETY) # top non-printable margin (px)
        dpi_x        = dc.GetDeviceCaps(win32con.LOGPIXELSX)
        dpi_y        = dc.GetDeviceCaps(win32con.LOGPIXELSY)

        if debug_print_caps:
            print(f"[Printer caps] phys_w={phys_w}, phys_h={phys_h}, "
                  f"printable_w={printable_w}, printable_h={printable_h}, "
                  f"off_x={off_x}, off_y={off_y}, dpi_x={dpi_x}, dpi_y={dpi_y}")

        # Allow convenient mm-based offset (overrides pixel offset if provided)
        if offset_mm is not None:
            offset_x = int(round((offset_mm / 25.4) * dpi_x))

        # Start the print job
        dc.StartDoc(image_path)
        dc.StartPage()

        # Load the image and prepare a DIB
        img = Image.open(image_path)
        dib = ImageWin.Dib(img)
        img_w, img_h = img.size

        # Scale uniformly to fit *inside the printable area*
        scale = min(printable_w / img_w, printable_h / img_h)
        scaled_w = int(img_w * scale)
        scaled_h = int(img_h * scale)

        # ---- Center with respect to the PHYSICAL PAGE ----
        # Compute the physical-page-centered position first:
        left_phys = (phys_w - scaled_w) // 2 + int(offset_x)   # apply horizontal offset on physical page
        top_phys  = (phys_h - scaled_h) // 2

        # Convert from physical-page coordinates to printable-area coordinates
        # by subtracting the printer's physical offsets (non-printable margins)
        left   = left_phys - off_x
        top    = top_phys  - off_y
        right  = left + scaled_w
        bottom = top  + scaled_h

        # Clamp to printable area to avoid driver clipping (keeps visual center correct)
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

        # Draw the image at the computed rectangle
        dib.draw(dc.GetHandleOutput(), (left, top, right, bottom))

        # Finish the job
        dc.EndPage()
        dc.EndDoc()
        dc.DeleteDC()

        print(f"Printed centered on physical page (offset_x={offset_x}px).")

    except Exception as e:
        print(f"Printing failed: {e}")
    finally:
        win32print.ClosePrinter(hPrinter)

if __name__ == "__main__":
    start_monitoring()
