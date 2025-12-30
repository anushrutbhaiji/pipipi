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

# Windows check
if sys.platform == "win32":
    try:
        from PIL import ImageWin
        import win32print
        import win32ui
    except ImportError: pass

def silent_print_label(label_data, printer_name="ZPL"):
    try:
        # --- 1. Canvas (880x400) ---
        W, H = 880, 400
        img = Image.new('RGB', (W, H), 'white')
        draw = ImageDraw.Draw(img)
        
        # --- 2. Fonts (Thode aur chote taaki fit rahein) ---
        try:
            if sys.platform != "win32":
                font_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                font_norm = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                
                font_header = ImageFont.truetype(font_bold, 38) # Size 45 -> 38 (Safe)
                font_main = ImageFont.truetype(font_norm, 28)   # Size 30 -> 28
                font_sub = ImageFont.truetype(font_norm, 22)    # Size 22
                font_id = ImageFont.truetype(font_bold, 26)     # ID Font
            else:
                font_header = ImageFont.truetype("arialbd.ttf", 38)
                font_main = ImageFont.truetype("arial.ttf", 28)
                font_sub = ImageFont.truetype("arial.ttf", 22)
                font_id = ImageFont.truetype("arialbd.ttf", 26)
        except:
            font_header = font_main = font_sub = font_id = ImageFont.load_default()

        # --- 3. COMPACT LAYOUT (Sab kuch upar shift kiya) ---
        
        # Brand Name (Top Margin kam kiya: Y=15)
        draw.text((40, 15), str(label_data['pipe_name']), font=font_header, fill="black")
        
        # Line (Y=60)
        draw.line((40, 60, 400, 60), fill="black", width=3)

        # Size | Color (Text gap kam kiya)
        draw.text((40, 70), f"{label_data['size']} | {label_data['color']}", font=font_main, fill="black")
        
        # Pressure
        pressure_val = label_data.get('pressure', '')
        if pressure_val:
            draw.text((40, 110), f"Pres: {pressure_val}", font=font_main, fill="black")

        # Operator / Batch / Time (Sabko upar khinch liya)
        draw.text((40, 160), f"Op: {label_data['operator']}", font=font_sub, fill="black")
        draw.text((40, 190), f"Batch: {label_data['batch']}   Time: {label_data['created_at'][11:16]}", font=font_sub, fill="black")

        # --- 4. QR Code ---
        qr = qrcode.make(json.dumps({"id": label_data['id']}))
        qr = qr.resize((170, 170)) # Size 170 (Safe)
        img.paste(qr, (620, 20))   # Position Right-Top

        # --- 5. Manual ID (Upar shift kiya: Y=280) ---
        # Pehle yeh Y=315 tha, ab Y=280 hai. Boht fark padega.
        draw.text((40, 280), f"ID: {label_data['id']}", font=font_id, fill="black")

        # --- 6. Barcode (Compact & Lifted) ---
        try:
            barcode_class = barcode.get_barcode_class('code128')
            my_barcode = barcode_class(str(label_data['id']), writer=ImageWriter())
            buffer = io.BytesIO()
            
            # Module height 5.0
            my_barcode.write(buffer, options={"write_text": False, "module_height": 5.0, "quiet_zone": 1.0})
            buffer.seek(0)
            
            # Size: 450 x 60 (Height kam ki taaki bottom se na kate)
            barcode_img = Image.open(buffer).resize((450, 60))
            
            # Position: Y=260 (Pehle 290 tha). Ab yeh bottom edge se bohot dur hai.
            img.paste(barcode_img, (380, 260))
        except Exception as e:
            print(f"Barcode Error: {e}")

        # --- 7. Printing ---
        if sys.platform != "win32":
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                img.save(tmp_file.name)
                tmp_path = tmp_file.name
            
            # CUPS Command
            # fit-to-page rakha hai taaki size adjust ho jaye
            cmd = ["lp", "-d", printer_name, "-o", "fit-to-page", tmp_path]
            subprocess.run(cmd, check=True)
            os.remove(tmp_path)
            return True, "Sent to CUPS"
        else:
            if not printer_name: printer_name = win32print.GetDefaultPrinter()
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
