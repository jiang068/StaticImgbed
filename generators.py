import os
import json

from config import OUTPUT_DIR, OUTPUT_TEXT_DIR, PAGES_DIR_NAME

def generate_robots_txt():
    robots_path = os.path.join(OUTPUT_DIR, "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write("User-agent: *\nDisallow: /")
    print("[完成] robots.txt 已生成")

def generate_cloudflare_worker(image_data, config):
    worker_path = os.path.join(OUTPUT_DIR, "_worker.js")
    security_cfg = config.get("security", {})
    api_key = security_cfg.get("api_key", "")
    
    # 获取站点标题
    site_cfg = config.get("site", {})
    site_title = site_cfg.get("title", "我的图库索引")
    
    safe_api_key = json.dumps(api_key)
    js_image_data = [
        {
            "path": f"/{item['path'].replace(os.sep, '/')}",
            "is_landscape": item["is_landscape"]
        }
        for item in image_data
    ]
    paths_array = json.dumps(js_image_data)

    js_template = """export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        const targetKey = TARGET_KEY_PLACEHOLDER;
        const images = PATHS_ARRAY_PLACEHOLDER;
        const siteTitle = "SITE_TITLE_PLACEHOLDER";
        
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
                pool = pool.filter(img => img.path.startsWith(normalizedPath));
            }
            
            const filterOri = url.searchParams.get('orientation');
            if (filterOri === 'landscape') {
                pool = pool.filter(img => img.is_landscape);
            } else if (filterOri === 'portrait') {
                pool = pool.filter(img => !img.is_landscape);
            }

            if (pool.length === 0) {
                return new Response('404 Not Found: 指定条件(路径/横竖版)下没有找到图片', { status: 404 });
            }
            
            const randomImage = pool[Math.floor(Math.random() * pool.length)];
            const redirectUrl = new URL(randomImage.path, request.url);
            
            return new Response(null, {
                status: 302,
                headers: {
                    "Location": redirectUrl.toString(),
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache"
                }
            });
        }

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
                const errorHtml = `<html lang="zh-CN"><head><meta charset="UTF-8"><title>密码错误 - ${siteTitle}</title></head><body style="text-align:center;padding:50px;font-family:sans-serif;"><h2>❌ 暗号错误</h2><a href="/">返回重试</a></body></html>`;
                return new Response(errorHtml, { status: 401, headers: { "Content-Type": "text/html;charset=UTF-8" } });
            }
        }

        if (targetKey !== "" && (url.pathname === '/' || url.pathname === '/index.html' || url.pathname.endsWith('.html'))) {
            const cookieHeader = request.headers.get('Cookie') || '';
            const cookies = Object.fromEntries(cookieHeader.split(';').map(c => c.trim().split('=')));
            
            if (decodeURIComponent(cookies['auth_session'] || '') !== targetKey) {
                const loginHtml = `<!DOCTYPE html>
                <html lang="zh-CN">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>${siteTitle} - 安全验证</title>
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
                        <h2>🔒 ${siteTitle}</h2>
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
    js_content = js_template.replace("TARGET_KEY_PLACEHOLDER", safe_api_key).replace("PATHS_ARRAY_PLACEHOLDER", paths_array).replace("SITE_TITLE_PLACEHOLDER", site_title)
    with open(worker_path, "w", encoding="utf-8") as f:
        f.write(js_content)
    print(f"[完成] _worker.js 已生成 (同步站点标题: {site_title})")

def generate_routes_json(config):
    routes_path = os.path.join(OUTPUT_DIR, "_routes.json")
    security_cfg = config.get("security", {})
    api_key = security_cfg.get("api_key", "")
    
    includes = ["/random"]
    if api_key != "":
        includes.extend(["/", "/index.html", "/pages/*", "/login"])

    routes_content = {
        "version": 1,
        "include": includes,
        "exclude": []
    }
    
    with open(routes_path, "w", encoding="utf-8") as f:
        json.dump(routes_content, f, indent=4)

def generate_text_links(image_data, config):
    # 将字典结构解包出路径，兼容老的逻辑
    image_paths = [item["path"] for item in image_data]
    
    os.makedirs(OUTPUT_TEXT_DIR, exist_ok=True)
    deploy_cfg = config.get("deploy", {})
    base_url = deploy_cfg.get("base_url", "https://your-domain.pages.dev").rstrip("/")
    
    groups = {}
    for path in image_paths:
        dirname = os.path.dirname(path)
        group_key = dirname if dirname else ""
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(path)
        
    for group_key, paths in groups.items():
        if group_key == "":
            target_dir = OUTPUT_TEXT_DIR
            txt_filename = "根目录.txt"
        else:
            target_dir = os.path.join(OUTPUT_TEXT_DIR, group_key.replace("/", os.sep))
            os.makedirs(target_dir, exist_ok=True)
            txt_filename = f"{os.path.basename(group_key)}.txt"
            
        txt_filepath = os.path.join(target_dir, txt_filename)
        with open(txt_filepath, "w", encoding="utf-8") as f:
            for p in paths:
                url_path = p.replace(os.sep, "/")
                f.write(f"{base_url}/{url_path}\n")
                
    print(f"[完成] TXT 批量链接已生成至 {OUTPUT_TEXT_DIR} 目录")

def generate_index_html(image_data, config):
    # 获取站点标题
    site_cfg = config.get("site", {})
    site_title = site_cfg.get("title", "我的图库索引")

    image_paths = [item["path"] for item in image_data]
    
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
            f'    <title>{group_name} - {site_title}</title>',
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
        f'    <title>{site_title}</title>',
        common_css,
        '</head>', '<body>',
        f'    <h1>🖼️ {site_title}</h1>',
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
    print(f"[完成] HTML 静态索引生成完毕 (同步站点标题: {site_title})")