"""Shared fixtures — loads backend .env so tests can access MONGO_URL etc."""
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
