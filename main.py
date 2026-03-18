import os
import io
import hashlib
import shutil
import json
from PIL import Image

# 兼容低版本 Python 的 TOML 解析
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("缺少 TOML 解析库。请运行: pip install tomli")
        exit(1)

# --- 目录常量 ---
INPUT_DIR = "input"
OUTPUT_DIR = "output"
PAGES_DIR_NAME = "pages"
LANDSCAPE_DIR_NAME = "landscape"
CONFIG_FILE = "config.toml"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"找不到 {CONFIG_FILE}，请确保它在根目录。")
        exit(1)
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)

def get_file_hash(filepath, length):
    """通过读取文件内容计算哈希，作为唯一且固定的文件名"""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()[:length]

def get_existing_outputs():
    """扫描输出目录，建立已经处理过的图片索引，避免重复计算"""
    existing = {}
    if not os.path.exists(OUTPUT_DIR):
        return existing
    
    for root, _, files in os.walk(OUTPUT_DIR):
        for file in files:
            # 忽略非图片文件
            if file.endswith((".html", ".js", ".txt")):
                continue
            name_without_ext = os.path.splitext(file)[0]
            rel_path = os.path.relpath(os.path.join(root, file), OUTPUT_DIR)
            existing[name_without_ext] = rel_path.replace(os.sep, "/")
    return existing

def process_image(input_path, config, existing_outputs):
    """核心图片处理逻辑"""
    img_cfg = config["image"]
    img_name = get_file_hash(input_path, img_cfg["name_length"])
    
    # 命中缓存：文件内容未变，直接返回已有路径
    if img_name in existing_outputs:
        print(f"[跳过] 已存在: {input_path} -> {existing_outputs[img_name]}")
        return existing_outputs[img_name]

    try:
        file_size_kb = os.path.getsize(input_path) / 1024
        original_ext = os.path.splitext(input_path)[1].lower()
        
        # 懒加载：获取宽高等元数据
        img = Image.open(input_path)
        width, height = img.size
        is_landscape = width >= height

        # 检查格式是否一致
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

        # 确定输出子目录
        if is_landscape:
            out_rel_dir = LANDSCAPE_DIR_NAME
        else:
            rel_input_dir = os.path.relpath(os.path.dirname(input_path), INPUT_DIR)
            out_rel_dir = "" if rel_input_dir == "." else rel_input_dir

        out_dir = os.path.join(OUTPUT_DIR, out_rel_dir)
        os.makedirs(out_dir, exist_ok=True)
        out_filepath = os.path.join(out_dir, f"{img_name}{out_ext}")

        # 优化：免压缩直接物理复制
        if format_ok and size_ok and dimension_ok:
            img.close()
            shutil.copy2(input_path, out_filepath)
            print(f"[直传] 复制: {input_path} -> {out_filepath} ({file_size_kb:.1f} KB)")
            
            final_rel_path = os.path.relpath(out_filepath, OUTPUT_DIR).replace(os.sep, "/")
            existing_outputs[img_name] = final_rel_path
            return final_rel_path

        # 需要重新编码的流程
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

