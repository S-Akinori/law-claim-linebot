# main.py
from fastapi import FastAPI
from line_handler import router
from cron import router as cron_router

app = FastAPI()
app.include_router(router)
app.include_router(cron_router)