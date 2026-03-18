## StaticImgbed 

#### 现代化的静态图床构建引擎

这是一个专为 Serverless 架构（如 Cloudflare Pages）设计的图床预处理引擎。它可以自动化完成图片重命名、渐进式压缩、尺寸缩放与横竖版分离，并最终生成一个支持 **原生懒加载**、**全站级目录鉴权** 以及 **多维随机图 API** 的优美索引库。

---

### ✨ 核心特性

- 🚀 **极速部署**：一键生成 `output` 静态资源目录，直接上传 Cloudflare Pages 等平台即可上线。
- 📦 **智能处理**：自动控制单图体积（默认 < 800KB），超大图片自动缩放，支持多格式向 JPG/WebP 的无损统一。
- 📂 **灵活分类**：支持多级文件夹扫描，内置开关可自动分离“横版图片”至专属目录。
- ⚡ **对称计算**：基于文件比特流哈希命名，内容不变不重复处理，极速节省本地算力。
- 🔒 **隐私防护**：原生集成 `_worker.js`，支持网页目录暗号访问，防偷窥的同时**不影响图片外链的公开引用**。
- 💰 **零损耗架构**：自动生成 `_routes.json`，确保外链图片直达 CDN 缓存，绝对**零消耗** Serverless 函数额度。
- 🎲 **多维随机 API**：内置强大的 `/random` 接口，支持按子目录、按横/竖版进行多条件组合过滤。
- 📝 **直链批量导出**：同步生成 `output_text` 目录，按文件夹归类输出绝对路径 TXT，方便一键导入博客。

---

### 🛠️ 快速上手

#### 1. 克隆项目
```bash
git clone [https://github.com/jiang068/StaticImgbed.git](https://github.com/jiang068/StaticImgbed.git)
cd StaticImgbed
```
#### 2. 环境准备
推荐使用 uv 进行现代化的 Python 环境管理：

```Bash
uv venv --python 3.12
uv pip install Pillow 
# 注：若使用 Python 3.11 以下版本，需额外安装 tomli
```
#### 3. 配置与运行
将你的原图放入 `input/` 文件夹（支持任意多层级子文件夹）。  

复制或新建 `config.toml`，根据需求调整参数。  

执行处理脚本：

```Bash
uv run main.py
```
处理完成后，直接将生成的 `output/` 文件夹整体上传至 `Cloudflare Pages` 即可。(注：`output_text` 仅供本地提取直链使用，无需上传)

### ⚙️ 配置说明 (config.toml)
请在项目根目录创建或修改 `config.toml`，核心参数如下：

```Ini, TOML
[image]
max_file_size_kb = 800        # 限制单张图片的最大体积 (KB)
max_dimension = 1920          # 限制图片长边的最大像素值
name_length = 8               # 统一文件名的随机哈希长度
convert_format = true         # 是否强制转换输出格式
output_format = "jpg"         # 强制统一的输出格式 (如 jpg, webp)
jpg_quality = 85              # JPG 初始压缩率
separate_landscape = true     # 是否将横版图片分离到专属文件夹

[security]
api_key = "your_key"          # 目录鉴权与 API 调用的暗号（留空则全站公开无锁）

[deploy]
base_url = "https://your-domain.pages.dev" # 图床绑定的域名，用于生成 TXT 直链

[site]
title = "Kei的图床"           # 网页全局标题
```

---

### 🔀 高级路由：随机图 API (/random)
部署至 `Cloudflare Pages` 后，自带的 `Serverless` 函数将提供强大的动态壁纸/随机图接口。接口通过 **302 重定向** 返回随机图片，具备极高的灵活度。

#### 基础调用规则：  

若 config.toml 中 api_key 留空，所有人可直接访问 /random。

若配置了 api_key，所有调用必须携带鉴权参数，否则返回 401，即：/random?key=your_key

### 🎲 参数拼接指南 (支持 & 组合使用)
#### 1. 全库随机

```Plaintext
https://你的域名/random?key=your_key
```
#### 2. 指定目录随机 (path)
精准匹配指定文件夹下的图片（包含其子文件夹）：

```Plaintext
单层目录：https://你的域名/random?key=your_key&path=ba
多层目录：https://你的域名/random?key=your_key&path=wuwa/sub
```
（注：&path=ba 与 &path=/ba/ 等效，引擎会自动进行绝对路径对齐）

#### 3. 指定横竖版随机 (orientation)
完美适配桌面壁纸与手机端动态背景：

```Plaintext
只要横图：https://你的域名/random?key=your_key&orientation=landscape
只要竖图：https://你的域名/random?key=your_key&orientation=portrait
```
#### 4. 终极组合魔法
从 wuwa 目录下随机抽取一张竖版图片：

```Plaintext
https://你的域名/random?key=your_key&path=wuwa&orientation=portrait
```
(注：更新本地 input 图片库后，请重新运行脚本并上传 output 目录，以刷新云端的路由策略与随机集合。)

---

#### ⚠️ Cloudflare Pages 平台限制参考
作为完全免费的托管方案，请留意以下极限阈值：

**单文件大小限制**：最大 `25MB`（本项目默认压缩至 `800KB` 以下，完美规避）

**单次构建文件数**：最多上传 `20,000` 个文件

**流量限制**：完全不限带宽与流量

---