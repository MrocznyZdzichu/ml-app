import unittest
import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import (
    PBKDF2_ITERATIONS,
    hash_password,
    verify_password,
)
from app.main import create_app


class AuthFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_registration_login_and_user_scoped_datasets(self) -> None:
        email_a = f"alice-{uuid4()}@example.com"
        email_b = f"bob-{uuid4()}@example.com"
        password = "password123"

        self.assertEqual(self.client.get("/api/v1/datasets").status_code, 401)

        register_a = self.client.post(
            "/api/v1/auth/register",
            json={"email": email_a, "password": password, "display_name": "Alice"},
        )
        self.assertEqual(register_a.status_code, 201)
        token_a = register_a.json()["access_token"]

        login_a = self.client.post(
            "/api/v1/auth/login",
            json={"email": email_a, "password": password},
        )
        self.assertEqual(login_a.status_code, 200)

        dataset = self.client.post(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"name": "private-data", "source_type": "file", "format": "csv"},
        )
        self.assertEqual(dataset.status_code, 201)
        dataset_id = dataset.json()["id"]

        token_b = self.client.post(
            "/api/v1/auth/register",
            json={"email": email_b, "password": password, "display_name": "Bob"},
        ).json()["access_token"]

        datasets_a = self.client.get(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        datasets_b = self.client.get(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {token_b}"},
        )

        self.assertIn(dataset_id, {item["id"] for item in datasets_a.json()})
        self.assertNotIn(dataset_id, {item["id"] for item in datasets_b.json()})

    def test_duplicate_registration_and_bad_login_are_rejected(self) -> None:
        email = f"dupe-{uuid4()}@example.com"

        payload = {"email": email, "password": "password123", "display_name": "Dupe"}
        self.assertEqual(self.client.post("/api/v1/auth/register", json=payload).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/auth/register", json=payload).status_code, 409)
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password"},
            ).status_code,
            401,
        )

    def test_password_hashes_are_versioned_and_legacy_hashes_remain_valid(self) -> None:
        password = "password123"
        current_hash = hash_password(password)

        self.assertTrue(current_hash.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"))
        self.assertTrue(verify_password(password, current_hash))
        self.assertFalse(verify_password("wrong-password", current_hash))

        salt = "legacy-salt"
        legacy_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            120_000,
        ).hex()
        self.assertTrue(
            verify_password(password, f"pbkdf2_sha256${salt}${legacy_digest}")
        )
