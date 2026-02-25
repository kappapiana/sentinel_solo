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
    shared_matters = relationship("MatterShare", back_populates="user")
    matter_rates = relationship("UserMatterRate", back_populates="user")


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
    shares = relationship("MatterShare", back_populates="matter", cascade="all, delete-orphan")
    user_rates = relationship("UserMatterRate", back_populates="matter", cascade="all, delete-orphan")

    def get_full_path(self, session):
        """Recursive path builder: 'Client > Project > Sub'"""
        if self.parent_id is None:
            return self.name
        parent = session.query(Matter).get(self.parent_id)
        return f"{parent.get_full_path(session)} > {self.name}" if parent else self.name


class MatterShare(Base):
    __tablename__ = "matter_shares"
    __table_args__ = (UniqueConstraint("matter_id", "user_id", name="uq_matter_share"),)
    matter_id = Column(Integer, ForeignKey("matters.id"), primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, nullable=False)

    matter = relationship("Matter", back_populates="shares")
    user = relationship("User", back_populates="shared_matters")


class UserMatterRate(Base):
    __tablename__ = "user_matter_rates"
    __table_args__ = (UniqueConstraint("user_id", "matter_id", name="uq_user_matter_rate"),)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, nullable=False)
    matter_id = Column(Integer, ForeignKey("matters.id"), primary_key=True, nullable=False)
    hourly_rate_euro = Column(Float, nullable=False)

    user = relationship("User", back_populates="matter_rates")
    matter = relationship("Matter", back_populates="user_rates")


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