def generate_robots_txt():
    """生成 robots.txt 以明确禁止所有爬虫抓取"""
    robots_path = os.path.join(OUTPUT_DIR, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /")
    print("\n[完成] robots.txt 已生成")

def generate_random_api(image_paths, config):
    """生成 Cloudflare Pages 高级模式 (_worker.js)"""
    worker_path = os.path.join(OUTPUT_DIR, "_worker.js")
    security_cfg = config.get("security", {})
    api_key = security_cfg.get("api_key", "")
    
    paths_array = json.dumps([f"/{p.replace(os.sep, '/')}" for p in image_paths])

    js_content = f"""export default {{
    async fetch(request, env) {{
        const url = new URL(request.url);
        
        if (url.pathname === '/random') {{
            const targetKey = "{api_key}";
            if (targetKey !== "") {{
                const userKey = url.searchParams.get('key');
                if (userKey !== targetKey) {{
                    return new Response('401 Unauthorized', {{ status: 401 }});
                }}
            }}

            const images = {paths_array};
            if (images.length === 0) {{
                return new Response('Not Found', {{ status: 404 }});
            }}
            
            const randomImage = images[Math.floor(Math.random() * images.length)];
            const redirectUrl = new URL(randomImage, request.url);
            
            return new Response(null, {{
                status: 302,
                headers: {{
                    "Location": redirectUrl.toString(),
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache"
                }}
            }});
        }}
        
        return env.ASSETS.fetch(request);
    }}
}};
"""
    with open(worker_path, "w", encoding="utf-8") as f:
        f.write(js_content)
    print(f"[完成] _worker.js 动态路由已生成")

def generate_index_html(image_paths):
    """生成主页索引及分页子页面"""
    pages_dir = os.path.join(OUTPUT_DIR, PAGES_DIR_NAME)
    os.makedirs(pages_dir, exist_ok=True)

    groups = {}
    for path in image_paths:
        dirname = os.path.dirname(path)
        if not dirname: dirname = "根目录"
        if dirname not in groups:
            groups[dirname] = []
        groups[dirname].append(path)

    common_css = """
    <style>
        :root { --primary: #007bff; --bg: #f8f9fa; --card-bg: #ffffff; --text: #333; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: var(--bg); color: var(--text); padding: 20px; max-width: 1400px; margin: 0 auto; }
        h1, h2 { text-align: center; color: #2c3e50; }
        .nav-bar { display: flex; align-items: center; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #e9ecef; }
        .back-btn { text-decoration: none; background: var(--primary); color: white; padding: 8px 16px; border-radius: 6px; font-weight: bold; transition: 0.2s; }
        .back-btn:hover { background: #0056b3; }
        .nav-title { flex-grow: 1; text-align: center; margin: 0; padding-right: 80px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
        .folder-card { background: var(--card-bg); border-radius: 10px; padding: 25px; text-align: center; text-decoration: none; color: inherit; box-shadow: 0 4px 6px rgba(0,0,0,0.05); transition: transform 0.2s, box-shadow 0.2s; border: 1px solid #e9ecef; }
        .folder-card:hover { transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.1); border-color: var(--primary); }
        .folder-icon { font-size: 40px; margin-bottom: 10px; }
        .img-card { background: var(--card-bg); border-radius: 8px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.08); display: flex; flex-direction: column; }
        .img-container { width: 100%; aspect-ratio: 16/9; background: #eee; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .img-container img { width: 100%; height: 100%; object-fit: contain; transition: opacity 0.3s; }
        .info { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
        .info p { margin: 0; font-size: 12px; color: #666; word-break: break-all; text-align: center; }
        .copy-btn { background: #f1f3f5; border: 1px solid #ced4da; padding: 6px; border-radius: 4px; cursor: pointer; font-size: 13px; color: #495057; transition: 0.2s; width: 100%; }
        .copy-btn:hover { background: #e2e6ea; }
        .copy-btn.success { background: #d4edda; border-color: #c3e6cb; color: #155724; }
    </style>
    """

    copy_script = """
    <script>
        function copyUrl(btn, relPath) {
            const absoluteUrl = new URL(relPath, window.location.href).href;
            navigator.clipboard.writeText(absoluteUrl).then(() => {
                const originalText = btn.innerText;
                btn.innerText = '✅ 已复制链接';
                btn.classList.add('success');
                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.classList.remove('success');
                }, 1500);
            }).catch(err => {
                alert('复制失败，请手动右键复制图片地址');
            });
        }
    </script>
    """

    group_html_map = {}
    
    # 1. 生成子页面
    for group_name in sorted(groups.keys()):
        safe_filename = group_name.replace("/", "_").replace("\\", "_") + ".html"
        group_html_map[group_name] = safe_filename
        page_path = os.path.join(pages_dir, safe_filename)
        
        html = [
            '<!DOCTYPE html>', '<html lang="zh-CN">', '<head>',
            '    <meta charset="UTF-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f'    <title>{group_name} - 图库</title>',
            common_css,
            '</head>', '<body>',
            '    <div class="nav-bar">',
            '        <a href="../index.html" class="back-btn">⬅ 返回首页</a>',
            f'        <h2 class="nav-title">📁 {group_name}</h2>',
            '    </div>',
            '    <div class="grid">'
        ]
        
        for path in sorted(groups[group_name]):
            img_rel_path = f"../{path}"
            html.append('        <div class="img-card">')
            html.append(f'            <a href="{img_rel_path}" target="_blank" class="img-container">')
            html.append(f'                <img src="{img_rel_path}" loading="lazy" alt="{path}">')
            html.append('            </a>')
            html.append('            <div class="info">')
            html.append(f'                <p>/{path}</p>')
            html.append(f'                <button class="copy-btn" onclick="copyUrl(this, \'{img_rel_path}\')">📋 复制图片直链</button>')
            html.append('            </div>')
            html.append('        </div>')
            
        html.extend(['    </div>', copy_script, '</body>', '</html>'])
        
        with open(page_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html))

    # 2. 生成主页
    main_html = [
        '<!DOCTYPE html>', '<html lang="zh-CN">', '<head>',
        '    <meta charset="UTF-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '    <title>图床相册索引</title>',
        common_css,
        '</head>', '<body>',
        '    <h1>🖼️ 我的图库索引</h1>',
        '    <div class="grid" style="margin-top: 40px;">'
    ]

    for group_name in sorted(groups.keys()):
        count = len(groups[group_name])
        target_html = f"{PAGES_DIR_NAME}/{group_html_map[group_name]}"
        
        main_html.append(f'        <a href="{target_html}" class="folder-card">')
        main_html.append('            <div class="folder-icon">📁</div>')
        main_html.append(f'            <h3 style="margin:10px 0;">{group_name}</h3>')
        main_html.append(f'            <p style="color:#888; margin:0;">共 {count} 张图</p>')
        main_html.append('        </a>')

    main_html.extend(['    </div>', '</body>', '</html>'])
    
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(main_html))
        
    print(f"[完成] HTML 静态索引生成完毕")

