from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List, Dict, Any, Optional
import os
import uuid
import json
import asyncio
from datetime import datetime

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create uploads directory if it doesn't exist
os.makedirs("uploads", exist_ok=True)

# Mount static files directory
app.mount("/files", StaticFiles(directory="uploads"), name="files")

# In-memory storage for documents (replace with database in production)
documents = {}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[Dict[str, Any]]] = {}

    async def connect(self, websocket: WebSocket, document_id: str, username: str):
        await websocket.accept()
        if document_id not in self.active_connections:
            self.active_connections[document_id] = []
        
        # Store connection with username
        self.active_connections[document_id].append({
            "websocket": websocket,
            "username": username
        })
        
        # Notify others that a new user joined
        await self.broadcast(
            json.dumps({
                "type": "user-joined",
                "user": username
            }),
            document_id,
            exclude_websocket=websocket
        )

    def disconnect(self, websocket: WebSocket, document_id: str):
        username = None
        if document_id in self.active_connections:
            # Find and remove the connection
            for i, connection in enumerate(self.active_connections[document_id]):
                if connection["websocket"] == websocket:
                    username = connection["username"]
                    self.active_connections[document_id].pop(i)
                    break
            
            # Remove document entry if no connections left
            if not self.active_connections[document_id]:
                del self.active_connections[document_id]
        
        return username

    async def broadcast(self, message: str, document_id: str, exclude_websocket: Optional[WebSocket] = None):
        if document_id in self.active_connections:
            for connection in self.active_connections[document_id]:
                if connection["websocket"] != exclude_websocket:
                    await connection["websocket"].send_text(message)

manager = ConnectionManager()

@app.get("/")
async def root():
    return {"message": "Notion Alternative API"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Generate a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("uploads", unique_filename)
    
    # Save the file
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    # Return the file URL
    file_url = f"/files/{unique_filename}"
    return {"url": file_url, "filename": file.filename}

@app.get("/documents")
async def get_documents():
    return {"documents": list(documents.values())}

@app.get("/documents/{document_id}")
async def get_document(document_id: str):
    if document_id not in documents:
        return {"error": "Document not found"}
    return documents[document_id]

@app.post("/documents")
async def create_document(document: Dict[str, Any]):
    document_id = str(uuid.uuid4())
    document["id"] = document_id
    document["created_at"] = datetime.now().isoformat()
    document["updated_at"] = document["created_at"]
    documents[document_id] = document
    return document

@app.put("/documents/{document_id}")
async def update_document(document_id: str, document: Dict[str, Any]):
    if document_id not in documents:
        return {"error": "Document not found"}
    
    document["id"] = document_id
    document["updated_at"] = datetime.now().isoformat()
    documents[document_id] = document
    return document

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    if document_id not in documents:
        return {"error": "Document not found"}
    
    del documents[document_id]
    return {"message": "Document deleted"}

@app.websocket("/ws/{document_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    document_id: str, 
    username: str = Query(None)
):
    await manager.connect(websocket, document_id, username or "Anonymous")
    
    try:
        while True:
            data_text = await websocket.receive_text()
            data = json.loads(data_text)
            
            if data["type"] == "document-update":
                # Store document content
                if document_id not in documents:
                    documents[document_id] = {
                        "id": document_id,
                        "content": None,
                        "created_at": datetime.now().isoformat(),
                    }
                
                documents[document_id]["content"] = data["content"]
                documents[document_id]["updated_at"] = datetime.now().isoformat()
                
                # Broadcast to all clients in the room
                await manager.broadcast(data_text, document_id)
            
            elif data["type"] == "get-document":
                # Send document content to the client
                if document_id in documents and documents[document_id]["content"]:
                    await websocket.send_text(json.dumps({
                        "type": "load-document",
                        "content": documents[document_id]["content"]
                    }))
    
    except WebSocketDisconnect:
        username = manager.disconnect(websocket, document_id)
        if username:
            await manager.broadcast(
                json.dumps({
                    "type": "user-left",
                    "user": username
                }),
                document_id
            )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
