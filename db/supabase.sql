-- Supabase-only setup: run AFTER schema.sql and seed.sql in the Supabase SQL editor.
-- 1. Links Supabase Auth sign-ups to app_user rows.
-- 2. Row-level security so the public website (anon key) only sees what each person may see.
-- 3. A read-only login for the AI SQL bot.

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.current_app_user_id() RETURNS BIGINT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT user_id FROM app_user WHERE auth_user_id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION public.can_view_recipe(rid BIGINT) RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT EXISTS (
        SELECT 1 FROM recipe r
        WHERE r.recipe_id = rid
          AND (r.visibility IN ('public', 'unlisted')
               OR r.owner_id = current_app_user_id()
               OR EXISTS (SELECT 1 FROM recipe_share s
                          WHERE s.recipe_id = rid
                            AND s.shared_with_user_id = current_app_user_id())))
$$;

CREATE OR REPLACE FUNCTION public.can_edit_recipe(rid BIGINT) RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
    SELECT EXISTS (
        SELECT 1 FROM recipe r
        WHERE r.recipe_id = rid
          AND (r.owner_id = current_app_user_id()
               OR EXISTS (SELECT 1 FROM recipe_share s
                          WHERE s.recipe_id = rid
                            AND s.shared_with_user_id = current_app_user_id()
                            AND s.permission = 'edit')))
$$;

-- Keep recipe.updated_at current.
CREATE OR REPLACE FUNCTION public.touch_updated_at() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS recipe_touch ON recipe;
CREATE TRIGGER recipe_touch BEFORE UPDATE ON recipe
    FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Auth: when someone signs up, claim the app_user row with the same email,
-- or create a new one.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_new_auth_user() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
    base TEXT := lower(regexp_replace(split_part(NEW.email, '@', 1), '[^a-zA-Z0-9_]', '', 'g'));
    candidate TEXT;
    n INT := 0;
BEGIN
    UPDATE app_user SET auth_user_id = NEW.id
     WHERE lower(email) = lower(NEW.email) AND auth_user_id IS NULL;
    IF FOUND THEN
        RETURN NEW;
    END IF;
    IF base = '' THEN base := 'cook'; END IF;
    candidate := base;
    WHILE EXISTS (SELECT 1 FROM app_user WHERE username = candidate) LOOP
        n := n + 1;
        candidate := base || n;
    END LOOP;
    INSERT INTO app_user (auth_user_id, username, display_name, email)
    VALUES (NEW.id, candidate, candidate, NEW.email);
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
ALTER TABLE app_user          ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe            ENABLE ROW LEVEL SECURITY;
ALTER TABLE category          ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_category   ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuisine           ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_cuisine    ENABLE ROW LEVEL SECURITY;
ALTER TABLE tag               ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_tag        ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingredient        ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_ingredient ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_step       ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_equipment  ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_note       ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_image      ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipe_share      ENABLE ROW LEVEL SECURITY;
ALTER TABLE cook_log          ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_recipe      ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection        ENABLE ROW LEVEL SECURITY;
ALTER TABLE collection_recipe ENABLE ROW LEVEL SECURITY;

-- Profiles are public, but email is not: only these columns are readable.
REVOKE SELECT ON app_user FROM anon, authenticated;
GRANT SELECT (user_id, username, display_name, bio, created_at) ON app_user TO anon, authenticated;
CREATE POLICY app_user_read ON app_user FOR SELECT USING (true);
CREATE POLICY app_user_update_self ON app_user FOR UPDATE TO authenticated
    USING (auth_user_id = auth.uid()) WITH CHECK (auth_user_id = auth.uid());

-- Recipes
CREATE POLICY recipe_read ON recipe FOR SELECT USING (can_view_recipe(recipe_id));
CREATE POLICY recipe_insert ON recipe FOR INSERT TO authenticated
    WITH CHECK (owner_id = current_app_user_id());
CREATE POLICY recipe_update ON recipe FOR UPDATE TO authenticated
    USING (can_edit_recipe(recipe_id))
    WITH CHECK (can_edit_recipe(recipe_id));
CREATE POLICY recipe_delete ON recipe FOR DELETE TO authenticated
    USING (owner_id = current_app_user_id());

-- Lookup tables: anyone reads, signed-in users can add new names.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['category', 'cuisine', 'tag', 'ingredient'] LOOP
        EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (true)', t || '_read', t);
        EXECUTE format('CREATE POLICY %I ON %I FOR INSERT TO authenticated WITH CHECK (true)',
                       t || '_insert', t);
    END LOOP;
