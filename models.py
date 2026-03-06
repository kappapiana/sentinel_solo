from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Float, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """Application user.

    Stores login credentials, admin flag, and an optional default hourly rate.
    Related to owned matters and time entries as well as shared matters and
    per-matter rate overrides.
    """
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
    """Matter (or client) node in the hierarchical tree.

    Roots (parent_id is None) represent clients; non-roots represent matters or
    submatters under a client. Hourly rate can be set on any node and is used
    (together with ancestors and the owning user) when resolving chargeable
    amounts.
    """
    __tablename__ = "matters"
    __table_args__ = (UniqueConstraint("owner_id", "matter_code", name="uq_matter_owner_code"),)
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    matter_code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("matters.id"), nullable=True)
    hourly_rate_euro = Column(Float, nullable=True)
    budget_eur = Column(Float, nullable=True)
    budget_threshold = Column(Float, nullable=True)

    owner = relationship("User", back_populates="matters")
    sub_matters = relationship("Matter", backref="parent", remote_side=[id])
    time_entries = relationship("TimeEntry", back_populates="matter")
    shares = relationship("MatterShare", back_populates="matter", cascade="all, delete-orphan")
    user_rates = relationship("UserMatterRate", back_populates="matter", cascade="all, delete-orphan")

    def get_full_path(self, session):
        """Return the full hierarchical path for this matter.

        Builds a label such as ``\"Client > Project > Sub\"`` by following the
        parent links up to the root. This helper is used throughout the UI
        (timer drop-downs, matters list, reporting, timesheet) so that the same
        path representation is shown everywhere.
        """
        if self.parent_id is None:
            return self.name
        parent = session.query(Matter).get(self.parent_id)
        return f"{parent.get_full_path(session)} > {self.name}" if parent else self.name


class MatterShare(Base):
    """Link table: which users a matter is shared with.

    Each row grants a user visibility on a matter that they do not own. The
    actual visibility rules are enforced in the DatabaseManager layer and, for
    PostgreSQL, reinforced by row level security policies.
    """
    __tablename__ = "matter_shares"
    __table_args__ = (UniqueConstraint("matter_id", "user_id", name="uq_matter_share"),)
    matter_id = Column(Integer, ForeignKey("matters.id"), primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, nullable=False)

    matter = relationship("Matter", back_populates="shares")
    user = relationship("User", back_populates="shared_matters")


class UserMatterRate(Base):
    """Per-user hourly rate override for a matter.

    When present for a (user, matter) pair, it takes precedence over the matter
    rate, any ancestor (client) rate, and the user's default hourly rate.
    """
    __tablename__ = "user_matter_rates"
    __table_args__ = (UniqueConstraint("user_id", "matter_id", name="uq_user_matter_rate"),)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, nullable=False)
    matter_id = Column(Integer, ForeignKey("matters.id"), primary_key=True, nullable=False)
    hourly_rate_euro = Column(Float, nullable=False)

    user = relationship("User", back_populates="matter_rates")
    matter = relationship("Matter", back_populates="user_rates")


class TimeEntry(Base):
    """Logged unit of work for a user on a matter.

    Time entries can be created by the running timer or manually. Duration is
    stored in seconds; ``invoiced`` flags whether it has been billed. The
    optional ``activity_group_id`` groups multiple segments of the same logical
    activity (created via \"Continue task\") so reporting and timesheets can
    treat them as one task.
    """
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