import json
import qrcode
import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont, ImageWin

def silent_print_label(label_data, printer_name=None):
    try:
        import win32print; import win32ui
        W, H = 640, 400
        img = Image.new('RGB', (W, H), 'white')
        draw = ImageDraw.Draw(img)
        
        # Fonts
        try:
            font_lg = ImageFont.truetype("arial.ttf", 45)
            font_md = ImageFont.truetype("arial.ttf", 30)
            font_sm = ImageFont.truetype("arial.ttf", 22)
            font_xl = ImageFont.truetype("arial.ttf", 55) # For Pressure
        except:
            font_lg = font_md = font_sm = font_xl = ImageFont.load_default()

        # Text Info
        draw.text((20, 10), str(label_data['pipe_name']), font=font_lg, fill="black")
        draw.text((20, 65), f"{label_data['size']} | {label_data['color']}", font=font_md, fill="black")
        draw.text((20, 110), f"Wt: {label_data['weight_g']} g", font=font_lg, fill="black")
        draw.text((20, 180), f"Batch: {label_data['batch']}", font=font_sm, fill="black") 
        draw.text((20, 210), f"Op: {label_data['operator']}", font=font_sm, fill="black")
        draw.text((220, 210), f"Time: {label_data['created_at'][11:16]}", font=font_sm, fill="black")

        # --- NEW: PRESSURE CLASS PRINTING ---
        pressure_val = label_data.get('pressure', '')
        if pressure_val:
            # Draw Pressure boldly on the right side
            draw.text((280, 60), pressure_val, font=font_xl, fill="black")

        # QR Code
        qr = qrcode.make(json.dumps({"id": label_data['id']}))
        qr = qr.resize((160, 160))
        img.paste(qr, (460, 20))

        # Barcode
        try:
            barcode_class = barcode.get_barcode_class('code128')
            my_barcode = barcode_class(str(label_data['id']), writer=ImageWriter())
            buffer = io.BytesIO()
            my_barcode.write(buffer, options={"write_text": True, "font_size": 10, "module_height": 8.0})
            buffer.seek(0)
            barcode_img = Image.open(buffer).resize((400, 100))
            img.paste(barcode_img, (120, 280))
        except: pass

        # Windows Printing Logic
        if not printer_name: printer_name = win32print.GetDefaultPrinter()
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        hDC.StartDoc("PVC Label")
        hDC.StartPage()
        ImageWin.Dib(img).draw(hDC.GetHandleOutput(), (0, 0, W, H))
        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()
        return True, "Printed"
    except Exception as e: 
        return False, str(e)
