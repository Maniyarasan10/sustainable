from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from routers import auth, issues
from routers import help as help_router
from routers import users as users_router
from routers import leaderboard as leaderboard_router
from routers import notifications as notifications_router
from routers import esp32 as esp32_router
from routers import devices as devices_router
from fastapi.staticfiles import StaticFiles
import os
from pathlib import Path

# Initialize FastAPI app
app = FastAPI(
    title="Sustainable Community API",
    description="API for managing community issues and voting",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (blueprints)
app.include_router(auth.router, prefix="/api")
app.include_router(issues.router, prefix="/api")
app.include_router(help_router.router, prefix="/api")
app.include_router(users_router.router, prefix="/api")
app.include_router(leaderboard_router.router, prefix="/api")
app.include_router(notifications_router.router, prefix="/api")
app.include_router(esp32_router.router, prefix="/api")
app.include_router(devices_router.router, prefix="/api")

# Global Exception Handler to log errors to console
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    print(f"HTTP Error {exc.status_code}: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

# Ensure static folders exist before mounting (avoid runtime error)
static_dir = Path(__file__).resolve().parent / 'static'
uploads_dir = static_dir / 'uploads'
static_dir.mkdir(parents=True, exist_ok=True)
uploads_dir.mkdir(parents=True, exist_ok=True)

# Serve uploaded media
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Sustainable Community API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/api/migrate/promote-first-user")
def promote_first_user():
    """Migration: Promote first registered user to admin role (one-time setup)"""
    from db_mongo import users_col
    from datetime import datetime
    
    # Find and promote the first user in the database
    user = users_col.find_one(sort=[("created_at", 1)])
    if not user:
        return {"success": False, "message": "No users found in database"}
    
    user_id = user.get('_id')
    current_role = user.get('role', 'user')
    
    # Promote to admin
    users_col.update_one(
        {"_id": user_id},
        {"$set": {"role": "admin", "is_admin": True, "promoted_at": datetime.utcnow()}}
    )
    
    return {
        "success": True,
        "message": f"User {user_id} promoted to admin",
        "previous_role": current_role,
        "new_role": "admin"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)