import fitz  # PyMuPDF
import pdfplumber
import pandas as pd
import hashlib
from pathlib import Path
import re


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

            tables = page.extract_tables()

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