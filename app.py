from flask import Flask, request, jsonify, send_from_directory, render_template, session, redirect, url_for, flash
from functools import wraps
import os
import uuid
from datetime import datetime
import hashlib
from werkzeug.utils import secure_filename
from typing import Dict, Union
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # 用于session加密

# 配置
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ADMIN_PASSWORD = 'PASSWORD'  # 在实际应用中应该使用加密存储的密码

# 登录装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

class ImageBed:
    def __init__(self, upload_folder: str, allowed_extensions: set, max_file_size: int = 5 * 1024 * 1024):
        self.upload_folder = upload_folder
        self.allowed_extensions = allowed_extensions
        self.max_file_size = max_file_size
        self._ensure_upload_folder()
        
    def _ensure_upload_folder(self):
        if not os.path.exists(self.upload_folder):
            os.makedirs(self.upload_folder)
            
    def _allowed_file(self, filename: str) -> bool:
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in self.allowed_extensions
            
    def _generate_unique_filename(self, original_filename: str) -> str:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4().hex[:8])
        ext = os.path.splitext(original_filename)[1]
        return f"{timestamp}_{unique_id}{ext}"
        
    def _calculate_file_hash(self, file_path: str) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
        
    def get_all_images(self) -> list:
        """获取所有图片列表"""
        files = []
        for filename in os.listdir(self.upload_folder):
            if self._allowed_file(filename):
                file_path = os.path.join(self.upload_folder, filename)
                size = os.path.getsize(file_path)
                files.append({
                    'filename': filename,
                    'url': f"/images/{filename}",
                    'size': size,
                    'date': datetime.fromtimestamp(os.path.getctime(file_path))
                })
        return sorted(files, key=lambda x: x['date'], reverse=True)
        
    def upload_image(self, file) -> Dict[str, Union[str, bool]]:
        if not file:
            return {"success": False, "message": "没有文件"}
            
        if not self._allowed_file(file.filename):
            return {"success": False, "message": "不支持的文件类型"}
            
        filename = self._generate_unique_filename(secure_filename(file.filename))
        file_path = os.path.join(self.upload_folder, filename)
        
        try:
            file.save(file_path)
            file_hash = self._calculate_file_hash(file_path)
            
            return {
                "success": True,
                "message": "上传成功",
                "filename": filename,
                "url": f"/images/{filename}",
                "hash": file_hash
            }
        except Exception as e:
            return {"success": False, "message": f"上传失败: {str(e)}"}
            
    def delete_image(self, filename: str) -> Dict[str, Union[str, bool]]:
        file_path = os.path.join(self.upload_folder, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return {"success": True, "message": "删除成功"}
            except Exception as e:
                return {"success": False, "message": f"删除失败: {str(e)}"}
        return {"success": False, "message": "文件不存在"}

# 初始化图床服务
image_bed = ImageBed(UPLOAD_FOLDER, ALLOWED_EXTENSIONS)

# 路由
@app.route('/')
@login_required
def index():
    images = image_bed.get_all_images()
    return render_template('index.html', images=images)

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', url_for('index'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['user'] = True
            return redirect(next_url)
        flash('密码错误')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "没有文件"}), 400
        
    file = request.files['file']
    result = image_bed.upload_image(file)
    
    # 构建完整的URL
    if result["success"]:
        result["full_url"] = request.host_url.rstrip('/') + result["url"]
        # 构建不同格式的URL
        result["markdown_url"] = f"![{result['filename']}]({result['full_url']})"
        result["html_url"] = f'<img src="{result["full_url"]}" alt="{result["filename"]}">'
        result["bbcode_url"] = f"[img]{result['full_url']}[/img]"
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if result["success"]:
            return jsonify(result), 200
        return jsonify(result), 400
    
    if result["success"]:
        flash('上传成功')
    else:
        flash(result["message"])
    return redirect(url_for('index'))

@app.route('/images/<filename>')
def get_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(
        UPLOAD_FOLDER, 
        filename,
        as_attachment=True,
        download_name=filename
    )

@app.route('/delete/<filename>', methods=['POST'])
@login_required
def delete_file(filename):
    result = image_bed.delete_image(filename)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if result["success"]:
            return jsonify(result), 200
        return jsonify(result), 404
    
    if result["success"]:
        flash('删除成功')
    else:
        flash(result["message"])
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8003)