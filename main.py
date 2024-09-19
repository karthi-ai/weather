# main.py
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime
from typing import List
import requests
from fastapi.middleware.cors import CORSMiddleware
from config import OPENWEATHERMAP_API_KEY

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./weather.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# OpenWeatherMap API setup
OPENWEATHERMAP_API_URL = "http://api.openweathermap.org/data/2.5/weather"

# Database model
class WeatherDB(Base):
    __tablename__ = "weather"
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    temperature = Column(Float)
    humidity = Column(Float)
    wind_speed = Column(Float)
    description = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Pydantic models
class WeatherBase(BaseModel):
    city: str
    temperature: float
    humidity: float
    wind_speed: float
    description: str

class WeatherCreate(WeatherBase):
    pass

class Weather(WeatherBase):
    id: int
    timestamp: datetime

    class Config:
        orm_mode = True

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/weather/", response_model=Weather)
def create_weather(weather: WeatherCreate, db: Session = Depends(get_db)):
    db_weather = WeatherDB(**weather.dict())
    db.add(db_weather)
    db.commit()
    db.refresh(db_weather)
    return db_weather

@app.get("/all-weather/", response_model=List[Weather])
def read_all_weather(db: Session = Depends(get_db)):
    weather = db.query(WeatherDB).order_by(WeatherDB.timestamp.desc()).all()
    return weather

@app.get("/weather/", response_model=List[Weather])
def read_weather(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    weather = db.query(WeatherDB).offset(skip).limit(limit).all()
    return weather

@app.get("/weather/{city}", response_model=Weather)
def read_weather_by_city(city: str, db: Session = Depends(get_db)):
    # Check if we have recent data in the database
    db_weather = db.query(WeatherDB).filter(WeatherDB.city == city).order_by(WeatherDB.timestamp.desc()).first()
    
    if db_weather and (datetime.utcnow() - db_weather.timestamp).total_seconds() < 3600:  # Data is less than 1 hour old
        return db_weather
    
    # If no recent data, fetch from OpenWeatherMap
    params = {
        "q": city,
        "appid": OPENWEATHERMAP_API_KEY,
        "units": "metric"
    }
    response = requests.get(OPENWEATHERMAP_API_URL, params=params)
    
    if response.status_code != 200:
        raise HTTPException(status_code=404, detail="City not found or API error")
    
    weather_data = response.json()
    new_weather = WeatherCreate(
        city=city,
        temperature=weather_data["main"]["temp"],
        humidity=weather_data["main"]["humidity"],
        wind_speed=weather_data["wind"]["speed"],
        description=weather_data["weather"][0]["description"]
    )
    
    # Save the new data to the database
    db_weather = WeatherDB(**new_weather.dict())
    db.add(db_weather)
    db.commit()
    db.refresh(db_weather)
    
    return db_weather

@app.put("/weather/{weather_id}", response_model=Weather)
def update_weather(weather_id: int, weather: WeatherCreate, db: Session = Depends(get_db)):
    db_weather = db.query(WeatherDB).filter(WeatherDB.id == weather_id).first()
    if db_weather is None:
        raise HTTPException(status_code=404, detail="Weather data not found")
    for key, value in weather.dict().items():
        setattr(db_weather, key, value)
    db.commit()
    db.refresh(db_weather)
    return db_weather

@app.delete("/weather/{weather_id}", response_model=Weather)
def delete_weather(weather_id: int, db: Session = Depends(get_db)):
    db_weather = db.query(WeatherDB).filter(WeatherDB.id == weather_id).first()
    if db_weather is None:
        raise HTTPException(status_code=404, detail="Weather data not found")
    db.delete(db_weather)
    db.commit()
    return db_weather