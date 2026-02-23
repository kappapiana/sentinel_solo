from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Float, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)  # nullable for future OAuth
    is_admin = Column(Boolean, default=False, nullable=False)
    default_hourly_rate_euro = Column(Float, nullable=True)

    matters = relationship("Matter", back_populates="owner")
    time_entries = relationship("TimeEntry", back_populates="owner")


class Matter(Base):
    __tablename__ = "matters"
    __table_args__ = (UniqueConstraint("owner_id", "matter_code", name="uq_matter_owner_code"),)
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    matter_code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("matters.id"), nullable=True)
    hourly_rate_euro = Column(Float, nullable=True)

    owner = relationship("User", back_populates="matters")
    sub_matters = relationship("Matter", backref="parent", remote_side=[id])
    time_entries = relationship("TimeEntry", back_populates="matter")

    def get_full_path(self, session):
        """Recursive path builder: 'Client > Project > Sub'"""
        if self.parent_id is None:
            return self.name
        parent = session.query(Matter).get(self.parent_id)
        return f"{parent.get_full_path(session)} > {self.name}" if parent else self.name

class TimeEntry(Base):
    __tablename__ = "time_entries"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    matter_id = Column(Integer, ForeignKey("matters.id"), nullable=False)
    description = Column(String)
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    invoiced = Column(Boolean, default=False, nullable=False)
    # Link segments of the same logical activity (Continue task): first segment has None, continued segments point to first entry id
    activity_group_id = Column(Integer, ForeignKey("time_entries.id"), nullable=True)
    owner = relationship("User", back_populates="time_entries")
    matter = relationship("Matter", back_populates="time_entries")