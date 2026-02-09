from PIL import Image
import io
import base64
import os
import sys

def update_icon_from_path(image_path):
    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found.")
        return False

    try:
        # Open source image
        img = Image.open(image_path)
        
        # Convert to RGBA if needed (for transparency support)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 1. Standard Icon (favicon/app icon) - 192x192
        img_std = img.resize((192, 192), Image.Resampling.LANCZOS)
        buffer_std = io.BytesIO()
        img_std.save(buffer_std, format="PNG")
        icon_base64 = base64.b64encode(buffer_std.getvalue()).decode("utf-8")

        # 2. iOS Icon (Apple Touch Icon) - 180x180
        img_ios = img.resize((180, 180), Image.Resampling.LANCZOS)
        buffer_ios = io.BytesIO()
        img_ios.save(buffer_ios, format="PNG")
        ios_icon_base64 = base64.b64encode(buffer_ios.getvalue()).decode("utf-8")

        # Write to icon_data.py
        with open("icon_data.py", "w", encoding="utf-8") as f:
            f.write(f'ICON_BASE64 = "{icon_base64}"\n')
            f.write(f'IOS_ICON_BASE64 = "{ios_icon_base64}"\n')
        
        # Also save directly to static folder
        img_std.save("static/icon.png", format="PNG")
        img_ios.save("static/apple-touch-icon.png", format="PNG")
        
        # Also update src_icon.png for future reference
        img.save("src_icon.png", format="PNG")
            
        print(f"Success: All icons updated from {image_path}")
        print(f"  - static/icon.png (192x192)")
        print(f"  - static/apple-touch-icon.png (180x180)")
        print(f"  - src_icon.png (original)")
        print(f"  - icon_data.py (base64)")
        return True
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        update_icon_from_path(sys.argv[1])
    else:
        print("Usage: python update_all_icons.py <path_to_image>")
