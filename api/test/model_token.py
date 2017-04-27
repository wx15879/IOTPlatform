import unittest

from bson import ObjectId


class TokenTests(unittest.TestCase):
    repository_collection = None

    def setUp(self):
        self.tokens = TokenTests.repository_collection.token_repository
        self.user1id = ObjectId()
        self.user2id = ObjectId()
        self.user3id = ObjectId()
        self.token1 = self.tokens.generate_token(self.user1id)
        self.token2 = self.tokens.generate_token(self.user2id)
        self.token3 = self.tokens.generate_token(self.user3id)

    def tearDown(self):
        self.tokens.clear_db()

    def test_TokenAddedCorrectly(self):
        token = self.tokens.find_by_token(self.token1)
        self.assertEqual(token['user_id'], self.user1id, "Token user was not added correctly.")

    def test_TokenRemovedCorrectly(self):
        self.tokens.invalidate_token(self.token3)
        all_remaining_tokens = self.tokens.get_all_tokens()
        self.assertEqual(len(all_remaining_tokens), 2, "A token was not removed.")

    def test_TokensAreUnique(self):
        unique = self.tokens.check_token_is_new(self.token1)
        self.assertFalse(unique, "The existing token was not recognised.")
