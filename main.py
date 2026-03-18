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
OUTPUT_TEXT_DIR = "output_text"  # 新增：TXT 链接输出目录
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

def generate_robots_txt():
    robots_path = os.path.join(OUTPUT_DIR, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /")
    print("[完成] robots.txt 已生成")

def generate_cloudflare_worker(image_paths, config):
    worker_path = os.path.join(OUTPUT_DIR, "_worker.js")
    security_cfg = config.get("security", {})
    api_key = security_cfg.get("api_key", "")
    
    safe_api_key = json.dumps(api_key)
    paths_array = json.dumps([f"/{p.replace(os.sep, '/')}" for p in image_paths])

    js_template = """export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        const targetKey = TARGET_KEY_PLACEHOLDER;
        const images = PATHS_ARRAY_PLACEHOLDER;
        
        // ====================
        // 1. 随机图 API 逻辑 (/random)
        // ====================
        if (url.pathname === '/random') {
            if (targetKey !== "") {
                const userKey = url.searchParams.get('key');
                if (userKey !== targetKey) {
                    return new Response('401 Unauthorized: 暗号错误', { status: 401 });
                }
            }

            let pool = images;
            const filterPath = url.searchParams.get('path');
            if (filterPath) {
                let normalizedPath = filterPath.startsWith('/') ? filterPath : '/' + filterPath;
                if (!normalizedPath.endsWith('/')) {
                    normalizedPath += '/';
                }
                pool = images.filter(img => img.startsWith(normalizedPath));
            }

            if (pool.length === 0) {
                return new Response('404 Not Found: 指定路径下没有找到图片', { status: 404 });
            }
            
            const randomImage = pool[Math.floor(Math.random() * pool.length)];
            const redirectUrl = new URL(randomImage, request.url);
            
            return new Response(null, {
                status: 302,
                headers: {
                    "Location": redirectUrl.toString(),
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache"
                }
            });
        }

        // ====================
        // 2. 页面登录鉴权逻辑
        // ====================
        if (url.pathname === '/login' && request.method === 'POST') {
            const formData = await request.formData();
            const userKey = formData.get('key');
            
            if (userKey === targetKey) {
                return new Response(null, {
                    status: 302,
                    headers: {
                        "Location": "/",
                        "Set-Cookie": `auth_session=${encodeURIComponent(targetKey)}; Path=/; HttpOnly; Max-Age=2592000`
                    }
                });
            } else {
                const errorHtml = `<html lang="zh-CN"><head><meta charset="UTF-8"><title>密码错误</title></head><body style="text-align:center;padding:50px;font-family:sans-serif;"><h2>❌ 暗号错误</h2><a href="/">返回重试</a></body></html>`;
                return new Response(errorHtml, { status: 401, headers: { "Content-Type": "text/html;charset=UTF-8" } });
            }
        }

        // ====================
        // 3. 静态 HTML 索引保护拦截
        // ====================
        if (targetKey !== "" && (url.pathname === '/' || url.pathname === '/index.html' || url.pathname.endsWith('.html'))) {
            const cookieHeader = request.headers.get('Cookie') || '';
            const cookies = Object.fromEntries(cookieHeader.split(';').map(c => c.trim().split('=')));
            
            if (decodeURIComponent(cookies['auth_session'] || '') !== targetKey) {
                const loginHtml = `<!DOCTYPE html>
                <html lang="zh-CN">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>图床安全验证</title>
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f4f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                        .login-card { background: white; padding: 40px 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); text-align: center; width: 100%; max-width: 320px; }
                        .login-card h2 { margin-top: 0; color: #333; margin-bottom: 25px; font-size: 22px; }
                        input { width: 100%; padding: 12px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; font-size: 16px; transition: 0.2s; }
                        input:focus { border-color: #007bff; outline: none; box-shadow: 0 0 0 3px rgba(0,123,255,0.1); }
                        button { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.2s; }
                        button:hover { background: #0056b3; }
                    </style>
                </head>
                <body>
                    <div class="login-card">
                        <h2>🔒 图床私密索引</h2>
                        <form method="POST" action="/login">
                            <input type="password" name="key" placeholder="请输入暗号 (API Key)" required autofocus>
                            <button type="submit">解锁图库</button>
                        </form>
                    </div>
                </body>
                </html>`;
                
                return new Response(loginHtml, {
                    headers: { "Content-Type": "text/html;charset=UTF-8" }
                });
            }
        }

        return env.ASSETS.fetch(request);
    }
};
"""
    js_content = js_template.replace("TARGET_KEY_PLACEHOLDER", safe_api_key).replace("PATHS_ARRAY_PLACEHOLDER", paths_array)

    with open(worker_path, "w", encoding="utf-8") as f:
        f.write(js_content)
    print(f"[完成] _worker.js 全站鉴权已生成")

def generate_routes_json(config):
    routes_path = os.path.join(OUTPUT_DIR, "_routes.json")
    security_cfg = config.get("security", {})
    api_key = security_cfg.get("api_key", "")
    
    includes = ["/random"]
    if api_key != "":
        includes.extend([
            "/",
            "/index.html",
            "/pages/*",
            "/login"
        ])

    routes_content = {
        "version": 1,
        "include": includes,
        "exclude": []
    }
    
    with open(routes_path, "w", encoding="utf-8") as f:
        json.dump(routes_content, f, indent=4)

def generate_index_html(image_paths):
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

# ==========================================
# 新增功能：生成全目录结构的 txt 直链文件
# ==========================================
def generate_text_links(image_paths, config):
    """
    根据 output 的目录结构，在 output_text 中生成对应的 txt 链接列表
    """
    os.makedirs(OUTPUT_TEXT_DIR, exist_ok=True)
    
    deploy_cfg = config.get("deploy", {})
    # 默认加上一个备用前缀，防止用户没配置
    base_url = deploy_cfg.get("base_url", "https://your-domain.pages.dev").rstrip("/")
    
    # 按照目录结构对图片路径进行分组
    groups = {}
    for path in image_paths:
        dirname = os.path.dirname(path)
        group_key = dirname if dirname else ""
            
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(path)
        
    for group_key, paths in groups.items():
        if group_key == "":
            # 根目录的图片，直接放在 output_text/根目录.txt 中
            target_dir = OUTPUT_TEXT_DIR
            txt_filename = "根目录.txt"
        else:
            # 创建与 output 对应的子目录结构
            target_dir = os.path.join(OUTPUT_TEXT_DIR, group_key.replace("/", os.sep))
            os.makedirs(target_dir, exist_ok=True)
            # 文件名为该层子目录的名称，例如: output_text/landscape/landscape.txt
            txt_filename = f"{os.path.basename(group_key)}.txt"
            
        txt_filepath = os.path.join(target_dir, txt_filename)
        
        with open(txt_filepath, "w", encoding="utf-8") as f:
            for p in paths:
                # 拼接完整的绝对 URL
                url_path = p.replace(os.sep, "/")
                f.write(f"{base_url}/{url_path}\n")
                
    print(f"[完成] TXT 批量链接已生成至 {OUTPUT_TEXT_DIR} 目录")


def main():
    print("\n" + "="*40)
    print("🚀 CFPages 图床自动化脚本启动")
    print("="*40 + "\n")
    
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
        print("\n=== 开始生成边缘网络配置与静态索引 ===")
        generate_index_html(all_final_paths)
        generate_robots_txt()
        generate_cloudflare_worker(all_final_paths, config)
        generate_routes_json(config)
        
        # 调用新增的 TXT 导出功能
        generate_text_links(all_final_paths, config)
        
        # --- 最终统计报告 ---
        total_size_mb = total_size_bytes / (1024 * 1024)
        security_cfg = config.get("security", {})
        api_key = security_cfg.get('api_key', '')
        
        api_status = f"已启用 (需暗号解锁)" if api_key else "已启用 (公开)"
        auth_status = "已加密" if api_key else "公开无锁"
        
        print("\n" + "="*40)
        print(f"📊 图床构建报告")
        print(f"✅ 处理完毕: 共 {len(all_final_paths)} 张")
        print(f"📦 预估空间: {total_size_mb:.2f} MB")
        print(f"🛡️ 全站鉴权: {auth_status}")
        print(f"🎲 随机接口: {api_status}")
        print(f"📝 链接导出: {OUTPUT_TEXT_DIR} 目录已就绪")
        print(f"🚀 部署操作: 请将 output 目录上传至 Cloudflare Pages")
        print("="*40 + "\n")

if __name__ == "__main__":
    main()