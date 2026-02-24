-- PostgreSQL bootstrap for Sentinel Solo (RLS-safe user and login operations).
-- Run once as a superuser (e.g. postgres) so that the app works correctly with RLS.
--
-- Creates schema "app" and SECURITY DEFINER functions used by the app:
--   Login / first run: has_any_user, get_login_credentials, create_first_admin
--   Admin check:      current_user_is_admin, get_current_user_info, get_user_is_admin
--   User admin:       list_users, get_user, create_user, update_user, delete_user
--
-- Usage: psql -U postgres -d YOUR_DATABASE -f scripts/postgres_bootstrap_login.sql
--        (or from the server: sudo -u postgres psql -d timesheets -f /path/to/scripts/postgres_bootstrap_login.sql)
--
-- The superuser that runs this script will own the functions; they bypass RLS
-- when called by the app role. GRANTs at the end allow the app user to call them.

CREATE SCHEMA IF NOT EXISTS app;

CREATE OR REPLACE FUNCTION app.current_user_is_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT COALESCE(
    (SELECT is_admin FROM public.users WHERE id::text = current_setting('app.current_user_id', true)),
    false
  )
$$;

-- Returns (id, username, is_admin) for the user in app.current_user_id. Bypasses RLS so the app can always resolve admin flag.
CREATE OR REPLACE FUNCTION app.get_current_user_info()
RETURNS table(id int, username text, is_admin boolean) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT u.id, u.username, u.is_admin
  FROM public.users u
  WHERE u.id::text = current_setting('app.current_user_id', true)
$$;

-- Returns is_admin for user id. Bypasses RLS; no session variable needed. Used so the app can show Users tab reliably.
CREATE OR REPLACE FUNCTION app.get_user_is_admin(p_user_id int)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT COALESCE((SELECT is_admin FROM public.users WHERE id = p_user_id), false)
$$;

CREATE OR REPLACE FUNCTION app.has_any_user()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT (SELECT count(*) FROM public.users) > 0
$$;

CREATE OR REPLACE FUNCTION app.get_login_credentials(p_username text)
RETURNS table(id int, password_hash text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT u.id, u.password_hash FROM public.users u WHERE u.username = p_username
$$;

CREATE OR REPLACE FUNCTION app.create_first_admin(p_username text, p_password_hash text)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  new_id int;
BEGIN
  IF (SELECT count(*) FROM public.users) > 0 THEN
    RETURN NULL;
  END IF;
  INSERT INTO public.users (username, password_hash, is_admin)
  VALUES (p_username, p_password_hash, true)
  RETURNING id INTO new_id;
  RETURN new_id;
END
$$;

-- Create a user (admin only). Caller must pass their user_id; we check they are admin. Bypasses RLS so insert succeeds.
CREATE OR REPLACE FUNCTION app.create_user(p_caller_id int, p_username text, p_password_hash text, p_is_admin boolean)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  new_id int;
BEGIN
  IF NOT app.get_user_is_admin(p_caller_id) THEN
    RAISE EXCEPTION 'Only admin can create users.';
  END IF;
  INSERT INTO public.users (username, password_hash, is_admin)
  VALUES (p_username, p_password_hash, p_is_admin)
  RETURNING id INTO new_id;
  RETURN new_id;
END
$$;

-- Return all users (admin only). Caller must pass their user_id; we check they are admin. Bypasses RLS.
-- Types must match public.users (username/password_hash varchar, default_hourly_rate_euro double precision).
CREATE OR REPLACE FUNCTION app.list_users(p_caller_id int)
RETURNS table(id int, username character varying, password_hash character varying, is_admin boolean, default_hourly_rate_euro double precision)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  IF NOT app.get_user_is_admin(p_caller_id) THEN
    RETURN;
  END IF;
  RETURN QUERY
  SELECT u.id, u.username, u.password_hash, u.is_admin, u.default_hourly_rate_euro
  FROM public.users u
  ORDER BY u.username;
END
$$;

-- Return one user row if caller may see it (self or admin). Types match public.users.
CREATE OR REPLACE FUNCTION app.get_user(p_caller_id int, p_user_id int)
RETURNS table(id int, username character varying, password_hash character varying, is_admin boolean, default_hourly_rate_euro double precision)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT u.id, u.username, u.password_hash, u.is_admin, u.default_hourly_rate_euro
  FROM public.users u
  WHERE u.id = p_user_id
    AND (p_caller_id = p_user_id OR app.get_user_is_admin(p_caller_id))
$$;

-- Update user (self or admin; only admin can change is_admin). NULL args mean leave unchanged; p_clear_default_rate true = set rate to NULL.
CREATE OR REPLACE FUNCTION app.update_user(
  p_caller_id int,
  p_user_id int,
  p_username character varying DEFAULT NULL,
  p_password_hash character varying DEFAULT NULL,
  p_is_admin boolean DEFAULT NULL,
  p_default_hourly_rate_euro double precision DEFAULT NULL,
  p_clear_default_rate boolean DEFAULT false
)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  IF p_caller_id != p_user_id AND NOT app.get_user_is_admin(p_caller_id) THEN
    RAISE EXCEPTION 'User not found or no permission.';
  END IF;
  IF p_is_admin IS NOT NULL AND p_caller_id != p_user_id AND NOT app.get_user_is_admin(p_caller_id) THEN
    RAISE EXCEPTION 'Only admin can change is_admin.';
  END IF;
  UPDATE public.users u SET
    username = COALESCE(p_username, u.username),
    password_hash = COALESCE(p_password_hash, u.password_hash),
    is_admin = COALESCE(p_is_admin, u.is_admin),
    default_hourly_rate_euro = CASE
      WHEN p_clear_default_rate THEN NULL
      WHEN p_default_hourly_rate_euro IS NOT NULL THEN p_default_hourly_rate_euro
      ELSE u.default_hourly_rate_euro
    END
  WHERE u.id = p_user_id;
END
$$;

-- Delete user (admin only).
CREATE OR REPLACE FUNCTION app.delete_user(p_caller_id int, p_user_id int)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  IF NOT app.get_user_is_admin(p_caller_id) THEN
    RAISE EXCEPTION 'Only admin can delete users.';
  END IF;
  DELETE FROM public.users WHERE id = p_user_id;
END
$$;

-- Allow the app role to call these functions. Use the same role as in DATABASE_URL
-- (e.g. if your URL is postgresql://admin:... then use: GRANT ... TO admin).
-- Granting to PUBLIC ensures any role (including your app user) works.
GRANT USAGE ON SCHEMA app TO PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO PUBLIC;
