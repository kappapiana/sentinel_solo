-- PostgreSQL bootstrap for Sentinel Solo (RLS-safe user and login operations).
-- Run once as a superuser (e.g. postgres) so that the app works correctly with RLS.
--
-- Creates schema "app" and SECURITY DEFINER functions used by the app:
--   Login / first run: has_any_user, get_login_credentials, create_first_admin
--   Admin check:      current_user_is_admin, get_current_user_info, get_user_is_admin
--   User admin:       list_users, get_user, create_user, update_user, delete_user
--   Sharing / merge:  list_users_for_share, get_owned_matter_paths, merge_other_matter_into
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

-- Return (id, username) for all users (for share dropdown). Any user can call; SECURITY DEFINER bypasses RLS.
CREATE OR REPLACE FUNCTION app.list_users_for_share(p_caller_id int)
RETURNS TABLE(id int, username text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT u.id, u.username FROM public.users u ORDER BY u.username
$$;

-- Return (matter_id, path) for all matters owned by p_user_id (recursive full path). Used for same-name conflict when sharing.
CREATE OR REPLACE FUNCTION app.get_owned_matter_paths(p_user_id int)
RETURNS TABLE(matter_id int, path text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  WITH RECURSIVE paths AS (
    SELECT m.id AS node_id, m.name AS path
    FROM public.matters m
    WHERE m.owner_id = p_user_id AND m.parent_id IS NULL
    UNION ALL
    SELECT m.id, p.path || ' > ' || m.name
    FROM public.matters m
    JOIN paths p ON m.parent_id = p.node_id
    WHERE m.owner_id = p_user_id
  )
  SELECT node_id AS matter_id, path FROM paths
$$;

-- Merge source matter into target (caller must own target). Returns error message or NULL on success.
CREATE OR REPLACE FUNCTION app.merge_other_matter_into(p_caller_id int, p_src_id int, p_tgt_id int)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  tgt_owner int;
  src_rec record;
BEGIN
  SELECT owner_id INTO tgt_owner FROM public.matters WHERE id = p_tgt_id;
  IF tgt_owner IS NULL OR tgt_owner != p_caller_id THEN
    RETURN 'Target matter not found or not owned by you.';
  END IF;
  SELECT id, owner_id, parent_id INTO src_rec FROM public.matters WHERE id = p_src_id;
  IF src_rec.id IS NULL THEN
    RETURN 'Source matter not found.';
  END IF;
  IF p_src_id = p_tgt_id THEN
    RETURN 'Cannot merge a matter into itself.';
  END IF;
  UPDATE public.time_entries SET matter_id = p_tgt_id WHERE matter_id = p_src_id;
  UPDATE public.matters SET parent_id = p_tgt_id WHERE parent_id = p_src_id;
  DELETE FROM public.matter_shares WHERE matter_id = p_src_id;
  DELETE FROM public.user_matter_rates WHERE matter_id = p_src_id;
  DELETE FROM public.matters WHERE id = p_src_id;
  RETURN NULL;
END
$$;

-- Allow the app role to call these functions. Use the same role as in DATABASE_URL
-- (e.g. if your URL is postgresql://admin:... then use: GRANT ... TO admin).
-- Granting to PUBLIC ensures any role (including your app user) works.
GRANT USAGE ON SCHEMA app TO PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO PUBLIC;
