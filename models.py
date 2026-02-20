from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Matter(Base):
    __tablename__ = 'matters'
    id = Column(Integer, primary_key=True)
    matter_code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey('matters.id'), nullable=True)
    
    sub_matters = relationship("Matter", backref="parent", remote_side=[id])
    time_entries = relationship("TimeEntry", back_populates="matter")

    def get_full_path(self, session):
        """Recursive path builder: 'Client > Project > Sub'"""
        if self.parent_id is None:
            return self.name
        parent = session.query(Matter).get(self.parent_id)
        return f"{parent.get_full_path(session)} > {self.name}" if parent else self.name

class TimeEntry(Base):
    __tablename__ = 'time_entries'
    id = Column(Integer, primary_key=True)
    matter_id = Column(Integer, ForeignKey('matters.id'), nullable=False)
    description = Column(String)
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    matter = relationship("Matter", back_populates="time_entries")