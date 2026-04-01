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
        # --- 1. Canvas Setup (Paper Size) ---
        # 880 = Width, 400 = Height
        W, H = 880, 400
        img = Image.new('RGB', (W, H), 'white')
        draw = ImageDraw.Draw(img)
        
        # ====================================================================
        #                     FONT SETTINGS (SIZE YAHAN BADHAYEIN)
        # ====================================================================
        try:
            if sys.platform != "win32":
                # --- RASPBERRY PI FONTS ---
                font_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                font_norm = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                
                # 1. BRAND NAME (Sabse upar wala) - Abhi 38 hai
                font_header = ImageFont.truetype(font_bold, 40) 

                # 2. DETAILS (Size, Color, Pressure) - Abhi 32 hai
                font_main = ImageFont.truetype(font_norm, 38)   

                # 3. INFO (Operator, Batch, Time) - Abhi 24 hai
                font_sub = ImageFont.truetype(font_norm, 32)    

                # 4. BOTTOM ID (Niche wala ID number) - Abhi 28 hai
                font_id = ImageFont.truetype(font_bold, 48)     

                # 5. MANUFACTURER (Bhaiji Products) - Abhi 28 hai
                font_mfg = ImageFont.truetype(font_bold, 28) 
            else:
                # --- WINDOWS FONTS (Backup) ---
                font_header = ImageFont.truetype("arialbd.ttf", 38) # Brand
                font_main = ImageFont.truetype("arial.ttf", 28)     # Details
                font_sub = ImageFont.truetype("arial.ttf", 22)      # Info
                font_id = ImageFont.truetype("arialbd.ttf", 34)     # ID
                font_mfg = ImageFont.truetype("arialbd.ttf", 25)    # Mfg Name
        except:
            # Agar koi font na mile to Default use karega
            font_header = font_main = font_sub = font_id = font_mfg = ImageFont.load_default()

        # ====================================================================
        #                     PRINTING & POSITIONING
        #       (X = Left se kitna dur, Y = Upar se kitna niche)
        # ====================================================================

        # --- A. Brand Name ---
        # X=40, Y=15 (Thoda upar rakha hai)
        draw.text((40, 15), str(label_data['pipe_name']), font=font_header, fill="black")
        
        # --- B. Underline (Brand ke niche line) ---
        draw.line((40, 60, 400, 60), fill="black", width=3)

        # --- C. Size & Color ---
        # X=40, Y=70
        draw.text((40, 70), f"{label_data['size']} | {label_data['color']}", font=font_main, fill="black")
        
        # --- D. Pressure ---
        pressure_val = label_data.get('pressure', '')
        if pressure_val:
            # X=40, Y=110
            draw.text((40, 110), f"Pres: {pressure_val}", font=font_main, fill="black")

        # --- E. Operator Info ---
        # X=40, Y=160
        draw.text((40, 160), f"Op: {label_data['operator']}", font=font_sub, fill="black")
        
        # --- F. Batch & Time ---
        # X=40, Y=190
        batch_str = label_data.get('batch', '')
        draw.text((40, 190), f"{batch_str}   Time: {label_data['created_at'][11:16]}", font=font_sub, fill="black")

        # --- G. QR CODE ---
        qr = qrcode.make(json.dumps({"id": label_data['id']}))
        # Size Yahan Change karein: (170, 170)
        qr = qr.resize((200, 200))
        # Position: X=620 (Right Side), Y=20 (Top)
        img.paste(qr, (620, 20)) 

        # --- H. MANUFACTURER NAME (Bhaiji Products) ---
        # X=550, Y=200 (QR ke niche)
        draw.text((550, 200), "Bhaiji Products", font=font_mfg, fill="black")

        # --- I. BOTTOM MANUAL ID ---
        # X=40, Y=280 (Niche Left side)
        draw.text((40, 280), f"ID: {label_data['id']}", font=font_id, fill="black")

        # --- J. BARCODE ---
        try:
            barcode_class = barcode.get_barcode_class('code128')
            my_barcode = barcode_class(str(label_data['id']), writer=ImageWriter())
            buffer = io.BytesIO()
            my_barcode.write(buffer, options={"write_text": False, "module_height": 5.0, "quiet_zone": 1.0})
            buffer.seek(0)
            
            # Barcode ka Size Yahan Change karein: (Width=450, Height=60)
            barcode_img = Image.open(buffer).resize((450, 60))
            
            # Barcode ki Position: X=380, Y=260
            img.paste(barcode_img, (380, 260))
        except Exception as e:
            print(f"Barcode Error: {e}")

        # --- PRINTING COMMANDS (DO NOT CHANGE) ---
        if sys.platform != "win32":
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                img.save(tmp_file.name)
                tmp_path = tmp_file.name
            cmd = [
    "lp",
    "-d", printer_name,
    "-o", "fit-to-page",
    "-o", "Darkness=21",
    "-o", "zePrintRate=4",
    tmp_path
]

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