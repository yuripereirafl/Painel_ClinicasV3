from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Modelo Clinic para representar uma clínica
class Clinic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=True)  # Localização opcional

# Modelo Password associado à clínica
class Password(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    guiche = db.Column(db.String(15), nullable=True) # Pode ser null até ser chamado
    queue_type = db.Column(db.String(50), nullable=False, default='NORMAL')
    status = db.Column(db.String(20), nullable=False, default='AGUARDANDO')
    date = db.Column(db.Date, nullable=False)
    called_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True) # Data/Hora de geração da senha
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)  # Relaciona com a clínica
    clinic = db.relationship('Clinic', backref=db.backref('passwords', lazy=True))

# Modelo Attendant (Atendente) associado à clínica
class Attendant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)  # Relaciona com a clínica
    clinic = db.relationship('Clinic', backref=db.backref('attendants', lazy=True))
