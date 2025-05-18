from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import uuid
import base64
from datetime import datetime

app = FastAPI()

# 配置 CORS - 允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该限制为您的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存存储
documents = {}
files_db = {}

@app.get("/")
async def root():
    return {"message": "Notion Alternative API"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# 文件上传处理
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        # 读取文件内容
        file_content = await file.read()
        
        # 生成唯一ID
        file_id = str(uuid.uuid4())
        
        # 将文件内容编码为 base64 并存储在内存中
        file_content_base64 = base64.b64encode(file_content).decode('utf-8')
        
        # 存储文件元数据
        file_data = {
            "id": file_id,
            "filename": file.filename,
            "content_type": file.content_type,
            "url": f"/files/{file_id}/content",
            "size": len(file_content),
            "content_base64": file_content_base64,
            "created_at": datetime.now().isoformat()
        }
        
        # 存储在内存
        files_db[file_id] = file_data
        
        # 返回文件信息（不包括 base64 内容）
        response_data = {
            "id": file_id,
            "url": f"/files/{file_id}/content", 
            "filename": file.filename,
            "content_type": file.content_type
        }
        
        return JSONResponse(content=response_data)
    except Exception as e:
        print(f"Error uploading file: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to upload file: {str(e)}"}
        )

# 获取文件内容
@app.get("/files/{file_id}/content")
async def get_file_content(file_id: str):
    if file_id not in files_db:
        return JSONResponse(
            status_code=404,
            content={"error": "File not found"}
        )
    
    file_data = files_db[file_id]
    
    # 解码 base64 内容
    content = base64.b64decode(file_data["content_base64"])
    
    # 返回文件内容
    return Response(
        content=content,
        media_type=file_data["content_type"]
    )

# 获取文件列表
@app.get("/files")
async def get_files():
    files_list = []
    for file_id, file_data in files_db.items():
        file_copy = file_data.copy()
        if "content_base64" in file_copy:
            del file_copy["content_base64"]
        files_list.append(file_copy)
    
    return JSONResponse(content={"files": files_list})

# 文档相关端点...