from flask import Flask, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from openai import OpenAI

import os
import zipfile
import uuid
import textwrap
import json

app = Flask(__name__)

# -----------------------------
# OpenAI
# -----------------------------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


# -----------------------------
# FOLDERS
# -----------------------------
UPLOAD_FOLDER = "static/uploads"
OUTPUT_FOLDER = "static/generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

generated_images_global = []


# -----------------------------
# TEXT UTILS
# -----------------------------
def calc_text_block(text, font, wrap_width, line_spacing):
    lines = textwrap.wrap(text, width=wrap_width)
    return lines, len(lines) * line_spacing


def draw_text_block(draw, text, font, canvas_width, start_y, fill, wrap_width, line_spacing):

    lines, _ = calc_text_block(text, font, wrap_width, line_spacing)

    y = start_y

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (canvas_width - (bbox[2] - bbox[0])) / 2

        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=fill)

        y += line_spacing

    return y


def auto_font_size(text, base_size, max_width, font_path):

    size = base_size

    while size > 20:

        font = ImageFont.truetype(font_path, size)
        lines = textwrap.wrap(text, width=18)

        max_line = max([font.getlength(l) for l in lines])

        if max_line < max_width * 0.85:
            return font

        size -= 2

    return ImageFont.truetype(font_path, 24)


# -----------------------------
# HOME
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def home():

    global generated_images_global

    generated_images = []

    if request.method == "POST":

        topic = request.form["topic"]
        template = request.form["template"]

        files = request.files.getlist("images")
        image_paths = []

        # upload
        for f in files:
            ext = f.filename.split(".")[-1]
            name = f"{uuid.uuid4()}.{ext}"

            path = os.path.join(UPLOAD_FOLDER, name)
            f.save(path)

            image_paths.append(path)

        # -----------------------------
        # GPT (SAFE JSON)
        # -----------------------------
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{
                "role": "user",
                "content": f"""
{topic} 카드뉴스 생성

⚠️ 반드시 JSON만 출력 (설명 금지)

{{
  "cards":[
    {{"title":"...","content":"..."}},
    {{"title":"...","content":"..."}},
    {{"title":"...","content":"..."}},
    {{"title":"...","content":"..."}}
  ],
  "hashtags":["#태그","#태그"]
}}
"""
            }]
        )

        # -----------------------------
        # SAFE PARSE
        # -----------------------------
        content = response.choices[0].message.content

        if not content:
            raise Exception("GPT 응답 없음")

        content = content.strip()
        content = content.replace("```json", "")
        content = content.replace("```", "")

        data = json.loads(content)
        cards = data["cards"]

        # -----------------------------
        # CARD GENERATION
        # -----------------------------
        for i, card in enumerate(cards):

            img = Image.open(image_paths[i % len(image_paths)])
            img = img.resize((1080, 1350)).convert("RGBA")

            font_path = "C:/Windows/Fonts/malgun.ttf"

            # -----------------------------
            # TEMPLATE STYLE
            # -----------------------------
            if template == "dark":
                box_color = (0, 0, 0, 85)   # 🔥 투명도 핵심
                text_color = "white"
            else:
                box_color = (255, 255, 255, 120)
                text_color = "black"

            # -----------------------------
            # BLUR BOX AREA
            # -----------------------------
            card_area = img.crop((70, 760, 1010, 1240))
            card_area = card_area.filter(ImageFilter.GaussianBlur(8))
            img.paste(card_area, (70, 760))

            # -----------------------------
            # TRANSPARENT BOX LAYER
            # -----------------------------
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw_box = ImageDraw.Draw(layer)

            draw_box.rounded_rectangle(
                (70, 760, 1010, 1240),
                radius=50,
                fill=box_color
            )

            img = Image.alpha_composite(img, layer)

            draw = ImageDraw.Draw(img)

            # -----------------------------
            # TEXT
            # -----------------------------
            title_font = auto_font_size(card["title"], 70, 900, font_path)
            content_font = ImageFont.truetype(font_path, 38)
            small_font = ImageFont.truetype(font_path, 28)

            title_lines, title_h = calc_text_block(card["title"], title_font, 12, 70)
            content_lines, content_h = calc_text_block(card["content"], content_font, 22, 55)

            total_h = title_h + content_h + 40
            start_y = (760 + 1240) / 2 - total_h / 2

            draw_text_block(draw, card["title"], title_font, 1080, start_y, text_color, 12, 70)

            draw_text_block(
                draw,
                card["content"],
                content_font,
                1080,
                start_y + title_h + 40,
                text_color,
                22,
                55
            )

            # footer
            draw.text((120, 1180), "@plume_vue", font=small_font, fill=text_color)
            draw.text((930, 1180), f"{i+1}/4", font=small_font, fill=text_color)

            # save
            out = f"card_{i+1}.png"
            path = os.path.join(OUTPUT_FOLDER, out)

            img.save(path)

            generated_images.append(f"generated/{out}")

        generated_images_global = generated_images

    return render_template("index.html", generated_images=generated_images)


# -----------------------------
# DOWNLOAD
# -----------------------------
@app.route("/download")
def download():

    zip_path = "static/cards.zip"

    with zipfile.ZipFile(zip_path, "w") as z:
        for img in generated_images_global:
            z.write(f"static/{img}", arcname=os.path.basename(img))

    return send_file(zip_path, as_attachment=True)


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
