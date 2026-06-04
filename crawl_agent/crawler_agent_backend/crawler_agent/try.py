from PIL import Image, ImageDraw

def draw_boxes(image_path, boxes, output_path="output.png", color="red", width=3):
    """
    image_path: 输入图片路径
    boxes: [(x1, y1, x2, y2), ...]  左上角和右下角坐标
    output_path: 输出图片路径
    color: 框颜色
    width: 框线宽
    """

    # 打开图片
    image = Image.open(image_path).convert("RGB")

    # 创建画布
    draw = ImageDraw.Draw(image)

    # 画每一个框
    for box in boxes:
        x1, y1, x2, y2 = box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=width)

    # 保存图片
    image.save(output_path)

    print(f"Saved to {output_path}")


if __name__ == "__main__":
    image_path = "/Users/a123/Downloads/456.jpg"

    # 示例框
    boxes = [
        (225, 657, 455, 664),
    ]

    draw_boxes(image_path, boxes, "boxed_image.png")