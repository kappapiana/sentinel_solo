-- Run this script once as a PostgreSQL superuser (e.g. postgres) so that login
-- works when no user is logged in (e.g. after "Log out", or on first launch).
--
-- Without this, has_any_user() and get_login_credentials() are subject to RLS
-- when the session has no app.current_user_id, so the app shows "Create first admin"
-- instead of the login form and login fails.
--
-- Usage: psql -U postgres -d YOUR_DATABASE -f scripts/postgres_bootstrap_login.sql
--
-- The superuser that runs this script will own the functions; they will then
-- bypass RLS when called by the app user.

CREATE SCHEMA IF NOT EXISTS app;

CREATE OR REPLACE FUNCTION app.current_user_is_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT COALESCE(
    (SELECT is_admin FROM public.users WHERE id::text = current_setting('app.current_user_id', true)),
    false
  )
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

-- Allow the app user (and any role) to call these functions.
GRANT USAGE ON SCHEMA app TO PUBLIC;
