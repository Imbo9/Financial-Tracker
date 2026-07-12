"""Single source of truth for the category taxonomy (MoneyManager replica, 2026-07-12).

Every consumer derives from this module: categorizer prompt, API validation,
GET /v1/categories, frontend picker and colors. To add/rename/remove a category
edit ONLY this file (renames also need a one-off UPDATE on transactions labels —
see docs/superpowers/specs/2026-07-12-categories-taxonomy-design.md, playbook).
"""

EXPENSE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Groceries": ("Supermarket", "Market & Fresh produce", "Household supplies"),
    "Car": (
        "Fuel",
        "Insurance & Road tax",
        "Maintenance & Service",
        "Tolls & Parking",
        "Fines",
        "Wash & Detailing",
        "Accessories & Parts",
        "Car rental",
    ),
    "Eating Out": (
        "Restaurants & Pizzerias",
        "Cafés & Breakfast",
        "Work Lunch",
        "Delivery",
        "Drinks & Aperitifs",
        "Street food & Quick bites",
    ),
    "Personal shopping": (
        "Clothing",
        "Shoes",
        "Accessories",
        "Electronics & Gadgets",
        "Impulse buys",
    ),
    "Personal care": (
        "Hair & Barber",
        "Cosmetics & Skincare",
        "Fragrances",
        "Laundry & Tailoring",
    ),
    "Health": (
        "Doctor visits & Specialists",
        "Pharmacy",
        "Dentist",
        "Optical",
        "Tests & Lab works",
        "Health Insurance",
        "Medical therapies",
    ),
    "Wellness & Fitness": (
        "Gym",
        "Nutritionist & Dietitian",
        "Supplements",
        "Treatments (massage, spa, aesthetics)",
        "Basic fitness gear",
    ),
    "Main hobby": ("Equipment", "Consumables", "Courses & Lessons", "Events & Community"),
    "Sport & Outdoor": (
        "Equipment",
        "Lift passes & Entry fees",
        "Lessons & Guides",
        "Activity transport",
        "Activity lodging",
        "Activity meals",
        "Memberships & Fees",
    ),
    "Entertainment": (
        "Music streaming",
        "Video streaming",
        "Cinema & Theatre",
        "Concerts & Events",
        "Books & Comics",
        "Video games & Apps",
        "Podcasts & Audiobooks",
        "Tech gadgets & Experiential",
    ),
    "Partner": (
        "Shared experiences",
        "Shared shopping",
        "Recurring expenses",
        "Anniversaries & Milestones",
    ),
    "Family": (
        "Shared experiences",
        "Contributions & Support",
        "Care & Assistance",
        "Family events",
    ),
    "Gifts": ("Birthdays", "Holidays", "Special occasions", "Group gifts"),
    "Social life": ("Events & Activities", "Memberships & Dues", "Hosting & Treats"),
    "Transit": (
        "Urban public transport",
        "Trains & Long distance",
        "Taxi & Ride-sharing",
        "Sharing services (car, bike, scooter)",
    ),
    "Travel": (
        "Flights",
        "Lodging",
        "Local transport",
        "Food while traveling",
        "Activities & Experiences",
        "Souvenirs & Travel shopping",
        "Documents & Visas",
    ),
    "Connectivity": ("Mobile phone", "Home internet", "Roaming & eSIM", "VoIP & Cloud telephony"),
    "Digital services": (
        "AI & Productivity",
        "Cloud & Storage",
        "Creative tools",
        "Security",
        "Reading & News",
        "Domains & Hosting",
        "Development & Tools",
    ),
    "Career & Professional development": (
        "Courses & Certifications",
        "Technical books & Manuals",
        "Conferences & Events",
        "Professional subscriptions",
        "Career tools",
        "Networking & Community",
        "Relocation & Job mobility",
        "Languages",
    ),
    "Finance & Admin": (
        "Bank fees",
        "Taxes & Stamps",
        "Personal documents",
        "Insurance (non-vehicle)",
        "Donations & Charity",
        "Professional consulting (accountant, legal)",
        "Miscellaneous & Unexpected",
    ),
}

INCOME_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Salary": (
        "Base salary",
        "Overtime & Extra hours",
        "Variable & Bonus",
        "Benefits & Perks",
        "Equity & Stock",
        "Severance & End-of-employment",
    ),
    "Freelance & Side income": (
        "Consulting & Projects",
        "Content & Royalties",
        "Teaching & Workshops",
    ),
    "Investments": ("Dividends", "Interest", "Capital gains", "Crypto gains", "P2P & Alternative"),
    "Gifts received": ("From family", "From partner", "From others", "Occasions"),
    "Reimbursements": (
        "From Partner",
        "From Friends",
        "From Family",
        "Work expenses",
        "Returns & Refunds",
        "Insurance claims",
    ),
    "Tax & State": ("Tax refunds", "Public bonuses", "Subsidies & Grants"),
    "Windfall": ("Sales", "Winnings & Prizes", "Found money"),
    "Other": (),
}

_ALL_CATEGORIES = {**EXPENSE_CATEGORIES, **INCOME_CATEGORIES}


def is_valid(category: str, subcategory: str | None = None) -> bool:
    """True when the category exists and the subcategory (if given) belongs to it."""
    subs = _ALL_CATEGORIES.get(category)
    if subs is None:
        return False
    return subcategory is None or subcategory in subs


def _render(side_name: str, categories: dict[str, tuple[str, ...]]) -> list[str]:
    lines = [f"{side_name} categories:"]
    for cat, subs in categories.items():
        lines.append(f"- {cat}: {', '.join(subs)}" if subs else f"- {cat}")
    return lines


def prompt_block() -> str:
    """Category list rendered for the categorizer system prompt."""
    return "\n".join(
        [*_render("Expense", EXPENSE_CATEGORIES), "", *_render("Income", INCOME_CATEGORIES)]
    )
