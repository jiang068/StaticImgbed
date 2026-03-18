import os
import io
import hashlib
import shutil
from PIL import Image

# 导入基础配置常量
from config import INPUT_DIR, OUTPUT_DIR, LANDSCAPE_DIR_NAME

def get_file_hash(filepath, length):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()[:length]

def get_existing_outputs():
    existing = {}
    if not os.path.exists(OUTPUT_DIR):
        return existing
    
    for root, _, files in os.walk(OUTPUT_DIR):
        for file in files:
            if file.endswith((".html", ".js", ".json", ".txt")):
                continue
            name_without_ext = os.path.splitext(file)[0]
            rel_path = os.path.relpath(os.path.join(root, file), OUTPUT_DIR)
            existing[name_without_ext] = rel_path.replace(os.sep, "/")
    return existing

def process_image(input_path, config, existing_outputs):
    img_cfg = config["image"]
    img_name = get_file_hash(input_path, img_cfg["name_length"])
    
    if img_name in existing_outputs:
        print(f"[跳过] 已存在: {input_path} -> {existing_outputs[img_name]}")
        return existing_outputs[img_name]

    try:
        file_size_kb = os.path.getsize(input_path) / 1024
        original_ext = os.path.splitext(input_path)[1].lower()
        
        img = Image.open(input_path)
        width, height = img.size
        is_landscape = width >= height

        format_ok = True
        out_ext = original_ext
        
        if img_cfg["convert_format"]:
            target_ext = f".{img_cfg['output_format']}".lower()
            out_ext = target_ext
            
            if target_ext == original_ext:
                format_ok = True
            elif target_ext in (".jpg", ".jpeg") and original_ext in (".jpg", ".jpeg"):
                format_ok = True
            else:
                format_ok = False

        size_ok = file_size_kb <= img_cfg["max_file_size_kb"]
        dimension_ok = max(width, height) <= img_cfg["max_dimension"]

        if is_landscape:
            out_rel_dir = LANDSCAPE_DIR_NAME
        else:
            rel_input_dir = os.path.relpath(os.path.dirname(input_path), INPUT_DIR)
            out_rel_dir = "" if rel_input_dir == "." else rel_input_dir

        out_dir = os.path.join(OUTPUT_DIR, out_rel_dir)
        os.makedirs(out_dir, exist_ok=True)
        out_filepath = os.path.join(out_dir, f"{img_name}{out_ext}")

        if format_ok and size_ok and dimension_ok:
            img.close()
            shutil.copy2(input_path, out_filepath)
            print(f"[直传] 复制: {input_path} -> {out_filepath} ({file_size_kb:.1f} KB)")
            
            final_rel_path = os.path.relpath(out_filepath, OUTPUT_DIR).replace(os.sep, "/")
            existing_outputs[img_name] = final_rel_path
            return final_rel_path

        if img.mode in ("RGBA", "P") and out_ext in (".jpg", ".jpeg"):
            img = img.convert("RGB")

        if not dimension_ok:
            ratio = img_cfg["max_dimension"] / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        quality = img_cfg["jpg_quality"]
        output_format_pil = "JPEG" if out_ext in (".jpg", ".jpeg") else out_ext.replace(".", "").upper()

        while True:
            buffer = io.BytesIO()
            if output_format_pil == "JPEG":
                img.save(buffer, format=output_format_pil, quality=quality, optimize=True)
            else:
                img.save(buffer, format=output_format_pil)
            
            new_size_kb = buffer.tell() / 1024
            
            if new_size_kb <= img_cfg["max_file_size_kb"] or output_format_pil != "JPEG" or quality <= 15:
                with open(out_filepath, "wb") as f:
                    f.write(buffer.getvalue())
                break
            quality -= 5 

        print(f"[压缩] 处理: {input_path} -> {out_filepath} ({new_size_kb:.1f} KB)")
        
        final_rel_path = os.path.relpath(out_filepath, OUTPUT_DIR).replace(os.sep, "/")
        existing_outputs[img_name] = final_rel_path
        return final_rel_path

    except Exception as e:
        print(f"[错误] 处理 {input_path} 失败: {e}")
        return None