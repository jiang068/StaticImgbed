# StaticImgbed 

### 静态图床生成工具
这是一个静态图床预处理脚本。它可以自动化地帮你完成图片重命名、尺寸缩放、体积压缩、横竖版自动分类，并生成一个支持 **懒加载** 和 **一键复制链接** 的优美索引网页。

---
## ✨ 功能特性

- **极速部署**：一键生成 `output` 目录，直接上传 Cloudflare Pages 等即可使用。
- **智能压缩**：自动控制单图大小（默认 < 800KB），超过 1920px 的图片自动缩放，无损格式转换。
- **自动分类**：支持多级文件夹扫描，并自动分离“横版图片”到专属目录。
- **对称算法**：基于文件哈希命名，内容不变不重复处理，极速节省算力。
- **动态链接**：内置 JS 逻辑，点击即可复制对应当前域名的图片绝对直链。
- **体验优化**：原生图片懒加载，支持“文件夹目录 -> 子页面”二级索引结构。

---
## 🛠️ 快速上手

### 1. 克隆项目
```bash
git clone https://github.com/jiang068/StaticImgbed.git
cd StaticImgbed
```
### 2. 安装依赖
```Bash
uv venv --python --3.12
uv pip install Pillow # Python 3.11 以下需要安装 tomli 
```
### 3. 开始使用  
将你的原图放入 `input/` 文件夹（支持多层级文件夹）。根据需要修改 `config.toml` 中的压缩参数。  
  
`config.toml` 参数说明:  
```txt  
max_file_size_kb     限制单张图片的最大体积 (KB)
max_dimension     限制图片长边的最大像素值
name_length     统一文件名的随机哈希长度
output_format     强制统一的输出格式 (如 jpg, webp)
```

运行脚本：
```Bash
uv python main.py
```
处理完成后，将生成的 `output/` 文件夹上传至 `Cloudflare Pages` 等运营商即可。  

---

#### Cloudflare Pages 限制  

- **单文件大小限制**：最大 `25MB`

- **文件总数限制**：单次上传最多 `20,000` 个文件

---

## 🔀 /random（随机图）

- 访问 /random 返回 302 重定向到一张随机图片（由 `output/_worker.js` 提供）。
- 生成：运行 `uv python main.py`，脚本会在处理完成后生成 `output/_worker.js`。
- 部署：将 `output/` 上传到 Cloudflare Pages（需启用 Worker/Functions）。
- 更新图片后请重新运行脚本并部署以刷新随机集合。
- 如果配置了 key 请在config.toml配置调用的key。
```
如果设置为空 ""，则任何人都可以直接访问 /random
如果设置了 (例如 "your_key")，则访问路径需变为 /random?key=your_key
```
- 拼接参数指南

全库随机：
```
https://你的域名/random?key=your_key
```

指定单层目录随机：
```
https://你的域名/random?key=your_key&path=ba
（等同于 &path=/ba 或 &path=/ba/）
```
指定多层子目录随机：
```
https://你的域名/random?key=your_key&path=wuwa/sub
```

---