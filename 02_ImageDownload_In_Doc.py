import fitz  # PyMuPDF
import pdfplumber
import pandas as pd
import hashlib
from pathlib import Path
import re
from statistics import median


def safe_name(text):
    """ファイル名に使えない文字を置換"""
    return re.sub(r'[\\/:*?"<>|]', "_", text)


def image_signature(image_bytes):
    pixmap = fitz.Pixmap(image_bytes)
    color_space = pixmap.colorspace.name if pixmap.colorspace else None
    pixel_hash = hashlib.sha256(pixmap.samples).digest()
    return (
        pixmap.width,
        pixmap.height,
        pixmap.n,
        pixmap.alpha,
        color_space,
        pixel_hash,
    )


def ruled_table_settings(page):
    horizontal_rules = []

    for rect in page.rects:
        if rect["width"] < page.width * 0.15 or rect["height"] > 5:
            continue

        y = (rect["top"] + rect["bottom"]) / 2
        group = next(
            (items for rule_y, items in horizontal_rules if abs(rule_y - y) <= 1),
            None,
        )
        if group is None:
            horizontal_rules.append((y, [rect]))
        else:
            group.append(rect)

    if len(horizontal_rules) < 3:
        return None

    internal_boundaries = []
    for _, rects in horizontal_rules:
        rects.sort(key=lambda rect: rect["x0"])
        for left, right in zip(rects, rects[1:]):
            gap = right["x0"] - left["x1"]
            if 0.5 <= gap <= 6:
                internal_boundaries.append((left["x1"] + right["x0"]) / 2)

    boundary_groups = []
    for boundary in sorted(internal_boundaries):
        group = next(
            (items for center, items in boundary_groups if abs(center - boundary) <= 4),
            None,
        )
        if group is None:
            boundary_groups.append((boundary, [boundary]))
        else:
            group.append(boundary)

    minimum_matches = max(2, (len(horizontal_rules) + 1) // 2)
    vertical_boundaries = sorted(
        median(items)
        for _, items in boundary_groups
        if len(items) >= minimum_matches
    )
    if len(vertical_boundaries) < 2:
        return None

    vertical_lines = [
        min(rect["x0"] for _, rects in horizontal_rules for rect in rects),
        *vertical_boundaries,
        max(rect["x1"] for _, rects in horizontal_rules for rect in rects),
    ]

    rule_ys = sorted(y for y, _ in horizontal_rules)
    words = sorted(page.extract_words(), key=lambda word: word["top"])
    header_top = None
    word_lines = []
    for word in words:
        line = next(
            (items for top, items in word_lines if abs(top - word["top"]) <= 3),
            None,
        )
        if line is None:
            word_lines.append((word["top"], [word]))
        else:
            line.append(word)

    for _, line in reversed(word_lines):
        if max(word["bottom"] for word in line) >= rule_ys[0]:
            continue
        if rule_ys[0] - max(word["bottom"] for word in line) > 80:
            break

        occupied_columns = {
            next(
                (
                    index
                    for index, (left, right) in enumerate(
                        zip(vertical_lines, vertical_lines[1:])
                    )
                    if left <= (word["x0"] + word["x1"]) / 2 <= right
                ),
                -1,
            )
            for word in line
        }
        if len(occupied_columns - {-1}) >= 2:
            header_top = min(word["top"] for word in line) - 2
            break

    horizontal_lines = (
        [header_top] if header_top is not None else []
    ) + rule_ys
    return {
        "vertical_strategy": "explicit",
        "horizontal_strategy": "explicit",
        "explicit_vertical_lines": vertical_lines,
        "explicit_horizontal_lines": horizontal_lines,
    }


def extract_pdf_contents(pdf_path):
    pdf_path = Path(pdf_path)

    output_dir = pdf_path.parent / f"{pdf_path.stem}_extracted"
    output_dir.mkdir(exist_ok=True)

    template_dir = Path.cwd() / "template"
    if not template_dir.is_dir():
        raise FileNotFoundError(f"テンプレートフォルダーが見つかりません: {template_dir}")

    template_signatures = {
        image_signature(template_file.read_bytes())
        for template_file in template_dir.iterdir()
        if template_file.is_file()
    }

    print(f"\n処理中: {pdf_path}")

    # --------------------
    # 図（画像）抽出
    # --------------------
    doc = fitz.open(pdf_path)

    image_count = 0
    removed_image_count = 0

    for page_no in range(len(doc)):
        page = doc[page_no]

        for img_no, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]

            image = doc.extract_image(xref)

            image_bytes = image["image"]
            image_ext = image["ext"]

            image_file = (
                output_dir
                / f"page_{page_no+1:03d}"
                  f"_figure_{img_no:03d}.{image_ext}"
            )

            if image_signature(image_bytes) in template_signatures:
                image_file.unlink(missing_ok=True)
                removed_image_count += 1
                continue

            with open(image_file, "wb") as f:
                f.write(image_bytes)

            image_count += 1

    doc.close()

    # --------------------
    # 表抽出
    # --------------------
    table_count = 0

    with pdfplumber.open(pdf_path) as pdf:

        for page_no, page in enumerate(pdf.pages, start=1):

            tables = []
            table_bboxes = []

            table_settings_to_try = [None, ruled_table_settings(page)]
            table_settings_to_try.append(
                {"vertical_strategy": "text", "horizontal_strategy": "lines"}
            )
            for table_settings in table_settings_to_try:
                detected_tables = page.find_tables(table_settings=table_settings)

                for detected_table in detected_tables:
                    x0, top, x1, bottom = detected_table.bbox
                    area = (x1 - x0) * (bottom - top)

                    if any(
                        max(0, min(x1, old_x1) - max(x0, old_x0))
                        * max(0, min(bottom, old_bottom) - max(top, old_top))
                        / min(area, old_area) >= 0.8
                        for old_x0, old_top, old_x1, old_bottom, old_area
                        in table_bboxes
                    ):
                        continue

                    table_bboxes.append((x0, top, x1, bottom, area))
                    table = [
                        row
                        for row in detected_table.extract()
                        if any(cell and cell.strip() for cell in row)
                    ]
                    if table:
                        tables.append(table)

            for table_no, table in enumerate(tables, start=1):
                df = pd.DataFrame(table)

                csv_file = (
                    output_dir
                    / f"page_{page_no:03d}"
                      f"_table_{table_no:03d}.csv"
                )

                df.to_csv(
                    csv_file,
                    index=False,
                    header=False,
                    encoding="utf-8-sig"
                )

                table_count += 1

    print(
        f"完了: 画像 {image_count}個 "
        f"(テンプレート一致 {removed_image_count}個を除外) "
        f"/ 表 {table_count}個"
    )


def search_pdfs(folder):

    folder = Path(folder)

    for pdf_file in folder.rglob("*.pdf"):

        try:
            extract_pdf_contents(pdf_file)

        except Exception as e:
            print(f"エラー: {pdf_file}")
            print(e)


if __name__ == "__main__":
    search_pdfs(Path.cwd())