def main():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    config = load_config()
    existing_outputs = get_existing_outputs()
    
    all_final_paths = []
    total_size_bytes = 0

    print("=== 开始处理图床图片 ===")
    for root, _, files in os.walk(INPUT_DIR):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                input_path = os.path.join(root, file)
                result_path = process_image(input_path, config, existing_outputs)
                if result_path:
                    all_final_paths.append(result_path)
                    out_full_path = os.path.join(OUTPUT_DIR, result_path.replace("/", os.sep))
                    if os.path.exists(out_full_path):
                        total_size_bytes += os.path.getsize(out_full_path)

    if not all_final_paths:
        print("\n提示: 未在 input 文件夹中发现新图片。")
    else:
        generate_index_html(all_final_paths)
        generate_robots_txt()
        generate_random_api(all_final_paths, config)
        
        # --- 最终统计报告 ---
        total_size_mb = total_size_bytes / (1024 * 1024)
        security_cfg = config.get("security", {})
        api_key = security_cfg.get('api_key', '')
        api_status = f"已启用 (/random?key={api_key})" if api_key else "已公开启用 (/random)"
        
        print("\n" + "="*40)
        print(f"📊 图床构建报告")
        print(f"✅ 处理完毕: 共 {len(all_final_paths)} 张")
        print(f"📦 预估空间: {total_size_mb:.2f} MB")
        print(f"🛡️ 隐私防护: robots.txt 已部署")
        print(f"🎲 随机接口: {api_status}")
        print(f"🚀 部署操作: 请将 output 目录上传至 Cloudflare Pages")
        print("="*40)

if __name__ == "__main__":
    main()