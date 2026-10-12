import pymupdf
import pdfplumber
from pathlib import Path


def check_pdf(pdf_path):
    """図と表が見つかったページ番号をそれぞれ返す"""
    figure_pages = []
    table_pages = []

    # 図・画像の確認
    doc = pymupdf.open(pdf_path)

    for page_number, page in enumerate(doc, start=1):
        images = page.get_images(full=True)
        if images:
            figure_pages.append(page_number)

    doc.close()

    # 表の確認
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.find_tables()
            if tables:
                table_pages.append(page_number)

    return figure_pages, table_pages


def search_pdfs(folder):
    """フォルダ以下のPDFをすべて検索する"""
    folder = Path(folder)

    for pdf_path in folder.rglob("*.pdf"):
        try:
            figure_pages, table_pages = check_pdf(pdf_path)

            if not figure_pages and not table_pages:
                result = "図・表なし"
            else:
                details = []
                if figure_pages:
                    pages = ", ".join(map(str, figure_pages))
                    details.append(f"図あり: {pages}ページ")
                if table_pages:
                    pages = ", ".join(map(str, table_pages))
                    details.append(f"表あり: {pages}ページ")
                result = " / ".join(details)

            print(f"{result}: {pdf_path}")

        except Exception as e:
            print(f"判定エラー: {pdf_path} ({e})")


# 検索対象フォルダ
search_pdfs(Path.cwd())