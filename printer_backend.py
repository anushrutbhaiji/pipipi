import json
import qrcode
import io
import os
import sys
import subprocess
import tempfile
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont

# Windows-specific imports (only loaded if on Windows)
if sys.platform == "win32":
    try:
        from PIL import ImageWin
        import win32print
        import win32ui
    except ImportError:
        pass

def silent_print_label(label_data, printer_name="TSC_TE244"):
    """
    Generates a label image and prints it.
    On Windows: Uses win32ui to print directly to DC.
    On Linux (Pi): Saves to a temp file and calls CUPS 'lp'.
    """
    try:
        # --- 1. GENERATE IMAGE (Common for both OS) ---
        # Note: 640x400 is approx 3x2 inches at 203 DPI. 
        # Adjust W, H if your physical label is different.
        W, H = 640, 400 
        img = Image.new('RGB', (W, H), 'white')
        draw = ImageDraw.Draw(img)
        
        # Load Fonts
        try:
            # On Pi, arial.ttf might not exist unless installed. 
            # Use absolute path or default if fails.
            font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 45)
            font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
            font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
        except:
            # Fallback to default if custom fonts fail
            font_lg = font_md = font_sm = font_xl = ImageFont.load_default()

        # Draw Text Info
        draw.text((20, 10), str(label_data['pipe_name']), font=font_lg, fill="black")
        draw.text((20, 65), f"{label_data['size']} | {label_data['color']}", font=font_md, fill="black")
        draw.text((20, 110), f"Wt: {label_data['weight_g']} Kg", font=font_lg, fill="black")
        draw.text((20, 180), f"Batch: {label_data['batch']}", font=font_sm, fill="black") 
        draw.text((20, 210), f"Op: {label_data['operator']}", font=font_sm, fill="black")
        # Fix: created_at might be None or short string
        time_str = label_data.get('created_at', '')[11:16] if label_data.get('created_at') else "--:--"
        draw.text((220, 210), f"Time: {time_str}", font=font_sm, fill="black")

        # Draw Pressure Class (if exists)
        pressure_val = label_data.get('pressure', '')
        if pressure_val:
            draw.text((280, 60), pressure_val, font=font_xl, fill="black")

        # Draw QR Code
        qr_data = json.dumps({"id": label_data['id']})
        qr = qrcode.make(qr_data).resize((160, 160))
        img.paste(qr, (460, 20))

        # Draw Barcode (Code128)
        try:
            barcode_class = barcode.get_barcode_class('code128')
            my_barcode = barcode_class(str(label_data['id']), writer=ImageWriter())
            buffer = io.BytesIO()
            my_barcode.write(buffer, options={"write_text": True, "font_size": 10, "module_height": 8.0})
            buffer.seek(0)
            barcode_img = Image.open(buffer).resize((400, 100))
            img.paste(barcode_img, (120, 280))
        except Exception as e:
            print(f"Barcode Error: {e}")

        # --- 2. PRINTING LOGIC ---
        
        # LINUX / RASPBERRY PI
        if sys.platform != "win32":
            # Save to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                img.save(tmp_file.name)
                tmp_path = tmp_file.name

            # Command to print using CUPS
            # -d: Specify printer name (MUST MATCH 'lpstat -p' name)
            # -o fit-to-page: Ensures the image scales to your label media
            cmd = ["lp", "-d", printer_name, "-o", "fit-to-page", tmp_path]
            
            subprocess.run(cmd, check=True)
            
            # Clean up temp file
            os.remove(tmp_path)
            return True, "Sent to CUPS"

        # WINDOWS (Legacy Support)
        else:
            if not printer_name: 
                printer_name = win32print.GetDefaultPrinter()
            
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            hDC.StartDoc("PVC Label")
            hDC.StartPage()
            ImageWin.Dib(img).draw(hDC.GetHandleOutput(), (0, 0, W, H))
            hDC.EndPage()
            hDC.EndDoc()
            hDC.DeleteDC()
            return True, "Printed on Windows"

    except Exception as e:
        return False, str(e)
