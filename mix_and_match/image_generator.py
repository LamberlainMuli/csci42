from io import BytesIO
from PIL import Image
from PIL.Image import Resampling
import os

def generate_outfit_image(outfit):
    """
    Given a UserOutfit instance, generate a composite PNG image of size 500x500.
    OutfitItems are sorted by z_index (ascending) so lower layers are drawn first.
    Each product's primary image is resized based on the outfit item's scale and
    pasted onto the canvas at the stored (position_x, position_y).
    """
    canvas_size = (500, 500)
    canvas_img = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
    
    items = outfit.items.all().order_by('z_index')
    
    for item in items:
        if item.product.images.filter(is_primary=True).exists():
            prod_img_field = item.product.images.filter(is_primary=True).first().image
        elif item.product.images.exists():
            prod_img_field = item.product.images.first().image
        else:
            continue

        try:
            prod_img = Image.open(prod_img_field.path).convert("RGBA")
        except Exception:
            continue

        base_width = 100
        new_width = int(base_width * item.scale)
        w_percent = new_width / float(prod_img.size[0])
        new_height = int(float(prod_img.size[1]) * w_percent)
        prod_img = prod_img.resize((new_width, new_height), Resampling.LANCZOS)
        
        pos = (int(item.position_x), int(item.position_y))
        canvas_img.paste(prod_img, pos, prod_img)
    
    output = BytesIO()
    canvas_img.save(output, format="PNG")
    output.seek(0)
    return output