END $$;

-- Recipe parts: visible with the recipe, editable by whoever can edit the recipe.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['recipe_category', 'recipe_cuisine', 'recipe_tag',
                             'recipe_ingredient', 'recipe_step', 'recipe_equipment',
                             'recipe_image'] LOOP
        EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (can_view_recipe(recipe_id))',
                       t || '_read', t);
        EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO authenticated '
                       'USING (can_edit_recipe(recipe_id)) WITH CHECK (can_edit_recipe(recipe_id))',
                       t || '_write', t);
    END LOOP;
END $$;

-- Notes and comments: anyone who can see the recipe can read and add; authors edit their own.
CREATE POLICY recipe_note_read ON recipe_note FOR SELECT USING (can_view_recipe(recipe_id));
CREATE POLICY recipe_note_insert ON recipe_note FOR INSERT TO authenticated
    WITH CHECK (author_id = current_app_user_id() AND can_view_recipe(recipe_id));
CREATE POLICY recipe_note_modify ON recipe_note FOR UPDATE TO authenticated
    USING (author_id = current_app_user_id()) WITH CHECK (author_id = current_app_user_id());
CREATE POLICY recipe_note_delete ON recipe_note FOR DELETE TO authenticated
    USING (author_id = current_app_user_id());

-- Shares: the owner manages them; the person shared with can see theirs.
CREATE POLICY recipe_share_read ON recipe_share FOR SELECT TO authenticated
    USING (shared_with_user_id = current_app_user_id()
           OR EXISTS (SELECT 1 FROM recipe r WHERE r.recipe_id = recipe_share.recipe_id
                      AND r.owner_id = current_app_user_id()));
CREATE POLICY recipe_share_manage ON recipe_share FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM recipe r WHERE r.recipe_id = recipe_share.recipe_id
                   AND r.owner_id = current_app_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM recipe r WHERE r.recipe_id = recipe_share.recipe_id
                        AND r.owner_id = current_app_user_id()));

-- Cook logs: ratings on visible recipes are public; you manage your own.
CREATE POLICY cook_log_read ON cook_log FOR SELECT USING (can_view_recipe(recipe_id));
CREATE POLICY cook_log_manage ON cook_log FOR ALL TO authenticated
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id() AND can_view_recipe(recipe_id));

-- Saved recipes are private to each user.
CREATE POLICY saved_recipe_own ON saved_recipe FOR ALL TO authenticated
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id() AND can_view_recipe(recipe_id));

-- Collections
CREATE POLICY collection_read ON collection FOR SELECT
    USING (visibility IN ('public', 'unlisted') OR owner_id = current_app_user_id());
CREATE POLICY collection_manage ON collection FOR ALL TO authenticated
    USING (owner_id = current_app_user_id()) WITH CHECK (owner_id = current_app_user_id());
CREATE POLICY collection_recipe_read ON collection_recipe FOR SELECT
    USING (can_view_recipe(recipe_id) AND EXISTS (
        SELECT 1 FROM collection c WHERE c.collection_id = collection_recipe.collection_id
        AND (c.visibility IN ('public', 'unlisted') OR c.owner_id = current_app_user_id())));
CREATE POLICY collection_recipe_manage ON collection_recipe FOR ALL TO authenticated
    USING (EXISTS (SELECT 1 FROM collection c WHERE c.collection_id = collection_recipe.collection_id
                   AND c.owner_id = current_app_user_id()))
    WITH CHECK (can_view_recipe(recipe_id) AND EXISTS (
        SELECT 1 FROM collection c WHERE c.collection_id = collection_recipe.collection_id
        AND c.owner_id = current_app_user_id()));

-- ---------------------------------------------------------------------------
-- Read-only login for the AI SQL bot (bot/db_bot.py). It reads every row,
-- including private recipes, but cannot change anything.
-- Replace the password before running, and keep it out of git.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'recipe_bot') THEN
        CREATE ROLE recipe_bot LOGIN PASSWORD 'CHANGE_ME';
    END IF;
END $$;
ALTER ROLE recipe_bot SET default_transaction_read_only = on;
ALTER ROLE recipe_bot SET statement_timeout = '5s';
GRANT USAGE ON SCHEMA public TO recipe_bot;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO recipe_bot;
DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('CREATE POLICY %I ON %I FOR SELECT TO recipe_bot USING (true)',
                       t || '_bot_read', t);
    END LOOP;
END $$;
