from fintracker import taxonomy


def test_sides_have_expected_sizes():
    assert len(taxonomy.EXPENSE_CATEGORIES) == 20
    assert len(taxonomy.INCOME_CATEGORIES) == 8
    assert sum(len(s) for s in taxonomy.EXPENSE_CATEGORIES.values()) == 109
    assert sum(len(s) for s in taxonomy.INCOME_CATEGORIES.values()) == 30


def test_no_name_overlap_between_sides():
    assert not set(taxonomy.EXPENSE_CATEGORIES) & set(taxonomy.INCOME_CATEGORIES)


def test_no_duplicate_subcategories_within_a_category():
    for cats in (taxonomy.EXPENSE_CATEGORIES, taxonomy.INCOME_CATEGORIES):
        for cat, subs in cats.items():
            assert len(subs) == len(set(subs)), f"duplicate subcategory in {cat}"


def test_canonical_order_starts_as_screenshotted():
    assert next(iter(taxonomy.EXPENSE_CATEGORIES)) == "Groceries"
    assert next(iter(taxonomy.INCOME_CATEGORIES)) == "Salary"


def test_is_valid_accepts_category_alone():
    assert taxonomy.is_valid("Car")
    assert taxonomy.is_valid("Salary", None)


def test_is_valid_accepts_own_subcategory():
    assert taxonomy.is_valid("Car", "Fuel")
    assert taxonomy.is_valid("Windfall", "Found money")


def test_is_valid_rejects_unknown_category():
    assert not taxonomy.is_valid("Food & Dining")


def test_is_valid_rejects_foreign_subcategory():
    assert not taxonomy.is_valid("Car", "Supermarket")


def test_income_other_has_no_subcategories():
    assert taxonomy.INCOME_CATEGORIES["Other"] == ()


def test_prompt_block_contains_every_category():
    block = taxonomy.prompt_block()
    for cat in (*taxonomy.EXPENSE_CATEGORIES, *taxonomy.INCOME_CATEGORIES):
        assert f"- {cat}" in block
    assert "Expense categories:" in block
    assert "Income categories:" in block
