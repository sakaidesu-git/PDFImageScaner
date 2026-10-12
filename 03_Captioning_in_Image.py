from pathlib import Path
from ollama import chat


IMAGE_DIR = Path("./prs095_extracted")

PROMPT = """
この画像を要件定義書・設計書のGAP分析に利用します。

以下の観点で説明してください。

1. 図の種類
2. 主な構成要素
3. システム間の関係
4. データや処理の流れ
5. 要件として読み取れる事項

最後に200文字程度で要約してください。
"""


def summarize_image(image_file):

    response = chat(
        model="qwen2.5vl:3b",
        messages=[
            {
                "role": "user",
                "content": PROMPT,
                "images": [str(image_file)]
            }
        ]
    )

    return response["message"]["content"]


def main():

    image_files = []

    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        image_files.extend(IMAGE_DIR.rglob(ext))

    print(f"画像数: {len(image_files)}")

    for image_file in image_files:

        try:

            print(f"解析中: {image_file.name}")

            summary = summarize_image(image_file)

            txt_file = image_file.with_suffix(".txt")

            txt_file.write_text(
                summary,
                encoding="utf-8"
            )

            print(f"保存: {txt_file.name}")

        except Exception as e:

            print(f"エラー: {image_file}")
            print(e)


if __name__ == "__main__":
    main()