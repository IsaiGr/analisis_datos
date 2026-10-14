import unittest

from scripts.check_publication import inspect_file


class PublicationTests(unittest.TestCase):
    def test_only_explicitly_allowed_paths(self):
        self.assertEqual(inspect_file('README.md', b'Public demo'), [])
        for name in ['datos.xlsx', '.env', 'artifacts/screenshot.png', 'src/private.csv', '../README.md']:
            self.assertIn('file outside publication allowlist', inspect_file(name, b'example'))

    def test_secrets_rejected_without_echoing_values(self):
        fake = ('gh' + 'p_' + 'a' * 36).encode()
        result = inspect_file('app.py', fake)
        self.assertIn('possible GitHub credential', result)
        self.assertNotIn(fake.decode(), str(result))

    def test_personal_paths_and_email_are_detected(self):
        self.assertIn('personal Windows path', inspect_file('README.md', ('C:' + '/Users/' + 'example/file').encode()))
        self.assertIn('possible personal email', inspect_file('README.md', ('example' + '@' + 'gmail.com').encode()))

    def test_binary_symlink_and_large_content_are_rejected(self):
        self.assertTrue(inspect_file('app.py', b'\0'))
        self.assertTrue(inspect_file('app.py', b'example', '120000'))
        self.assertTrue(inspect_file('app.py', b'a' * 1_000_001))


if __name__ == '__main__':
    unittest.main()
