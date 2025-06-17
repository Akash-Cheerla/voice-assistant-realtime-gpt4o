import sys
import json
import io
import fitz  # PyMuPDF
from PIL import Image

def extract_form_fields(pdf_path):
    fields = {}
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc):
        widgets = page.widgets()
        for widget in widgets:
            field_name = widget.field_name
            if field_name:
                rect = widget.rect
                field_type = widget.field_type
                fields[field_name] = {
                    'page': page_num,
                    'rect': [rect.x0, rect.y0, rect.x1, rect.y1],
                    'type': field_type
                }
    doc.close()
    return fields

def fill_pdf(input_pdf_path, output_pdf_path, data):
    # Propagate single initials/signature
    if "MerchantInitials" in data:
        for i in range(1, 8):
            data[f"MerchantInitials{i}"] = data["MerchantInitials"]
    if "MerchantSignatureName" in data:
        data["signer1signature1"] = data["MerchantSignatureName"]
        data["signer1signature2"] = data["MerchantSignatureName"]

    for key in list(data.keys()):
        if data[key] in ("null", None):
            data[key] = ""

    print("Extracting field positions...")
    fields = extract_form_fields(input_pdf_path)
    doc = fitz.open(input_pdf_path)

    for field_name, field_info in fields.items():
        if field_name in data and data[field_name]:
            value = data[field_name]
            page = doc[field_info['page']]
            x0, y0, x1, y1 = field_info['rect']
            font_size = min(11, (y1 - y0) - 2)
            x_pos = x0 + 2
            y_pos = y0 + (y1 - y0) * 0.75

            print(f"Field: {field_name}, Value: {value}")
            page.insert_text((x_pos, y_pos), str(value), fontsize=font_size, fontname="helv")

    # Insert signature image if exists
    try:
        sig_path = "saved_signature.png"
        img = Image.open(sig_path)
        img_width, img_height = img.size

        for sig_field in ["signer1signature1", "signer1signature2"]:
            if sig_field in fields:
                field = fields[sig_field]
                page = doc[field['page']]
                x0, y0, x1, y1 = field['rect']
                rect_width = x1 - x0
                rect_height = y1 - y0
                scale = min(rect_width / img_width, rect_height / img_height)
                new_width = img_width * scale
                new_height = img_height * scale
                x_centered = x0 + (rect_width - new_width) / 2
                y_centered = y0 + (rect_height - new_height) / 2

                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                page.insert_image(
                    fitz.Rect(x_centered, y_centered, x_centered + new_width, y_centered + new_height),
                    stream=img_byte_arr.getvalue()
                )
                print(f"Signature inserted at {sig_field}")
    except Exception as e:
        print("⚠️ Signature image not inserted:", e)

    print(f"Saving to: {output_pdf_path}")
    doc.save(output_pdf_path, incremental=False, deflate=True)
    doc.close()
    print(f"✅ PDF saved to {output_pdf_path}")

def load_json_data(json_file_path):
    with open(json_file_path, 'r') as file:
        return json.load(file)

if __name__ == "__main__":
    if len(sys.argv) == 4:
        input_pdf_path = sys.argv[1]
        json_file_path = sys.argv[2]
        output_pdf_path = sys.argv[3]
        field_values = load_json_data(json_file_path)
        fill_pdf(input_pdf_path, output_pdf_path, field_values)
    else:
        print("Usage: python pdf_text_overlay.py <input_pdf_path> <json_file_path> <output_pdf_path>")
