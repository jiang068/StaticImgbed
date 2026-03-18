import os
from config import load_config, INPUT_DIR, OUTPUT_DIR, SUPPORTED_EXTENSIONS
from image_handler import get_existing_outputs, process_image
from generators import (
    generate_index_html,
    generate_robots_txt,
    generate_cloudflare_worker,
    generate_routes_json,
    generate_text_links
)

def main():
    print("\n" + "="*40)
    print("🚀 CFPages 图床自动化脚本启动")
    print("="*40 + "\n")
    
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    config = load_config()
    existing_outputs = get_existing_outputs()
    
    # 这里存储的将是字典列表: [{"path": "...", "is_landscape": True}, ...]
    all_final_data = []
    total_size_bytes = 0

    print("=== 开始处理图床图片 ===")
    for root, _, files in os.walk(INPUT_DIR):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                input_path = os.path.join(root, file)
                result_data = process_image(input_path, config, existing_outputs)
                if result_data:
                    all_final_data.append(result_data)
                    out_full_path = os.path.join(OUTPUT_DIR, result_data["path"].replace("/", os.sep))
                    if os.path.exists(out_full_path):
                        total_size_bytes += os.path.getsize(out_full_path)

    if not all_final_data:
        print("\n提示: 未在 input 文件夹中发现新图片。")
    else:
        print("\n=== 开始生成边缘网络配置与静态资源 ===")
        # 将带有属性的数据传递给各个生成器
        generate_index_html(all_final_data, config)
        generate_robots_txt()
        generate_cloudflare_worker(all_final_data, config)
        generate_routes_json(config)
        generate_text_links(all_final_data, config)
        
        # --- 最终统计报告 ---
        total_size_mb = total_size_bytes / (1024 * 1024)
        security_cfg = config.get("security", {})
        api_key = security_cfg.get('api_key', '')
        
        api_status = f"已启用 (需暗号解锁)" if api_key else "已启用 (公开)"
        auth_status = "已加密" if api_key else "公开无锁"
        
        print("\n" + "="*40)
        print(f"📊 图床构建报告")
        print(f"✅ 处理完毕: 共 {len(all_final_data)} 张")
        print(f"📦 预估空间: {total_size_mb:.2f} MB")
        print(f"🛡️ 全站鉴权: {auth_status}")
        print(f"🎲 随机接口: {api_status}")
        print(f"📝 链接导出: output_text 目录已就绪")
        print(f"🚀 部署操作: 请将 output 目录上传至 Cloudflare Pages")
        print("="*40 + "\n")

if __name__ == "__main__":
    main()