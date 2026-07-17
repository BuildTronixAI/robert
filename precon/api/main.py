"""
PRECON FASTAPI — Main application
Run: uvicorn precon.api.main:app --reload --port 8000

Endpoints:
  GET  /health
  GET  /projects/{id}/review-state
  GET  /projects/{id}/bid-confidence
  GET  /projects/{id}/screen1
  POST /projects/{id}/screen1/{item_id}/decide
  POST /projects/{id}/screen1/advance
  GET  /projects/{id}/screen2
  POST /projects/{id}/screen2/{item_id}/approve
  POST /projects/{id}/screen2/{item_id}/correct
  POST /projects/{id}/screen2/batch-approve
  POST /projects/{id}/screen2/advance
  GET  /projects/{id}/screen25
  POST /projects/{id}/screen25/tab-a/{item_id}/resolve
  POST /projects/{id}/screen25/tab-b/{item_id}/verify
  POST /projects/{id}/screen25/tab-b/{item_id}/remove
  POST /projects/{id}/screen25/tab-b/{item_id}/override
  POST /projects/{id}/screen25/advance
  GET  /projects/{id}/screen3
  POST /projects/{id}/screen3/{item_id}/save
  POST /projects/{id}/screen3/advance
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from precon.api.routers import projects, screen1, screen2, screen25, screen3, proposal

app = FastAPI(
    title="Buildtronix Pre-Con API",
    version="1.0.0",
    description="Pre-Construction review platform backend",
)

# CORS — allow Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", "https://buildtronix.ai"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(projects.router)
app.include_router(screen1.router)
app.include_router(screen2.router)
app.include_router(screen25.router)
app.include_router(screen3.router)
app.include_router(proposal.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "buildtronix-precon-api", "version": "1.0.0"}


@app.get("/")
def root():
    return {"message": "Buildtronix Pre-Con API", "docs": "/docs"}
