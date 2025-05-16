# main.py
from fastapi import FastAPI
from line_handler import router
from cron import router as cron_router
from cron_job.not_complete_message import router as not_complete_message_router

app = FastAPI()
app.include_router(router)
app.include_router(cron_router)
app.include_router(not_complete_message_router)