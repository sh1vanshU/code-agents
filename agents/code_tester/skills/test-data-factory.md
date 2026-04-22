---
name: test-data-factory
description: Create test data factories/builders — Builder pattern, randomized valid data, fixture management, database seeding
---

## Before You Start

- Identify the core domain entities in the project (User, Order, Payment, etc.)
- Read the entity/model definitions to understand required fields, constraints, and relationships
- Check existing test data patterns — are there already factories, fixtures, or raw dict literals?
- Know the ORM or data layer (SQLAlchemy, Django ORM, Prisma, JPA, etc.)

## Workflow

1. **Audit current test data patterns.** Search for how tests create data today:
   ```bash
   # Look for inline data creation in tests
   grep -rn "dict(" tests/ | head -20
   grep -rn "Model(" tests/ | head -20
   grep -rn "factory" tests/ | head -20
   ```
   - Flag: copy-pasted dict literals across tests (DRY violation)
   - Flag: tests that create data with ALL fields when they only test one
   - Flag: hardcoded IDs, emails, timestamps that could collide

2. **Design the builder pattern** for each core entity:
   ```python
   # Python Builder pattern
   class UserBuilder:
       def __init__(self):
           self._data = {
               "id": uuid4().hex[:8],
               "name": f"test-user-{uuid4().hex[:6]}",
               "email": f"test-{uuid4().hex[:6]}@example.com",
               "role": "member",
               "active": True,
               "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
           }

       def with_name(self, name: str) -> "UserBuilder":
           self._data["name"] = name
           return self

       def with_role(self, role: str) -> "UserBuilder":
           self._data["role"] = role
           return self

       def admin(self) -> "UserBuilder":
           self._data["role"] = "admin"
           return self

       def inactive(self) -> "UserBuilder":
           self._data["active"] = False
           return self

       def build(self) -> dict:
           return dict(self._data)

       def build_model(self) -> User:
           return User(**self._data)
   ```

3. **Design convenience functions** for common cases:
   ```python
   # Simple functional API alongside builders
   def a_user(**overrides) -> dict:
       return {**UserBuilder().build(), **overrides}

   def an_admin(**overrides) -> dict:
       return {**UserBuilder().admin().build(), **overrides}

   def an_order(user_id: str = None, **overrides) -> dict:
       return {
           **OrderBuilder().build(),
           "user_id": user_id or a_user()["id"],
           **overrides,
       }
   ```

4. **Handle entity relationships:**
   - Builders should auto-create required parent entities with defaults
   - Allow overriding the parent: `OrderBuilder().with_user(specific_user).build()`
   - For lists, provide batch methods: `UserBuilder.batch(5)` creates 5 users
   ```python
   class OrderBuilder:
       def __init__(self):
           self._user = UserBuilder()
           self._data = {
               "id": uuid4().hex[:8],
               "amount": Decimal("99.99"),
               "status": "pending",
           }

       def with_user(self, user_builder: UserBuilder) -> "OrderBuilder":
           self._user = user_builder
           return self

       def build(self) -> dict:
           user = self._user.build()
           return {**self._data, "user_id": user["id"], "_user": user}
   ```

5. **Add randomized but valid data generation:**
   - Use `faker` or simple random helpers for realistic data
   - Keep data valid by default — random does not mean invalid
   - Pin random seeds in tests that need deterministic output
   ```python
   import random
   import string

   def random_email() -> str:
       prefix = "".join(random.choices(string.ascii_lowercase, k=8))
       return f"{prefix}@example.com"

   def random_amount(min_val=1, max_val=10000) -> Decimal:
       return Decimal(f"{random.uniform(min_val, max_val):.2f}")
   ```

6. **Create pytest fixtures for common data scenarios:**
   ```python
   # conftest.py
   @pytest.fixture
   def user_data() -> dict:
       return UserBuilder().build()

   @pytest.fixture
   def admin_data() -> dict:
       return UserBuilder().admin().build()

   @pytest.fixture
   def order_with_user() -> dict:
       return OrderBuilder().build()
   ```

7. **Set up database seeding for integration tests:**
   ```python
   @pytest.fixture
   def seeded_db(db_session):
       """Seed database with standard test data."""
       users = [UserBuilder().build_model() for _ in range(5)]
       orders = [OrderBuilder().with_user(UserBuilder()).build_model() for _ in range(10)]
       db_session.add_all(users + orders)
       db_session.commit()
       yield db_session
       # Teardown handled by transaction rollback fixture
   ```

8. **Organize factory files:**
   ```
   tests/
     factories/
       __init__.py          # Re-export all builders
       user_factory.py      # UserBuilder + a_user()
       order_factory.py     # OrderBuilder + an_order()
       payment_factory.py   # PaymentBuilder + a_payment()
     conftest.py            # Fixtures using factories
   ```

9. **Verify factories work.** Write a quick smoke test:
   ```python
   def test_user_builder_defaults():
       user = UserBuilder().build()
       assert user["name"].startswith("test-user-")
       assert "@example.com" in user["email"]
       assert user["active"] is True

   def test_user_builder_overrides():
       user = UserBuilder().with_name("Alice").admin().build()
       assert user["name"] == "Alice"
       assert user["role"] == "admin"

   def test_order_builder_auto_creates_user():
       order = OrderBuilder().build()
       assert "user_id" in order
       assert order["user_id"] is not None
   ```

## Definition of Done

- [ ] Builder class created for each core domain entity
- [ ] Builders have sensible defaults — `Builder().build()` produces valid data with no args
- [ ] Method chaining works for all overridable fields
- [ ] Convenience functions (`a_user()`, `an_order()`) exist for simple cases
- [ ] Entity relationships handled — child builders auto-create parents
- [ ] Randomized data is valid by default (no constraint violations)
- [ ] Pytest fixtures defined in conftest.py for common scenarios
- [ ] Database seeding fixture available for integration tests
- [ ] Factory files organized in `tests/factories/` directory
- [ ] Smoke tests for builders pass
