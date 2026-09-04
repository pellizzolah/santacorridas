import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'chave-secreta-super-segura-ifitness'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///ifitness.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False