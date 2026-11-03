"""Static regression checks. Real Supabase RLS must also be tested after setup."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent

class OwnerVIPSecurity(unittest.TestCase):
    def setUp(self):
        self.sql = (ROOT / 'supabase.sql').read_text()
        self.js = (ROOT / 'vip.js').read_text()

    def test_singleton_owner(self):
        self.assertIn('slot boolean primary key default true check (slot = true)', self.sql)
        self.assertIn('user_id uuid not null unique references auth.users(id)', self.sql)
        self.assertIn('using (user_id = (select auth.uid()))', self.sql)

    def test_no_self_grant(self):
        self.assertIn('revoke all on public.site_owner from anon, authenticated;', self.sql)
        self.assertIn('grant select on public.site_owner to authenticated;', self.sql)
        self.assertNotIn('grant insert on public.site_owner to authenticated;', self.sql)
        self.assertNotIn('grant update on public.site_owner to authenticated;', self.sql)

    def test_owner_or_active_membership(self):
        self.assertIn('exists (select 1 from public.site_owner o', self.sql)
        self.assertIn("m.status = 'active'", self.sql)
        self.assertIn('m.expires_at > now()', self.sql)

    def test_client_checks_real_uuid(self):
        self.assertIn("db.from('site_owner').select('user_id')", self.js)
        self.assertIn('ownerResult.data?.user_id === user.id', self.js)
        self.assertIn('Database row-level security', self.js)
        self.assertIn("supabaseUrl:", (ROOT / 'config.js').read_text())
        self.assertIn("supabaseAnonKey:", (ROOT / 'config.js').read_text())
        self.assertNotIn("service_role", (ROOT / 'config.js').read_text().split("window.GOALGRID_CONFIG =", 1)[-1])

if __name__ == '__main__':
    unittest.main()
