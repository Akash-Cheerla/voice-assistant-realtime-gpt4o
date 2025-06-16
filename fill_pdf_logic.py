import sys
import json
import io
import fitz  # PyMuPDF

def extract_form_fields(pdf_path):
    """
    Extracts form field positions and metadata using PyMuPDF
    """
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
    """
    Overlays extracted field values into corresponding positions on a PDF using text rendering.
    """
    # Copy MerchantInitials into MerchantInitials1–7
    if "MerchantInitials" in data and data["MerchantInitials"]:
        for i in range(1, 8):
            data[f"MerchantInitials{i}"] = data["MerchantInitials"]

    # Copy MerchantSignatureName into signer1signature1–2
    if "MerchantSignatureName" in data and data["MerchantSignatureName"]:
        data["signer1signature1"] = data["MerchantSignatureName"]
        data["signer1signature2"] = data["MerchantSignatureName"]

    # Clean up null values
    for key in list(data.keys()):
        if data[key] == "null" or data[key] is None:
            data[key] = ""

    print("Extracting field positions...")
    fields = extract_form_fields(input_pdf_path)

    print(f"Opening PDF: {input_pdf_path}")
    doc = fitz.open(input_pdf_path)

    for field_name, field_info in fields.items():
        if field_name in data and data[field_name]:
            value = data[field_name]
            page_num = field_info['page']
            x0, y0, x1, y1 = field_info['rect']
            page = doc[page_num]

            font_size = min(11, (y1 - y0) - 2)
            x_pos = x0 + 2
            y_pos = y0 + (y1 - y0) * 0.75

            print(f"Field: {field_name}, Value: {value}")
            page.insert_text((x_pos, y_pos), str(value), fontsize=font_size, fontname="helv")

    print(f"Saving to: {output_pdf_path}")
    doc.save(output_pdf_path, incremental=False, deflate=True)
    doc.close()
    print(f"PDF successfully filled and saved to {output_pdf_path}")

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
