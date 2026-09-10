from PIL import Image

def pad_to_square(image, fill_color=(114, 114, 114)):  # 중립 회색
    width, height = image.size
    max_side = max(width, height)
    new_image = Image.new("RGB", (max_side, max_side), fill_color)
    new_image.paste(image, ((max_side - width) // 2, (max_side - height) // 2))
    return new_image

img = Image.open("glass4-2.jpg").convert("RGB")
padded = pad_to_square(img, fill_color=(114, 114, 114))
padded.save("glass4-2_padded_gray.jpg")